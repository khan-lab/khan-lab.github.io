"""Private workspaces for render and preview processes; authored files stay separate."""
import os
from pathlib import Path
import re
import shutil
import tempfile
from content import ROOT, ContentError


def quarto_command(*arguments, env=None):
    # Windows CreateProcess does not apply PATHEXT to a bare "quarto".
    # Resolve its .cmd/.bat launcher using the same PATH as the child process.
    path = env.get('PATH', os.defpath) if env is not None else None
    executable = shutil.which('quarto', path=path)
    if not executable:
        raise ContentError('Quarto was not found on PATH. Run pixi install --locked, then pixi run build or pixi run preview; with the installed CLI, run rlf tools first.')
    return [executable, *(str(argument) for argument in arguments)]


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
