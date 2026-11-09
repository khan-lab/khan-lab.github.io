"""Private workspaces for render and preview processes; authored files stay separate."""
import os
from pathlib import Path
import re
import tempfile
from content import ROOT


def workspace(label):
    runs = ROOT / '.scratch/builds/runs'
    runs.mkdir(parents=True, exist_ok=True)
    prefix = re.sub(r'[^a-zA-Z0-9_-]+', '-', label).strip('-') or 'render'
    return Path(tempfile.mkdtemp(prefix=prefix + '-', dir=runs))


def environment(work):
    tmp = Path(work) / 'tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    # Quarto 1.11 does not support QUARTO_CACHE_DIR. Its native persistent
    # cache stays managed by Quarto; session files use this private directory.
    return dict(os.environ, TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp))
