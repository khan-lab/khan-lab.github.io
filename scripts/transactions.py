"""Validated, locked and reversible source writes shared by publication sync and the CLI."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
import shutil
import tempfile
from content import ContentError, validate

_HELD_LOCKS = ContextVar('researchlabfolio_locks', default=frozenset())


def scratch_directory(root=None):
    base = Path(root or Path.cwd()).resolve() / '.scratch/tmp'
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix='researchlabfolio-', dir=base)



def validate_changes(site, changes):
    """Validate an isolated candidate; never expose an invalid intermediate source."""
    with scratch_directory(site) as temp:
        candidate = Path(temp) / 'site'
        shutil.copytree(site, candidate, symlinks=True, ignore=shutil.ignore_patterns(
            '.scratch', '.pixi', '.git', '_site', '_generated', '__pycache__', '*.egg-info'))
        for relative, text in changes.items():
            if Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise ContentError(f'Unsafe content path: {relative}')
            path = candidate / relative
            if path.is_symlink() or not path.resolve().is_relative_to(candidate.resolve()):
                raise ContentError(f'Unsafe content path: {relative}')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        return validate(candidate)



@contextmanager
def site_lock(site):
    if site in _HELD_LOCKS.get():
        yield
        return
    base = site / '.scratch'
    base.mkdir(exist_ok=True)
    lock = base / 'cli.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ContentError(f'{lock}: another CLI edit is running. If it stopped, remove this lock directory and retry.') from None
    token = _HELD_LOCKS.set(_HELD_LOCKS.get() | {site})
    try:
        yield
    finally:
        _HELD_LOCKS.reset(token)
        lock.rmdir()



def commit_changes(site, changes, dry_run=False):
    """Serialize edits, validate all records, and roll back a partial multi-file write."""
    if dry_run:
        validate_changes(site, changes)
        return
    with site_lock(site):
        validate_changes(site, changes)
        before = {relative: (site / relative).read_bytes() if (site / relative).exists() else None for relative in changes}
        written = []
        with scratch_directory(site) as temp:
            try:
                for index, (relative, text) in enumerate(changes.items()):
                    target = site / relative
                    if target.is_symlink() or not target.resolve().is_relative_to(site):
                        raise ContentError(f'Cannot edit unsafe target {relative}')
                    pending = Path(temp) / str(index)
                    pending.write_text(text, encoding='utf-8')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        shutil.copymode(target, pending)
                    os.replace(pending, target)
                    written.append(relative)
            except BaseException:
                for relative in written:
                    target = site / relative
                    if before[relative] is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(before[relative])
                raise

