"""Build the generic, checksummed template artifact without examples or environments."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from template_manifest import TEMPLATE_PATHS
from template_metadata import metadata, record
from content import validate


def build(output,version=None):
    info=metadata(ROOT);current=info['version']
    if version is not None and version!=current: raise ValueError('Release version must match template.toml: '+current)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    (ROOT/'.scratch/tmp').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='template-release-',dir=ROOT/'.scratch/tmp') as temporary:
        stage=Path(temporary)/'researchlabfolio-template';stage.mkdir()
        for name in TEMPLATE_PATHS:
            source=ROOT/name
            if source.is_symlink(): raise ValueError('Template inventory contains a symlink: '+name)
            if source.is_dir():
                for p in source.rglob('*'):
                    if p.is_symlink(): raise ValueError('Template source contains a symlink: '+str(p))
                shutil.copytree(source,stage/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','_template'))
            elif source.is_file(): shutil.copy2(source,stage/name)
        manifest={'format':1,'template':'researchlabfolio','template_version':current,'content_schema':1,
                  'cli_min_version':info['cli_min_version'],'quarto_version':info['quarto_version'],'repository':'khan-lab/researchlabfolio'}
        (stage/'.researchlabfolio-release.json').write_text(json.dumps(manifest,indent=2)+'\n')
        validate(stage)
        record(stage)
        archive=output/'researchlabfolio-template.tar.gz'
        with archive.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped, tarfile.open(fileobj=zipped,mode='w') as tar:
            for p in sorted(stage.rglob('*')):
                if not p.is_file(): continue
                info=tar.gettarinfo(str(p),arcname='researchlabfolio-template/'+p.relative_to(stage).as_posix())
                info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o644
                with p.open('rb') as contents: tar.addfile(info,contents)
        checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
        (output/'SHA256SUMS').write_text(checksum+'  '+archive.name+'\n')
        return archive

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.scratch/releases/template')
    parser.add_argument('--version')
    args=parser.parse_args()
    try: print(build(args.output,args.version))
    except (ValueError,OSError) as exc: raise SystemExit(str(exc))
