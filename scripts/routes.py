"""Public routes independent of the editable authoring directory structure."""
from __future__ import annotations
import posixpath
from pathlib import Path
import json
import re
from urllib.parse import urlsplit, urlunsplit
import yaml
from content import ContentError, frontmatter


def main_page_url(value):
    """Map a local pages/name.qmd or .html reference, preserving its suffix."""
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return value
    path = re.sub(r'(^|/)pages/([a-z][a-z0-9-]*)\.(qmd|html)$',
                  lambda m: m[1] + ('join' if m[2] == 'opportunities' else m[2]) + ('/index.qmd' if m[3] == 'qmd' else '/'), parts.path)
    return urlunsplit(parts._replace(path=path))


def blog_page_url(value):
    """Keep authored blog paths separate from their public rendering paths."""
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return value
    path = re.sub(r'(^|/)content/blog/([^/]+)\.(qmd|html)$', r'\1blog/\2.\3', parts.path)
    return urlunsplit(parts._replace(path=path))


def main_page_links(text):
    # Match local reference prefixes only, never a path inside an external URL.
    text = re.sub(r'''(?<![\w./:-])(?:/|(?:\.\.?/)*)pages/[a-z][a-z0-9-]*\.(?:qmd|html)(?=[?#\s"'<>),\]}]|$)''',
                  lambda m: main_page_url(m[0]), text)
    return re.sub(r'''(?<![\w./:-])(?:/|(?:\.\.?/)*)content/blog/[a-z0-9_-]+\.(?:qmd|html)(?=[?#\s"'<>),\]}]|$)''',
                  lambda m: blog_page_url(m[0]), text)


def _rebase(value, old, new):
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not parts.path or parts.path.startswith('/'):
        return main_page_url(value)
    target = blog_page_url(main_page_url(posixpath.normpath(posixpath.join(old.parent.as_posix(), parts.path))))
    path = posixpath.relpath(target, new.parent.as_posix())
    if target.endswith('/'):
        path += '/'
    return urlunsplit(parts._replace(path=path))


def _body_links(text, old, new):
    text = re.sub(r'''\b(href|src|poster)=(['"])(.*?)\2''',
                  lambda m: m[1] + '=' + m[2] + _rebase(m[3], old, new) + m[2], text)
    return re.sub(r'(!?\[[^]\n]*\]\()([^\s)]+)([^)]*\))',
                  lambda m: m[1] + _rebase(m[2], old, new) + m[3], text)


