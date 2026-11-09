"""Cross-platform Pixi task driver; all disposable staging is under .scratch."""
import argparse
import html
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
from content import ROOT, load, validate, ContentError
from prepare import prepare
from routes import main_page_url, blog_page_url, finalize_main_page_urls
from build_runtime import workspace, environment, quarto_command


def fingerprint(root):
    """Watch authored inputs only; generated output must not trigger rebuild loops."""
    paths = set()
    for base, names in ((ROOT, ('styles', 'framework', 'assets', 'pages', 'index.qmd', '_quarto.yml', 'CNAME')), (root, ('lab.yml', 'content', 'assets', 'pages', 'index.qmd', '_quarto.yml', 'CNAME'))):
        for name in names:
            path = base / name
            if path.is_file():
                paths.add(path)
            elif path.is_dir():
                paths.update(p for p in path.rglob('*') if p.is_file())
    return tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths))


def stop_preview(child):
    if os.name == 'nt':
        if child.poll() is None:
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Quarto's shell launcher starts Deno. Terminating only the launcher
        # leaves an orphan holding the preview port and old Sass cache open.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if child.poll() is None:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                child.kill()
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait()


def start_preview(command, env):
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    return subprocess.Popen(command, env=env, **options)


def preview(root, stage, env, port):
    state = fingerprint(root)
    # The driver watches authored inputs and restarts the complete process.
    # Quarto must not also re-render the generated tree during regeneration.
    command = quarto_command('preview', stage, '--no-browser', '--no-watch-inputs', '--port', port, env=env)
    child = start_preview(command, env)
    try:
        while child.poll() is None:
            time.sleep(.5)
            current = fingerprint(root)
            if current != state:
                state = current
                try:
                    validate(root)
                except ContentError as exc:
                    print(f'Preview retains last valid content: {exc}', flush=True)
                    continue
                stop_preview(child)
                prepare(root, stage)
                print('Authored sources changed; refreshing preview.', flush=True)
                child = start_preview(command, env)
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, command)
    except KeyboardInterrupt:
        print('Preview stopped.')
    finally:
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            stop_preview(child)
        finally:
            signal.signal(signal.SIGINT, previous)


def redirects(root, output, extra=None):
    mapping = {**(extra or {}), **load(root / 'redirects.yml', {})}
    for old, target in mapping.items():
        target = blog_page_url(main_page_url(target))
        oldpath = Path(old.lstrip('/'))
        if old.endswith('/'):
            oldpath /= 'index.html'
        if not oldpath.suffix:
            oldpath /= 'index.html'
        parts = urlsplit(target)
        if oldpath.is_absolute() or '..' in oldpath.parts or parts.scheme or parts.netloc or '..' in Path(parts.path).parts:
            raise ContentError(f'Unsafe redirect: {old} -> {target}')
        destination = output / oldpath
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        relative = os.path.relpath(output / parts.path.lstrip('/'), destination.parent).replace(os.sep, '/')
        if parts.path.endswith('/'):
            relative += '/'
        if parts.query:
            relative += '?' + parts.query
        if parts.fragment:
            relative += '#' + parts.fragment
        escaped = html.escape(relative, quote=True)
        script_target = json.dumps(relative).replace('<', '\\u003c')
        forward = f'<script>const target=new URL({script_target},location.href);if(location.search)target.search=location.search;if(location.hash)target.hash=location.hash;location.replace(target.href);</script>'
        destination.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Page moved</title>{forward}<meta http-equiv="refresh" content="0;url={escaped}"></head><body><main><h1>Page moved</h1><p><a href="{escaped}">Continue to this page</a></p></main></body></html>\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['check', 'build', 'preview', 'clean'])
    parser.add_argument('--site', type=Path, default=None)
    parser.add_argument('--port', type=int, default=5896)
    args = parser.parse_args()
    root = (args.site or ROOT).resolve()
    if args.task == 'clean':
        for path in (ROOT / '_site', ROOT / '_site-docs', ROOT / 'examples/cbcrg/_site', ROOT / '.scratch/builds', ROOT / '.scratch/tmp', ROOT / '.scratch/cache'):
            if path.exists():
                shutil.rmtree(path)
        print('Removed build artifacts; source downloads, logs, and screenshots retained.')
        return
    if args.task == 'check':
        sites = [root] if args.site else [ROOT] + ([ROOT / 'examples/cbcrg'] if (ROOT / 'examples/cbcrg/lab.yml').is_file() else [])
        for site in sites:
            cfg, data = validate(site)
            print(f'{cfg["lab"]["name"]}: ' + ', '.join(f'{len(v)} {k}' for k,v in data.items()))
        return
    work = workspace(('generic' if root == ROOT else root.name) + '-' + args.task)
    stage = prepare(root, work / 'source')
    env = environment(work)
    if args.task == 'preview':
        preview(root, stage, env, args.port)
        return
    subprocess.run(quarto_command('render', stage, env=env), env=env, check=True)
    rendered = stage / '_site'
    finalize_main_page_urls(rendered, load(stage / '_quarto.yml')['website']['site-url'])
    (rendered / '.nojekyll').touch()
    redirects(root, rendered)
    # Audit before replacing a prior successful artifact.
    subprocess.run([sys.executable, str(Path(__file__).with_name('audit.py')), str(rendered)], check=True)
    output = root / '_site'
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(rendered, output)
    print(f'Built {output}')

if __name__ == '__main__':
    try:
        main()
    except (ContentError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
