"""Template version and framework baselines, independent of the Python CLI package."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import tomllib
from content import ContentError

STATE = '.researchlabfolio-template.json'
SCHEMA = 1
# Legacy package paths remain eligible so upgrades can remove unchanged old copies.
PREFIXES = ('scripts/', 'framework/', 'styles/', 'assets/fonts/', 'researchlabfolio/', '.github/workflows/')
FILES = {'_quarto.yml', 'pixi.toml', 'pixi.lock', 'template.toml', 'pyproject.toml', 'setup.py', 'template_manifest.py', 'MANIFEST.in', '.gitattributes'}
VERSION = r'\d+\.\d+\.\d+(?:[-+][\w.-]+)?'


def metadata(root):
    root = Path(root)
    path = root / 'template.toml'
    try:
        if path.exists():
            value = tomllib.loads(path.read_text())['template']
            if type(value.get('content_schema')) is not int or value['content_schema'] != SCHEMA:
                raise ValueError('unsupported content schema')
        else:
            # Read older releases as data; never import their bundled package.
            path = root / 'pyproject.toml'
            value = tomllib.loads(path.read_text())['project']
        if value.get('name') != 'researchlabfolio' or not isinstance(value.get('version'), str) or not re.fullmatch(VERSION, value['version']):
            raise ValueError('invalid template name or version')
        return value
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ContentError(f'{path.name}: expected versioned ResearchLabFolio template metadata ({exc}).') from None


def owned(name):
    if not isinstance(name, str): return False
    path = PurePosixPath(name)
    return ('\\' not in name and not path.is_absolute() and '..' not in path.parts and '.' not in path.parts
            and (name in FILES or name.startswith(PREFIXES))
            and not any(part in ('_template', '__pycache__', '.git', '.scratch', '.env') for part in path.parts)
            and not name.endswith('.pyc'))


def state_for(root, flavor, data):
    project = metadata(root)
    state = {'format': 1, 'template': 'researchlabfolio', 'template_version': project['version'],
             'content_schema': SCHEMA, 'flavor': flavor,
             'files': {name: hashlib.sha256(value).hexdigest() for name, value in sorted(data.items())}}
    state['revision'] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return state


def record(root):
    """Record a repository baseline without importing or installing a CLI."""
    root = Path(root).resolve()
    candidates = [root / name for name in FILES]
    for prefix in PREFIXES:
        folder = root / prefix
        if folder.is_symlink(): raise ContentError('Template baseline refuses symlink: ' + prefix)
        if folder.exists(): candidates.extend(folder.rglob('*'))
    data = {}
    for path in candidates:
        name = path.relative_to(root).as_posix()
        if not owned(name): continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            raise ContentError('Template baseline refuses symlink: ' + name)
        if path.is_file(): data[name] = path.read_bytes()
    destination = root / STATE
    if destination.is_symlink(): raise ContentError('Template baseline refuses symlink: ' + STATE)
    result = state_for(root, 'repository', data)
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(record(args.root)['revision'])
