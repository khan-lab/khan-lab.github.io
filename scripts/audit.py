"""Offline rendered-site checks: local links/anchors/assets and semantic basics."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.theme_styles = {}
        self.refs = []
        self.errors = []
        self.h1 = 0
        self.main = 0
        self.lang = False
        self.title = False
    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        if a.get('id'):
            classes = frozenset(a.get('class', '').split())
            path = Path(urlsplit(a.get('href', '')).path)
            native_theme = tag == 'link' and a.get('rel') == 'stylesheet' and classes in (
                frozenset({'quarto-color-scheme'}),
                frozenset({'quarto-color-scheme', 'quarto-color-alternate'}),
                frozenset({'quarto-color-scheme-extra'}),
            ) and ((a['id'] == 'quarto-bootstrap' and path.parent.name == 'bootstrap' and path.name.startswith('bootstrap-') and path.suffix == '.css') or
                   (a['id'] == 'quarto-text-highlighting-styles' and path.parent.name == 'quarto-html' and path.name.startswith('quarto-syntax-highlighting-') and path.suffix == '.css'))
            if a['id'] in self.ids:
                # Quarto's native theme switch intentionally shares these IDs
                # across primary/alternate/fallback CSS; all other IDs stay unique.
                if not native_theme or a['id'] not in self.theme_styles or classes in self.theme_styles[a['id']]:
                    self.errors.append(f'duplicate HTML id {a["id"]}')
            if native_theme:
                self.theme_styles.setdefault(a['id'], set()).add(classes)
            self.ids.add(a['id'])
        if tag == 'html':
            self.lang = bool(a.get('lang'))
        if tag == 'title':
            self.title = True
        if tag == 'h1':
            self.h1 += 1
        if tag == 'main':
            self.main += 1
        if tag == 'img' and 'alt' not in a:
            self.errors.append('image missing alt')
        for key in ('href', 'src', 'poster'):
            if a.get(key):
                self.refs.append(a[key])


def audit(root):
    root = Path(root).resolve()
    pages = {}
    errors = []
    for path in root.rglob('*.html'):
        parser = Page()
        parser.feed(path.read_text(encoding='utf-8'))
        pages[path] = parser
        for error in parser.errors:
            errors.append(f'{path.relative_to(root)}: {error}')
        if not parser.lang or not parser.title or parser.h1 != 1 or parser.main != 1:
            errors.append(f'{path.relative_to(root)}: needs lang, title, exactly one h1/main (h1={parser.h1}, main={parser.main})')
    if not pages:
        errors.append(f'{root}: no rendered HTML pages')
    for path, parser in pages.items():
        for ref in parser.refs:
            parts = urlsplit(ref)
            if parts.scheme or parts.netloc or ref.startswith('data:'):
                continue
            target = root / unquote(parts.path).lstrip('/') if parts.path.startswith('/') else path.parent / unquote(parts.path)
            target = target.resolve() if parts.path else path
            if target.is_dir():
                target /= 'index.html'
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f'{path.relative_to(root)}: broken local link {ref}')
            elif parts.fragment and target.suffix == '.html' and target in pages and unquote(parts.fragment) not in pages[target].ids:
                errors.append(f'{path.relative_to(root)}: missing anchor {ref}')
    return len(pages), sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sites', nargs='+', type=Path)
    args = parser.parse_args()
    errors = []
    for root in args.sites:
        count, issues = audit(root)
        print(f'{root}: {count} HTML pages, {len(issues)} issues')
        errors.extend(issues)
    if errors:
        print('\n'.join(errors))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
