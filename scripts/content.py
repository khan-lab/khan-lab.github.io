"""Hand-editable content contracts. No network access during validation/rendering."""
from __future__ import annotations
import datetime as dt
import re
import os
from pathlib import Path
from urllib.parse import urlsplit
import yaml

ROOT = Path(os.environ.get('RESEARCHLABFOLIO_ENGINE_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
ROLES = ('pi', 'postdoc', 'staff', 'phd', 'masters', 'undergraduate', 'visitor', 'alumni')
TYPES = ('software', 'database', 'dataset', 'protocol', 'education')
NAV = {'research', 'people', 'publications', 'software', 'news', 'blog', 'teaching', 'join', 'contact'}
FONTS = {'Source Serif 4', 'Source Sans 3', 'Georgia', 'Arial', 'system-ui'}

class ContentError(ValueError):
    pass

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    pairs = loader.construct_pairs(node, deep=deep)
    result = {}
    for (key, value), (_, value_node) in zip(pairs, node.value):
        # YAML 1.1 treats NO as false. Only declared country fields use ISO
        # semantics; never change boolean consent/settings or mutate alias nodes.
        def country_value(child):
            if child.tag == 'tag:yaml.org,2002:bool' and child.value.casefold() == 'no':
                return 'NO'
            return loader.construct_object(child, deep=True)
        if key == 'country' and value_node.tag == 'tag:yaml.org,2002:bool' and value_node.value.casefold() == 'no':
            value = 'NO'
        elif key == 'countries' and isinstance(value_node, yaml.SequenceNode):
            value = [country_value(child) for child in value_node.value]
        if key in result:
            raise ContentError(f'duplicate YAML key {key!r}, line {node.start_mark.line + 1}')
        result[key] = value
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

def load(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise ContentError(f'{path}: file is required')
    try:
        data = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise ContentError(f'{path}: {exc}') from exc
    return data if data is not None else default

def require(condition, where, message):
    if not condition:
        raise ContentError(f'{where}: {message}')

def text_fields(item, fields, where):
    require(isinstance(item, dict), where, 'expected a mapping')
    for field in fields:
        require(isinstance(item.get(field), str) and bool(item[field].strip()), where, f'{field} must be nonempty text')

def url(value, where):
    require(isinstance(value, str), where, 'URL must be text')
    parsed = urlsplit(value)
    require(parsed.scheme in ('https', 'http') and bool(parsed.netloc) and not re.search(r'[\s<>"\x00-\x1f]', value), where, f'invalid HTTP(S) URL {value!r}')

def email(value, where):
    require(isinstance(value, str) and re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value), where, 'invalid email address')

def orcid_valid(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', value):
        return False
    digits = value.replace('-', '')
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ('X' if check == 10 else str(check))

def normalize_doi(value):
    value = str(value or '').strip()
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value, flags=re.I).lower()

def author_key(value):
    """Normalize explicitly approved author spellings; never guess initials/surnames."""
    return ' '.join(value.casefold().split())

def luminance(color):
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return sum(c * weight for c, weight in zip([v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb], (.2126, .7152, .0722)))

def contrast(a, b):
    x, y = sorted((luminance(a), luminance(b)))
    return (y+.05)/(x+.05)

def accent_text(color):
    """Keep the brand exact; derive readable text for the light page surfaces."""
    if contrast(color, '#FAFAF8') >= 5:
        return color
    rgb = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    for step in range(1, 101):
        candidate = '#' + ''.join(f'{round(value * (1-step/100)):02X}' for value in rgb)
        if contrast(candidate, '#FAFAF8') >= 5:
            return candidate
    return '#000000'

def on_accent(color):
    """Select a readable label color for a solid brand-color control."""
    for foreground in ('#FAFAF8', '#202524', '#000000'):
        if contrast(foreground, color) >= 4.5:
            return foreground
    return '#000000'

def accent_text_dark(color):
    """Derive readable links/focus against the lightest dark-mode surface."""
    background = '#293337'
    if contrast(color, background) >= 5:
        return color
    rgb = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    for step in range(1, 101):
        candidate = '#' + ''.join(f'{round(value + (255-value)*step/100):02X}' for value in rgb)
        if contrast(candidate, background) >= 5:
            return candidate
    return '#FFFFFF'

def asset(root, value, where):
    require(isinstance(value, str), where, 'asset path must be text')
    path = (root / value).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), where, f'missing or unsafe local asset {value!r}')

