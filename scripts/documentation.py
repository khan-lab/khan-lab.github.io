"""Build the public documentation and nested demos without altering lab sources."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
import yaml
from content import ROOT, ContentError, load
from prepare import prepare
from run import redirects
from audit import audit
from routes import finalize_main_page_urls
from build_runtime import workspace, environment as render_environment, quarto_command
from cli_bridge import invocation

PUBLIC_URL = 'https://khan-lab.github.io/researchlabfolio/'
REFERENCE_SLUGS = ('distribution', 'smart-import', 'upgrading', 'cli', 'schema',
                   'batch-import', 'community-map', 'migration', 'publications',
                   'blog', 'teaching', 'cms', 'testing')
PALETTES = {
    'forest': ('#176B63', '#596779'), 'ocean': ('#2B94C8', '#596779'),
    'plum': ('#744477', '#596779'), 'terracotta': ('#A64B32', '#596779'),
}


def site_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or re.search(r'[\s<>"\x00-\x1f]', value):
        raise ContentError('Documentation site URL must be a credential-free HTTPS URL without query or fragment.')
    if any(part in ('.', '..') for part in parsed.path.split('/')):
        raise ContentError('Documentation site URL cannot contain dot path segments.')
    return value.rstrip('/') + '/'


def environment():
    return dict(render_environment(workspace('documentation-runtime')), NO_COLOR='1', TERM='dumb')


def checked(output):
    count, errors = audit(output)
    print(f'{output}: {count} HTML pages, {len(errors)} issues', flush=True)
    if errors:
        raise ContentError('\n'.join(errors))


def lab_build(source, key, url, docs_url, palette=None):
    workspace = ROOT / '.scratch/builds/public-demos' / key
    if workspace.exists(): shutil.rmtree(workspace)
    authored = workspace / 'input'; authored.mkdir(parents=True)
    for name in ('lab.yml', 'content', 'pages', 'assets', '_quarto.yml', 'index.qmd', 'redirects.yml'):
        origin = source / name
        if origin.is_dir(): shutil.copytree(origin, authored / name)
        elif origin.is_file(): shutil.copy2(origin, authored / name)
    cfg = load(authored / 'lab.yml')
    cfg['lab']['site_url'] = url
    cfg.setdefault('footer', {})['documentation_url'] = docs_url
    if palette:
        cfg['branding']['colors'] = dict(zip(('primary', 'secondary'), PALETTES[palette]))
    (authored / 'lab.yml').write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    stage = prepare(authored, workspace / 'source')
    env = environment()
    subprocess.run(quarto_command('render', stage, env=env), env=env, check=True)
    output = stage / '_site'; (output / '.nojekyll').touch()
    finalize_main_page_urls(output, url)
    redirects(authored, output)
    checked(output)
    return output


def stage_docs(url):
    stage = ROOT / '.scratch/builds/documentation/source'
    if stage.exists(): shutil.rmtree(stage)
    shutil.copytree(ROOT / 'documentation', stage)
    shutil.copytree(ROOT / 'assets/fonts', stage / 'assets/fonts', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'documentation/examples/import', stage / 'assets/downloads/import', dirs_exist_ok=True)
    shutil.make_archive(str(stage / 'assets/downloads/import/smart-hugo'), 'zip', ROOT / 'documentation/examples/import/smart-hugo')
    reference = stage / 'reference'; reference.mkdir(exist_ok=True)
    missing = [slug for slug in REFERENCE_SLUGS if not (reference / (slug + '.qmd')).is_file()]
    if missing: raise ContentError('Missing authored documentation reference: ' + ', '.join(missing))
    commands = [[], ['init'], ['config'], ['config','set'], ['add'], ['add','member'], ['add','blog'], ['add','publication'], ['import'], ['ai'], ['ai','configure'], ['ai','models'], ['ai','test'], ['export'], ['github'], ['github','setup'], ['github','publish'], ['upgrade'], ['doctor'], ['publications'], ['publications','check'], ['publications','sync']]
    help_page = '---\ntitle: Command reference\n---\n\nGenerated from this version of the CLI. `rlf` and `researchlabfolio` are aliases. From a checkout, prefix commands with `pixi run`.\n\n'
    cli_command, cli_environment = invocation()
    for command in commands:
        result = subprocess.run([*cli_command, *command, '--help'], cwd=ROOT, env={**cli_environment, **environment(), 'PYTHONPATH': cli_environment.get('PYTHONPATH', ''), 'COLUMNS': '100'}, capture_output=True, text=True, check=True)
        help_page += '## rlf' + (' ' + ' '.join(command) if command else '') + '\n\n```text\n' + result.stdout.strip() + '\n```\n\n'
    (reference / 'commands.qmd').write_text(help_page)
    for name, colors in PALETTES.items():
        path = stage / 'assets/gallery' / (name + '.yml'); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({'branding':{'colors':dict(zip(('primary','secondary'), colors))}}, sort_keys=False))
    cfg = load(stage / '_quarto.yml'); cfg['website']['site-url'] = url
    (stage / '_quarto.yml').write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    return stage


def render_portal(url, built):
    docs = stage_docs(url)
    env = environment()
    subprocess.run(quarto_command('render', docs, env=env), env=env, check=True)
    output = docs / '_site'
    for destination, source in built:
        shutil.copytree(source, output / destination, dirs_exist_ok=True)
    (output / '.nojekyll').touch()
    # A composite search index includes the documentation only. Each demo retains its own.
    checked(output)
    destination = ROOT / '_site-docs'
    if destination.exists(): shutil.rmtree(destination)
    shutil.copytree(output, destination)
    print(f'Built documentation and demos: {destination}', flush=True)


def build(url):
    demos = [('demo', ROOT, 'demo/'), ('cbcrg', ROOT / 'examples/cbcrg', 'examples/cbcrg/')]
    built = [(destination, lab_build(source, key, url + destination, url)) for key, source, destination in demos]
    render_portal(url, built)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['build', 'gallery-sites'])
    parser.add_argument('--site-url', default=PUBLIC_URL)
    args = parser.parse_args(); url = site_url(args.site_url)
    if args.task == 'build': build(url)
    else:
        for name in PALETTES:
            source = ROOT / 'examples/cbcrg' if name == 'ocean' else ROOT
            output = lab_build(source, 'gallery-' + name, url + 'demo/', url, name)
            print(f'Gallery {name}: {output}', flush=True)


if __name__ == '__main__':
    try: main()
    except (ContentError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
