"""Run the independent CLI; prefer an explicit/sibling checkout for local development."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from content import ContentError

ROOT = Path(__file__).resolve().parents[1]


def invocation():
    env = dict(os.environ)
    source = Path(env['LABFOLIO_CLI_PATH']).expanduser().resolve() if env.get('LABFOLIO_CLI_PATH') else ROOT.parent / 'researchlabfolio-cli'
    explicit = bool(env.get('LABFOLIO_CLI_PATH'))
    source_root = source / 'src' if (source / 'src/researchlabfolio/cli.py').is_file() else source
    if explicit and not (source_root / 'researchlabfolio/cli.py').is_file():
        raise ContentError('LABFOLIO_CLI_PATH must point to the independent CLI checkout.')
    if (source_root / 'researchlabfolio/cli.py').is_file():
        env['PYTHONPATH'] = str(source_root) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    python = env.get('LABFOLIO_CLI_PYTHON')
    if python:
        return [python, '-m', 'researchlabfolio'], env
    if importlib.util.find_spec('researchlabfolio') is not None:
        return [sys.executable, '-m', 'researchlabfolio'], env
    executable = shutil.which('researchlabfolio') or shutil.which('rlf')
    if executable:
        return [executable], env
    raise ContentError('Install the independent CLI first. For sibling development: pixi run python -m pip install -e ../researchlabfolio-cli. You can also set LABFOLIO_CLI_PYTHON to its environment Python.')


if __name__ == '__main__':
    try:
        command, env = invocation()
        raise SystemExit(subprocess.call([*command, *sys.argv[1:]], env=env))
    except (ContentError, OSError) as exc:
        raise SystemExit(str(exc))