def frontmatter(path):
    text = path.read_text(encoding='utf-8')
    require(text.startswith('---\n') and '\n---' in text[4:], path, 'YAML front matter required')
    head, body = text[4:].split('\n---', 1)
    try:
        data = yaml.load(head, Loader=UniqueLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise ContentError(f'{path}: invalid YAML or ISO date: {exc}') from exc
    require(isinstance(data, dict), path, 'front matter must be a mapping')
    return data, body.lstrip('\n')

def records(path):
    data = load(path, [])
    require(isinstance(data, list), path, 'expected a list of records')
    return data

def identify(items, where):
    seen = set()
    for item in items:
        text_fields(item, ['id'], where)
        key = item['id']
        require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key)), where, f'invalid stable id {key!r}')
        require(key not in seen, where, f'duplicate ID {key}')
        seen.add(key)
    return seen

def publication_records(root):
    folder = root / 'content/publications'
    manual = records(folder / 'manual.yml')
    cached = records(folder / 'cache.yml')
    for name, items in (('manual.yml', manual), ('cache.yml', cached)):
        identify(items, folder / name)
        seen = set()
        for item in items:
            doi = normalize_doi(item.get('doi'))
            if doi:
                require(doi not in seen, folder / name, f'duplicate normalized DOI {doi}')
                seen.add(doi)
    rules = load(folder / 'overrides.yml', {'include': [], 'exclude': [], 'overrides': {}})
    require(isinstance(rules, dict), folder, 'overrides must be a mapping')
    for key in ('include', 'exclude'):
        require(isinstance(rules.get(key, []), list) and all(isinstance(v, str) for v in rules.get(key, [])), folder, f'{key} must be a list of IDs or DOIs')
    changes = rules.get('overrides', {})
    require(isinstance(changes, dict) and all(isinstance(v, dict) for v in changes.values()), folder, 'overrides must map IDs or DOIs to records')
    def keys(p):
        return {p['id'], normalize_doi(p.get('doi'))} - {''}
    def matches(p, rule):
        return bool(keys(p) & {str(v) if not normalize_doi(v).startswith('10.') else normalize_doi(v) for v in rule})
    # Manual entries replace cached versions by stable ID or normalized DOI, deliberately.
    all_records = []
    for p in cached:
        if not any(keys(p) & keys(m) for m in manual):
            all_records.append(dict(p))
    all_records.extend(dict(p) for p in manual)
    known = set().union(*(keys(p) for p in all_records)) if all_records else set()
    for rule in [*rules.get('include', []), *changes.keys()]:
        require(rule in known or normalize_doi(rule) in known, folder, f'curation references unknown publication {rule!r}')
    for p in all_records:
        for key, patch in changes.items():
            if matches(p, [key]):
                require(not ({'id', 'doi'} & set(patch)), folder, 'overrides cannot change stable ID or DOI')
                p.update(patch)
        if matches(p, rules.get('exclude', [])):
            p['status'] = 'excluded'
        elif matches(p, rules.get('include', [])):
            p['status'] = 'confirmed'
    return all_records