def stage_main_pages(stage, config):
    """Relocate disposable page shells before native Quarto rendering."""
    pages = sorted((stage / 'pages').glob('*.qmd'))
    moved = {}
    for source in pages:
        old = source.relative_to(stage)
        new = Path(source.stem) / 'index.qmd'
        if (stage / new).exists():
            raise ContentError(f'Main page URL conflicts with existing source: {new}')
        metadata, body = frontmatter(source)
        if source.stem in config.get('_lab_toc', {}).get('pages', []) or 'toc' in metadata:
            formats = metadata.setdefault('format', {})
            if not isinstance(formats, dict):
                raise ContentError(f'{old}: contents navigation requires a format.html mapping.')
            html_format = formats.setdefault('html', {})
            if not isinstance(html_format, dict):
                raise ContentError(f'{old}: contents navigation requires a format.html mapping.')
            html_format.setdefault('toc', metadata.get('toc', True))
            html_format.setdefault('toc-depth', metadata.get('toc-depth', config.get('_lab_toc', {}).get('depth', 2)))
            html_format.setdefault('toc-location', metadata.get('toc-location', 'body'))
            if html_format['toc']:
                html_format['section-divs'] = False
                filters = metadata.setdefault('filters', [])
                if isinstance(filters, str): filters = metadata['filters'] = [filters]
                filters.append('../framework/filters/contents.lua')
        def rebase_metadata(value, key=''):
            if isinstance(value, dict):
                return {k: rebase_metadata(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [rebase_metadata(v, key) for v in value]
            if isinstance(value, str):
                if key in ('contents', 'template', 'filters', 'include-after-body', 'include-in-header', 'include-before-body'):
                    return _rebase(value, old, new)
                return _body_links(value, old, new)
            return value
        (stage / new).parent.mkdir(parents=True, exist_ok=True)
        (stage / new).write_text('---\n' + yaml.safe_dump(rebase_metadata(metadata), sort_keys=False, allow_unicode=True) + '---\n\n' + _body_links(body, old, new), encoding='utf-8')
        source.unlink()
        moved[old.as_posix()] = new.as_posix()
    # Generated includes resolve relative to their consuming document, not _generated/.
    for path in stage.rglob('*'):
        # Published blog bodies are rebased by Pandoc, which preserves literal
        # code and reference links; do not rewrite their Markdown as text.
        if path.parent == stage / 'blog' and path.name != 'index.qmd':
            continue
        if path.is_file() and (path.suffix == '.qmd' or path.parent == stage / '_generated' and path.suffix in ('.md', '.yml', '.json')):
            original = path.read_text(encoding='utf-8')
            updated = main_page_links(original)
            if updated != original:
                path.write_text(updated, encoding='utf-8')
    render = []
    for entry in config['project']['render']:
        if entry == 'pages/*.qmd':
            render.extend(moved.values())
        else:
            render.append('!' + main_page_url(entry[1:]) if entry.startswith('!') else main_page_url(entry))
    config['project']['render'] = render
    # Navbar/footer values can include complete HTML fragments.
    config = yaml.safe_load(main_page_links(yaml.safe_dump(config, sort_keys=False, allow_unicode=True)))
    config.pop('_lab_toc', None)
    return config


def finalize_main_page_urls(output, site_url):
    """Normalize native index.html links, including dynamic search and sitemap."""
    names = [p.name for p in output.iterdir() if p.is_dir() and (p / 'index.html').is_file()]
    site = urlsplit(site_url.rstrip('/') + '/')
    def clean(value):
        parts = urlsplit(value)
        path = parts.path
        if parts.scheme or parts.netloc:
            if (parts.scheme, parts.netloc) != (site.scheme, site.netloc) or not path.startswith(site.path):
                return value
            prefix, path = site.path, path[len(site.path):]
        else:
            prefix = ''
        if re.fullmatch(r'(?:/|(?:\.\.?/)*)index\.html', path):
            return urlunsplit(parts._replace(path=(prefix + path[:-len('index.html')]) or './'))
        for name in names:
            if re.fullmatch(r'(?:/|(?:\.\.?/)*)' + re.escape(name) + r'/index\.html', path):
                return urlunsplit(parts._replace(path=prefix + path[:-len('index.html')]))
        return value
    for path in output.rglob('*.html'):
        original = path.read_text(encoding='utf-8')
        updated = re.sub(r'''\b(href|content)=(['"])(.*?)\2''',
                         lambda m: m[1] + '=' + m[2] + clean(m[3]) + m[2], original)
        # Quarto 1.8.27 extracts a formatted citation from its bibliography list
        # but leaves role=listitem behind. A single attribution is not a list.
        updated = re.sub(r'<div\b[^>]*\bclass="[^"]*\bquarto-appendix-citeas\b[^"]*"[^>]*>',
                         lambda m: re.sub(r'\srole="listitem"', '', m[0]), updated)
        if updated != original:
            path.write_text(updated, encoding='utf-8')
    search = output / 'search.json'
    if search.exists():
        data = json.loads(search.read_text(encoding='utf-8'))
        for item in data:
            for key in ('href', 'objectID'):
                if key in item:
                    item[key] = clean(item[key])
        search.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sitemap = output / 'sitemap.xml'
    if sitemap.exists():
        sitemap.write_text(re.sub(r'<loc>([^<]+)</loc>', lambda m: '<loc>' + clean(m[1]) + '</loc>', sitemap.read_text(encoding='utf-8')), encoding='utf-8')