def validate(root=ROOT):
    root = Path(root).resolve()
    cfg = load(root / 'lab.yml')
    text_fields(cfg, [], 'lab.yml')
    lab = cfg.get('lab', {})
    text_fields(lab, ['name', 'tagline', 'description', 'institution', 'email'], 'lab.yml lab')
    if 'recruitment_heading' in lab:
        text_fields(lab, ['recruitment_heading'], 'lab')
    for key in ('mission', 'vision'):
        require(isinstance(lab.get(key, ''), str), 'lab.' + key, 'must be plain text')
    quote = lab.get('quote', {})
    require(isinstance(quote, dict) and set(quote) <= {'text', 'author'}, 'lab.quote', 'expected text and author fields')
    for key in ('text', 'author'):
        require(isinstance(quote.get(key, ''), str), 'lab.quote.' + key, 'must be plain text')
    require(bool(quote.get('text', '').strip()) == bool(quote.get('author', '').strip()), 'lab.quote', 'provide both text and author, or leave both blank')
    if 'department' in lab:
        require(isinstance(lab['department'], str), 'lab.department', 'must be text')
    email(lab['email'], 'lab.yml lab.email')
    if lab.get('site_url'):
        url(lab['site_url'], 'lab.site_url')
        require(not urlsplit(lab['site_url']).query and not urlsplit(lab['site_url']).fragment, 'lab.site_url', 'must be a base URL without query/fragment')
    branding = cfg.get('branding', {})
    require(isinstance(branding, dict), 'branding', 'expected mapping')
    for key in ('colors', 'fonts'):
        require(isinstance(branding.get(key), dict), f'branding.{key}', 'expected mapping')
    for key in ('primary', 'secondary'):
        color = branding.get('colors', {}).get(key)
        require(isinstance(color, str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}', color)), 'branding.colors', f'invalid {key} hex color')
    for key in ('body', 'headings'):
        require(branding.get('fonts', {}).get(key) in FONTS, 'branding.fonts', f'{key} must use one of {sorted(FONTS)}')
    for key in ('logo', 'favicon'):
        if branding.get(key):
            asset(root, branding[key], f'branding.{key}')
    people_options = cfg.get('people', {})
    require(isinstance(people_options, dict), 'people', 'expected mapping')
    require(isinstance(people_options.get('show_education', False), bool), 'people.show_education', 'must be boolean')
    from community_map import validate_options, normalize_countries
    validate_options(people_options.get('global_map', {}))
    photos = people_options.get('photos', {})
    require(isinstance(photos, dict), 'people.photos', 'expected mapping')
    require(set(photos) <= {'grayscale', 'blur', 'reveal_on_hover'}, 'people.photos', 'unknown photo option')
    for key in ('grayscale', 'reveal_on_hover'):
        require(isinstance(photos.get(key, True), bool), 'people.photos.' + key, 'must be boolean')
    blur = photos.get('blur', 0)
    require(type(blur) in (int, float) and 0 <= blur <= 10, 'people.photos.blur', 'must be a number from 0 to 10 (pixels)')
    alumni_options = people_options.get('alumni', {})
    require(isinstance(alumni_options, dict), 'people.alumni', 'expected mapping')
    require(set(alumni_options) <= {'show_photos', 'link_profiles'}, 'people.alumni', 'unknown alumni option')
    for key, default in (('show_photos', True), ('link_profiles', False)):
        require(isinstance(alumni_options.get(key, default), bool), 'people.alumni.' + key, 'must be boolean')
    resources = cfg.get('resources', {})
    provenance = cfg.get('provenance', {})
    require(isinstance(provenance, dict), 'provenance', 'expected mapping')
    require(isinstance(provenance.get('show_links', True), bool), 'provenance.show_links', 'must be boolean')
    require(isinstance(resources, dict), 'resources', 'expected mapping')
    require(isinstance(resources.get('search', True), bool), 'resources.search', 'must be boolean')
    footer = cfg.get('footer', {})
    require(isinstance(footer, dict), 'footer', 'expected mapping')
    require(isinstance(footer.get('pi_links', False), bool), 'footer.pi_links', 'must be boolean')
    require(isinstance(footer.get('show_logo', False), bool), 'footer.show_logo', 'must be boolean')
    require(isinstance(footer.get('show_email', True), bool), 'footer.show_email', 'must be boolean')
    require(not footer.get('show_logo', False) or bool(cfg['branding'].get('logo')), 'footer.show_logo', 'requires a configured branding.logo')
    for key in ('source_url', 'documentation_url'):
        if footer.get(key) is not None:
            require(isinstance(footer[key], str), 'footer.' + key, 'must be HTTP(S) URL text')
        if footer.get(key):
            url(footer[key], 'footer.' + key)
    logos = footer.get('logos', [])
    require(isinstance(logos, list), 'footer.logos', 'expected list')
    for index, logo in enumerate(logos):
        where = f'footer.logos[{index}]'
        text_fields(logo, ['src', 'alt'], where)
        asset(root, logo['src'], where + '.src')
        if logo.get('url') is not None:
            require(isinstance(logo['url'], str), where + '.url', 'must be HTTP(S) URL text')
        if logo.get('url'):
            url(logo['url'], where + '.url')
    nav = cfg.get('navigation', sorted(NAV))
    if isinstance(nav, list):
        nav = ['join' if value == 'opportunities' else value for value in nav]
        cfg['navigation'] = nav
    require(isinstance(nav, list) and all(isinstance(v, str) for v in nav) and len(nav) == len(set(nav)) and set(nav) <= NAV, 'navigation', f'expected unique section names in {sorted(NAV)}')
    blog = cfg.get('blog', {})
    require(isinstance(blog, dict) and set(blog) <= {'enabled', 'cite'}, 'blog', 'expected enabled and/or cite flags')
    for key, default in (('enabled', False), ('cite', True)):
        require(isinstance(blog.get(key, default), bool), 'blog.' + key, 'must be boolean')
    toc = cfg.get('toc', {})
    require(isinstance(toc, dict) and set(toc) <= {'pages', 'blog', 'depth'}, 'toc', 'expected pages, blog and/or depth')
    require(isinstance(toc.get('blog', False), bool), 'toc.blog', 'must be boolean')
    require(type(toc.get('depth', 2)) is int and 1 <= toc.get('depth', 2) <= 6, 'toc.depth', 'must be an integer in 1..6')
    toc_pages = toc.get('pages', [])
    require(isinstance(toc_pages, list) and all(isinstance(value, str) and value in {'research', 'teaching', 'join', 'contact', 'template'} for value in toc_pages)
            and len(toc_pages) == len(set(toc_pages)), 'toc.pages', 'expected unique main section names')
    teaching = cfg.get('teaching', {})
    require(isinstance(teaching, dict) and set(teaching) <= {'enabled', 'profile_courses', 'search'}, 'teaching', 'expected enabled, profile_courses and/or search flags')
    for key in ('enabled', 'profile_courses', 'search'):
        require(isinstance(teaching.get(key, key != 'enabled'), bool), 'teaching.' + key, 'must be boolean')
    home = cfg.get('homepage', {})
    require(isinstance(home, dict) and set(home) <= {'research', 'people', 'publications', 'software', 'news', 'recruitment', 'mission', 'vision', 'quote'} and all(isinstance(v, bool) for v in home.values()), 'homepage', 'expected section boolean flags')
    recruitment = cfg.get('recruitment', {})
    require(isinstance(recruitment, dict) and set(recruitment) <= {'image', 'image_alt', 'slides', 'photos'}, 'recruitment', 'expected image, image_alt, slides and/or photos fields')
    for key in ('image', 'image_alt'):
        require(isinstance(recruitment.get(key, ''), str), 'recruitment.' + key, 'must be text')
    if recruitment.get('image'):
        asset(root, recruitment['image'], 'recruitment.image')
        text_fields(recruitment, ['image_alt'], 'recruitment')
    slides = recruitment.get('slides', [])
    require(isinstance(slides, list), 'recruitment.slides', 'expected a list of photos')
    require(not (slides and recruitment.get('image')), 'recruitment', 'use slides or image, not both')
    for index, slide in enumerate(slides):
        where = f'recruitment.slides[{index}]'
        require(isinstance(slide, dict) and set(slide) <= {'image', 'image_alt', 'caption'}, where, 'expected image, image_alt and optional caption')
        text_fields(slide, ['image', 'image_alt'], where)
        asset(root, slide['image'], where + '.image')
        require(isinstance(slide.get('caption', ''), str), where + '.caption', 'must be text')
    photos = recruitment.get('photos', {})
    require(isinstance(photos, dict) and set(photos) <= {'grayscale', 'blur', 'reveal_on_hover'}, 'recruitment.photos', 'expected grayscale, blur and/or reveal_on_hover')
    for key, default in (('grayscale', False), ('reveal_on_hover', True)):
        require(isinstance(photos.get(key, default), bool), 'recruitment.photos.' + key, 'must be boolean')
    blur = photos.get('blur', 0)
    require(type(blur) in (int, float) and 0 <= blur <= 10, 'recruitment.photos.blur', 'must be a number from 0 to 10 (pixels)')
    hero = cfg.get('hero', {})
    require(isinstance(hero, dict), 'hero', 'expected mapping')
    require(set(hero) <= {'overview', 'image', 'image_alt', 'image_caption', 'metrics', 'actions', 'font_sizes'}, 'hero', 'unknown hero option')
    font_sizes = hero.get('font_sizes', {})
    require(isinstance(font_sizes, dict), 'hero.font_sizes', 'expected a mapping of font sizes in rem')
    require(set(font_sizes) <= {'lab_name', 'heading', 'description', 'lab_name_mobile', 'heading_mobile', 'description_mobile'}, 'hero.font_sizes', 'unknown font-size option')
    for key, value in font_sizes.items():
        require(type(value) in (int, float) and .5 <= value <= 8, 'hero.font_sizes.' + key, 'must be a number from 0.5 to 8 (rem)')
    require(isinstance(hero.get('overview', False), bool), 'hero.overview', 'must be boolean')
    for key in ('image', 'image_alt', 'image_caption'):
        require(isinstance(hero.get(key, ''), str), 'hero.' + key, 'must be text')
    if hero.get('image'):
        asset(root, hero['image'], 'hero.image')
        text_fields(hero, ['image_alt'], 'hero')
    metrics = hero.get('metrics', [])
    require(isinstance(metrics, list) and len(metrics) <= 4, 'hero.metrics', 'expected up to four explicitly curated metrics')
    for index, metric in enumerate(metrics):
        text_fields(metric, ['value', 'label'], f'hero.metrics[{index}]')
        if metric.get('url'):
            url(metric['url'], f'hero.metrics[{index}].url')
    if 'actions' in hero:
        require(isinstance(hero['actions'], list) and len(hero['actions']) <= 2, 'hero.actions', 'expected up to two actions')
        for index, action in enumerate(hero['actions']):
            text_fields(action, ['label', 'section'], f'hero.actions[{index}]')
            if action['section'] == 'opportunities':
                action['section'] = 'join'
            require(action['section'] in NAV, f'hero.actions[{index}].section', 'must name an existing website section')
            require(action['section'] != 'blog' or blog.get('enabled', False), f'hero.actions[{index}].section', 'Blog is disabled; enable blog.enabled first')
            require(action['section'] != 'teaching' or teaching.get('enabled', False), f'hero.actions[{index}].section', 'Teaching is disabled; enable teaching.enabled first')
    research = cfg.get('research', {})
    require(isinstance(research, dict), 'research config', 'expected mapping')
    require(isinstance(research.get('detail_pages', False), bool), 'research.detail_pages', 'must be boolean')
    require(isinstance(research.get('summary_figure', False), bool), 'research.summary_figure', 'must be boolean')
    if research.get('summary_figure', False):
        require(bool(hero.get('image')), 'research.summary_figure', 'requires hero.image and hero.image_alt')
    if 'summary' in research:
        text_fields(research, ['summary'], 'research config')
    newsconfig = cfg.get('news', {})
    require(isinstance(newsconfig, dict), 'news config', 'expected mapping')
    require(isinstance(newsconfig.get('detail_pages', False), bool), 'news.detail_pages', 'must be boolean')
    pubconfig = cfg.get('publications', {})
    require(isinstance(pubconfig, dict), 'publications config', 'expected mapping')
    require(isinstance(pubconfig.get('altmetric', False), bool), 'publications.altmetric', 'must be boolean')
    require(isinstance(pubconfig.get('highlight_authors', True), bool), 'publications.highlight_authors', 'must be boolean')
    for key in ('orcid', 'openalex'):
        value = pubconfig.get(key, '')
        require(not value or (orcid_valid(value) if key == 'orcid' else bool(re.fullmatch(r'A\d+', str(value)))), f'publications.{key}', 'invalid researcher identifier')
    people = records(root / 'content/people/people.yml')
    software = records(root / 'content/software/software.yml')
    publications = publication_records(root)
    projects, news = [], []
    for category, target in (('research', projects), ('news', news)):
        for path in sorted((root / 'content' / category).glob('*.qmd')):
            item, body = frontmatter(path)
            item = dict(item, body=body, path=path.relative_to(root).as_posix())
            text_fields(item, ['id', 'title', 'description'], path)
            if category == 'research':
                require(isinstance(item.get('detail_page', research.get('detail_pages', False)), bool), path, 'detail_page must be boolean')
                item['detail_page'] = item.get('detail_page', research.get('detail_pages', False))
            if category == 'news':
                require(isinstance(item.get('detail_page', newsconfig.get('detail_pages', False)), bool), path, 'detail_page must be boolean')
                item['detail_page'] = item.get('detail_page', newsconfig.get('detail_pages', False))
                try:
                    dt.date.fromisoformat(str(item.get('date', '')))
                except ValueError as exc:
                    raise ContentError(f'{path}: date must be ISO YYYY-MM-DD') from exc
                require(isinstance(item.get('categories'), list) and bool(item['categories']), path, 'categories must be a nonempty list')
            target.append(item)
    from blog import read_posts
    from teaching import read_courses
    posts = read_posts(root, people)
    data = {'people': people, 'software': software, 'publications': publications, 'projects': projects, 'news': news, 'blog': posts, 'teaching': read_courses(root, people)}
    ids = {name: identify(items, name) for name, items in data.items()}
    for name, items in data.items():
        for item in items:
            where = f'{name}/{item["id"]}'
            for key in ('interests', 'collaborators', 'funders'):
                if key in item:
                    require(isinstance(item[key], list) and all(isinstance(v, str) and v.strip() for v in item[key]), where, f'{key} must be a list of nonempty text values')
            for target in ('people', 'projects', 'software', 'publications'):
                refs = item.get(target, [])
                require(isinstance(refs, list) and all(isinstance(v, str) for v in refs), where, f'{target} must be a list of IDs')
                require(set(refs) <= ids[target], where, f'unresolved {target} references: {set(refs) - ids[target]}')
            for key in ('url', 'website', 'repo', 'pdf', 'preprint', 'code', 'data', 'source_url'):
                if name == 'teaching' and key == 'code':
                    continue  # Course codes are text; publication code fields are URLs.
                if item.get(key):
                    url(item[key], f'{where}.{key}')
            for key in ('photo', 'image'):
                if item.get(key):
                    asset(root, item[key], where)
                    require(bool(item.get('image_alt') or item.get('name')), where, 'image needs image_alt')
            links = item.get('links', {})
            require(isinstance(links, dict), where, 'links must map labels to HTTP(S) URLs')
            for label, value in links.items():
                require(isinstance(label, str) and bool(label.strip()), where, 'link labels must be nonempty text')
                url(value, f'{where}.links.{label}')
            if 'featured' in item:
                require(isinstance(item['featured'], bool), where, 'featured must be boolean')
    publication_aliases = {}
    for person in people:
        where = f'people/{person["id"]}'
        text_fields(person, ['name', 'role'], where)
        normalize_countries(person, where)
        aliases = person.get('publication_names', [])
        exclusions = person.get('exclude_publications', [])
        require(isinstance(exclusions, list) and all(isinstance(v, str) for v in exclusions), where, 'exclude_publications must be a list of publication IDs')
        require(set(exclusions) <= ids['publications'], where, 'exclude_publications contains unknown publication IDs')
        require(isinstance(aliases, list) and all(isinstance(value, str) and value.strip() for value in aliases), where + '.publication_names', 'expected a list of approved author names')
        for alias in aliases:
            key = author_key(alias)
            require(key not in publication_aliases, where + '.publication_names', f'author alias {alias!r} already assigned to {publication_aliases.get(key)}')
            publication_aliases[key] = person['id']
        # Backwards compatible starter: group is enum, role is display title.
        require(person.get('group', person['role']) in ROLES, where, f'role/group must be one of {ROLES}')
        for field in ('education', 'next_position', 'destination'):
            if person.get(field) is not None:
                require(isinstance(person[field], str), where + '.' + field, 'must be plain text')
        if 'destination' in person:
            if 'next_position' in person:
                require((person['next_position'] or '').strip() == (person['destination'] or '').strip(), where + '.next_position', 'conflicts with legacy destination; keep one next_position value')
            else:
                person['next_position'] = person['destination']
            del person['destination']  # Canonical in-memory field; authored files stay untouched.
        if person.get('years') is not None:
            require(isinstance(person['years'], str), where + '.years', 'must be plain text, for example "2020–2024"')
        if person.get('orcid'):
            require(orcid_valid(person['orcid']), where, 'invalid ORCID (including checksum)')
        if person.get('email'):
            email(person['email'], where)
    for item in software:
        text_fields(item, ['name' if 'name' in item else 'title', 'type', 'url'], f'software/{item["id"]}')
        require(item['type'] in TYPES, item['id'], f'resource type must be one of {TYPES}')
    seen_doi = set()
    for p in publications:
        where = f'publications/{p["id"]}'
        for key in ('website', 'code', 'data'):
            if key in p and p[key] is not None:
                require(isinstance(p[key], str), f'{where}.{key}', 'must be HTTP(S) URL text')
        text_fields(p, ['title', 'venue'], where)
        require(isinstance(p.get('authors'), (str, list)) and bool(p['authors']), where, 'authors required')
        if isinstance(p['authors'], list):
            require(all(isinstance(v, str) and v.strip() for v in p['authors']), where, 'author names must be nonempty text')
        require(type(p.get('year')) is int and 1600 <= p['year'] <= 2200, where, 'year must be an integer in 1600..2200')
        require(p.get('status', 'confirmed') in ('confirmed', 'candidate', 'excluded'), where, 'invalid curation status')
        require(p.get('type', 'article') in ('article', 'preprint', 'book', 'chapter', 'dataset', 'software', 'other'), where, 'invalid publication type')
        doi = normalize_doi(p.get('doi'))
        if doi:
            require(bool(re.fullmatch(r'10\.\d{4,9}/[^\s<>]+', doi)), where, 'invalid DOI')
            require(doi not in seen_doi, where, f'duplicate normalized DOI {doi}')
            seen_doi.add(doi)
    return cfg, data
