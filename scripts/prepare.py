"""Generate a disposable Quarto source tree without modifying authored files."""
from __future__ import annotations
import argparse
import datetime as dt
from email.utils import format_datetime
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
import yaml
from content import ROOT, ROLES, validate, normalize_doi, frontmatter, accent_text, accent_text_dark, on_accent, author_key, ContentError
from blog import published_posts, member_posts, member_publications, resolved_authors
from teaching import TYPES, sorted_offerings, chronological_offerings, offering_details, offering_anchor, member_courses
from routes import main_page_url, blog_page_url, stage_main_pages
from community_map import render as community_map

LABELS = {'research': 'Research', 'people': 'People', 'publications': 'Publications', 'software': 'Resources', 'news': 'News', 'blog': 'Blog', 'teaching': 'Teaching', 'join': 'Join', 'contact': 'Contact'}
GROUPS = dict(zip(ROLES, ('Principal investigator', 'Postdoctoral researchers', 'Research staff', 'Doctoral students', "Master’s students", 'Undergraduate students', 'Visitors', 'Alumni')))

def merge_config(base, override):
    """Nested site options augment the shared format instead of replacing it."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_config(base[key], value)
        else:
            base[key] = value
    return base

def esc(value):
    return html.escape(str(value or ''), quote=True)

def raw(value):
    return '\n```{=html}\n' + value + '\n```\n'

def link(label, url, css=''):
    return f'<a class="{esc(css)}" href="{esc(url)}">{esc(label)}</a>'


def teaching_actions(details):
    actions, seen = [], set()
    for label, destination in details.get('links', {}).items():
        if destination in seen:
            continue
        seen.add(destination)
        key = label.casefold()
        if any(value in key for value in ('github', 'code', 'repository', 'repo')):
            icon = 'github' if urlsplit(destination).hostname in ('github.com', 'www.github.com') else 'git'
        elif any(value in key for value in ('lms', 'canvas', 'moodle', 'blackboard')):
            icon = 'easel2'
        elif 'syllabus' in key:
            icon = 'file-earmark-text'
        elif any(value in key for value in ('website', 'catalog', 'homepage')):
            icon = 'globe2'
        elif 'pdf' in key or urlsplit(destination).path.casefold().endswith('.pdf'):
            icon = 'file-earmark-pdf'
        elif any(value in key for value in ('material', 'note', 'slide', 'assignment')):
            icon = 'journal-text'
        else:
            icon = 'box-arrow-up-right'
        context = ' '.join(filter(None, [details.get('term', ''), str(details['year'])]))
        actions.append('<a class="resource-link course-link" href="' + esc(destination) + '" title="' + esc(label) + '" aria-label="' + esc(f'{label} for {details["title"]}, {context}') + '"><i class="bi bi-' + icon + '" aria-hidden="true"></i><span class="resource-link-caption" aria-hidden="true">' + esc(label) + '</span></a>')
    return '<div class="course-links resource-links">' + ''.join(actions) + '</div>' if actions else ''


def teaching_metadata(details):
    values = [TYPES[details.get('type', 'course')], details.get('code', ''), details.get('institution', ''), details.get('teaching_role', '')]
    if str(details.get('credits', '')).strip():
        values.append('Credits: ' + str(details['credits']))
    if details.get('date'):
        def label(value):
            value = dt.date.fromisoformat(value)
            return str(value.day) + value.strftime(' %b %Y')
        values.append(label(details['date']) + (' – ' + label(details['end_date']) if details.get('end_date') else ''))
    values.append(details.get('duration', ''))
    return '<p class="course-meta">' + esc(' · '.join(str(value) for value in values if value)) + '</p>'


def teaching_rows(courses, people, prefix, compact=False, native_headings=False):
    by_id = {person['id']: person for person in people}
    rows, anchored = [], set()
    if compact:
        for course in courses:
            latest = sorted_offerings(course)[0]
            details = offering_details(course, latest)
            heading = link(course['title'], prefix + 'pages/teaching.html#' + course.get('_profile_anchor', course['id']))
            term = ' '.join(filter(None, [latest.get('term', ''), str(latest['year'])]))
            rows.append('<li><h3>' + heading + '</h3>' + teaching_metadata(details) + '<p class="course-term">' + esc(term) + '</p></li>')
        return '<ul class="profile-course-list">' + ''.join(rows) + '</ul>'
    for course, offering in chronological_offerings(courses):
        details = offering_details(course, offering)
        anchor = offering_anchor(course, offering)
        alias = '<span class="course-anchor" id="' + esc(course['id']) + '"></span>' if course['id'] not in anchored else ''
        anchored.add(course['id'])
        term = offering.get('term', '').strip()
        if not term and offering.get('date'):
            value = dt.date.fromisoformat(offering['date'])
            term = str(value.day) + value.strftime(' %b')
        dateline = '<div class="course-date"><span class="course-year">' + str(offering['year']) + '</span>' + ('<span class="course-term">' + esc(term) + '</span>' if term else '') + '</div>'
        instructors = [link(by_id[person]['name'], prefix + 'people/' + person + '.qmd') for person in details.get('people', [])]
        instructors.extend(link(person['name'], person['url']) if person.get('url') else esc(person['name']) for person in details.get('instructors', []))
        body = teaching_metadata(details)
        if instructors:
            body += '<p class="course-instructors"><span>Instructors:</span> ' + ', '.join(instructors) + '</p>'
        if details.get('description'):
            body += '<p class="course-description">' + esc(details['description']) + '</p>'
        attributes = ' data-teaching-type="' + esc(details['type']) + '"'
        actions = teaching_actions(details)
        if native_headings:
            safe_title = re.sub(r'([\\`*\[\]{}])', r'\\\1', esc(course['title']))
            rows.append(':::: {.teaching-course #' + anchor + attributes + '}\n\n' + raw(alias + dateline) + '\n::: {.course-content}\n\n::: {.course-heading-row}\n\n## ' + safe_title + ' {#course-heading-' + anchor + '}\n\n' + raw(actions) + '\n:::\n\n' + raw(body) + '\n:::\n\n::::\n')
        else:
            rows.append('<article class="teaching-course" id="' + anchor + '"' + attributes + '>' + alias + dateline + '<div class="course-content"><div class="course-heading-row"><h2>' + esc(course['title']) + '</h2>' + actions + '</div>' + body + '</div></article>')
    if native_headings:
        return '::::: {.teaching-list data-teaching-list=""}\n\n' + '\n'.join(rows) + '\n:::::\n'
    return '<div class="teaching-list" data-teaching-list>' + ''.join(rows) + '</div>'


def teaching_controls(courses):
    types = {offering_details(course, offering)['type'] for course, offering in chronological_offerings(courses)}
    count = sum(len(course['offerings']) for course in courses)
    return '<details class="teaching-filters" open hidden><summary>Search &amp; filter</summary><div class="teaching-controls"><div><label for="teaching-search">Search teaching</label><input id="teaching-search" type="search" placeholder="Title, instructor, institution, or year"></div><div><label for="teaching-type">Type</label><select id="teaching-type"><option value="">All types</option>' + ''.join('<option value="' + key + '">' + TYPES[key] + '</option>' for key in TYPES if key in types) + '</select></div></div></details><p id="teaching-count" role="status" aria-live="polite">' + str(count) + ' offering' + ('s' if count != 1 else '') + '</p>'


def blog_byline(post, people, prefix):
    return ', '.join(link(author['name'], prefix + 'people/' + author['person'] + '.qmd') if author.get('person') else esc(author['name']) for author in resolved_authors(post, people))


def blog_taxonomy(post, prefix):
    groups = []
    for field, parameter in (('categories', 'category'), ('tags', 'tag')):
        groups.extend(link(value, prefix + 'blog/?' + parameter + '=' + quote(value), 'blog-chip') for value in post.get(field, []))
    return '<div class="blog-taxonomy" role="group" aria-label="Categories and tags">' + ''.join(groups) + '</div>' if groups else ''


def blog_rows(posts, people, prefix, heading_level=2):
    rows = []
    for post in published_posts(posts):
        thumbnail = '<a class="blog-thumbnail" href="' + esc(prefix + blog_page_url(post['path'])) + '" tabindex="-1" aria-hidden="true"><img src="' + esc(prefix + post['image']) + '" alt="" loading="lazy"></a>' if post.get('image') else ''
        attributes = ' data-categories="' + esc(json.dumps([value.casefold() for value in post['categories']])) + '" data-tags="' + esc(json.dumps([value.casefold() for value in post.get('tags', [])])) + '"'
        rows.append('<article class="blog-post-row' + (' blog-has-thumbnail' if thumbnail else '') + '"' + attributes + '>' + thumbnail + '<div class="blog-post-copy"><time datetime="' + esc(post['date']) + '">' + esc(post['date']) + f'</time><h{heading_level}>' + link(post['title'], prefix + blog_page_url(post['path'])) + f'</h{heading_level}><p class="blog-byline">By ' + blog_byline(post, people, prefix) + '</p><p class="blog-description">' + esc(post['description']) + '</p>' + blog_taxonomy(post, prefix) + '</div></article>')
    return ''.join(rows)


def blog_listing(posts, people):
    posts = published_posts(posts)
    if not posts:
        return raw('<p class="blog-empty">Blog posts will be shared here.</p>')
    controls = '<details class="blog-filters" open hidden><summary>Search &amp; filter</summary><div class="blog-controls"><div><label for="blog-search">Search posts</label><input id="blog-search" type="search" placeholder="Title, author, or topic"></div>'
    for field, singular in (('categories', 'category'), ('tags', 'tag')):
        labels = {}
        for post in posts:
            for label in post.get(field, []):
                labels.setdefault(label.casefold(), label)
        controls += '<div><label for="blog-' + singular + '">' + singular.title() + '</label><select id="blog-' + singular + '"><option value="">All ' + field + '</option>' + ''.join('<option value="' + esc(value) + '">' + esc(labels[value]) + '</option>' for value in sorted(labels)) + '</select></div>'
    controls += '</div></details><p id="blog-count" role="status" aria-live="polite">' + str(len(posts)) + ' post' + ('s' if len(posts) != 1 else '') + '</p>'
    return raw(controls + '<div class="blog-list" data-blog-posts>' + blog_rows(posts, people, '../') + '</div><p id="blog-empty" hidden>No posts match these filters.</p>')


def blog_author_details(post, people):
    authors = []
    for author in resolved_authors(post, people):
        portrait = '<img class="blog-author-photo" src="../' + esc(author['photo']) + '" alt="" loading="lazy">' if author.get('photo') else ''
        name = link(author['name'], '../people/' + author['person'] + '.qmd') if author.get('person') else esc(author['name'])
        role = author.get('position', author.get('role', '')) if author.get('person') else author.get('affiliation', '')
        summary = author.get('summary', '') if author.get('person') else author.get('bio', '')
        icons = profile_links(author)
        authors.append('<div class="blog-author">' + portrait + '<div><h3>' + name + '</h3>' + ('<p class="blog-author-role">' + esc(role) + '</p>' if role else '') + ('<p>' + esc(summary) + '</p>' if summary else '') + ('<nav class="profile-links" aria-label="Profiles for ' + esc(author['name']) + '">' + icons + '</nav>' if icons else '') + '</div></div>')
    return '<section class="blog-authors" aria-labelledby="blog-authors-title"><h2 id="blog-authors-title">About the author' + ('s' if len(authors) > 1 else '') + '</h2>' + ''.join(authors) + '</section>'


def post_citation(post, people, site_url):
    return {'id': 'blog-' + post['id'], 'type': 'post-weblog', 'title': post['title'],
            'author': [{'literal': author['name']} for author in resolved_authors(post, people)],
            'issued': {'date-parts': [[int(part) for part in str(post['date']).split('-')]]},
            'URL': urljoin(site_url.rstrip('/') + '/', blog_page_url(post['path']).replace('.qmd', '.html')),
            **({'DOI': post['doi']} if post.get('doi') else {})}


def post_bibtex(record):
    def escaped(value):
        table = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%', '&': r'\&', '_': r'\_', '#': r'\#', '$': r'\$'}
        return ''.join(table.get(char, char) for char in str(value)).replace('\n', ' ')
    fields = {'title': '{' + escaped(record['title']) + '}',
              'author': ' and '.join('{' + escaped(author['literal']) + '}' for author in record['author']),
              'year': str(record['issued']['date-parts'][0][0]), 'url': escaped(record['URL'])}
    if record.get('DOI'): fields['doi'] = escaped(record['DOI'])
    return '@misc{' + record['id'] + ',\n' + ',\n'.join('  ' + key + ' = {' + value + '}' for key, value in fields.items()) + '\n}\n'


def blog_share_links(post, site_url):
    destination = urljoin(site_url.rstrip('/') + '/', blog_page_url(post['path']).replace('.qmd', '.html'))
    title = ' '.join(post['title'].split())
    text = title + '\n\n' + destination
    targets = (
        ('LinkedIn', 'linkedin', 'https://www.linkedin.com/sharing/share-offsite/', {'url': destination}),
        ('Bluesky', 'bluesky', 'https://bsky.app/intent/compose', {'text': text}),
        ('Weibo', 'sina-weibo', 'https://service.weibo.com/share/share.php', {'url': destination, 'title': title}),
        ('email', 'envelope', 'mailto:', {'subject': title, 'body': text}),
    )
    links = []
    for name, icon, endpoint, parameters in targets:
        label = 'Share by email' if name == 'email' else 'Share on ' + name
        href = endpoint + '?' + urlencode(parameters, quote_via=quote)
        external = ' target="_blank" rel="noopener noreferrer"' if name != 'email' else ''
        links.append('<a class="paper-link blog-share-link" href="' + esc(href) + '" aria-label="' + label + '" title="' + label + '"' + external + '><i class="bi bi-' + icon + '" aria-hidden="true"></i><span class="paper-link-caption" aria-hidden="true">' + label + '</span></a>')
    return '<nav class="blog-share" aria-label="Share this post"><span class="blog-share-label">Share</span>' + ''.join(links) + '</nav>'


def prepare_blog(stage, cfg, data, site_url):
    enabled = cfg.get('blog', {}).get('enabled', False)
    posts = published_posts(data['blog']) if enabled else []
    (stage / '_generated/blog.md').write_text(blog_listing(posts, data['people']), encoding='utf-8')
    for post in posts:
        metadata = {key: post[key] for key in ('id', 'title', 'description', 'date', 'image', 'image_alt', 'draft') if key in post}
        if post.get('image'):
            metadata['image'] = '../' + post['image']
        metadata.update({'body-classes': 'blog-page', 'date-format': 'D MMM YYYY', 'execute': {'enabled': False}, 'filters': ['../framework/filters/blog-paths.lua']})
        toc = cfg.get('toc', {})
        metadata['format'] = {'html': {'toc': post.get('toc', toc.get('blog', False)), 'toc-depth': toc.get('depth', 2), 'toc-location': 'body'}}
        if metadata['format']['html']['toc']:
            metadata['format']['html']['section-divs'] = False
            metadata['filters'].append('../framework/filters/contents.lua')
        intro = ''
        details = '<div class="blog-meta-details"><div class="blog-meta-byline"><p class="blog-back">' + link('← All posts', '../blog/index.qmd') + '</p><p class="blog-byline">By ' + blog_byline(post, data['people'], '../') + '</p></div>' + blog_taxonomy(post, '../') + '</div>'
        actions = ''
        if post.get('cite', cfg.get('blog', {}).get('cite', True)):
            citation = post_citation(post, data['people'], site_url)
            metadata.update({'citation': {'type': 'post-weblog', 'title': post['title'],
                'author': [author['literal'] for author in citation['author']], 'issued': str(post['date']),
                'url': citation['URL'], **({'doi': citation['DOI']} if citation.get('DOI') else {})},
                'google-scholar': True, 'language': {'section-title-citation': 'Cite this post'}})
            downloads = stage / 'assets/blog-citations'; downloads.mkdir(parents=True, exist_ok=True)
            (downloads / (post['id'] + '.bib')).write_text(post_bibtex(citation), encoding='utf-8')
            (downloads / (post['id'] + '.json')).write_text(json.dumps([citation], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            actions += '<nav class="blog-citation-links" aria-label="Post citation">' + link('Cite this post', '#quarto-citation') + '<a download href="../assets/blog-citations/' + esc(post['id']) + '.bib">BibTeX</a><a download href="../assets/blog-citations/' + esc(post['id']) + '.json">CSL JSON</a></nav>'
        else:
            metadata['citation'] = False
        actions += blog_share_links(post, site_url)
        intro += '<div class="blog-meta-bar">' + details + '<div class="blog-meta-actions">' + actions + '</div></div>'
        if post.get('image') and post.get('image_cover', True):
            intro += '<figure class="blog-cover"><img src="../' + esc(post['image']) + '" alt="' + esc(post['image_alt']) + '"></figure>'
        fence = ':' * (max([len(line.strip()) for line in post['body'].splitlines() if line.strip() and set(line.strip()) == {':'}] or [3]) + 2)
        authored = fence + ' {.blog-source data-blog-origin="' + Path(post['path']).parent.as_posix() + '"}\n\n' + post['body'] + '\n' + fence
        body = (fence + ':') + ' {.blog-article}\n\n' + raw(intro) + '\n' + authored + '\n\n' + raw(blog_author_details(post, data['people'])) + '\n' + (fence + ':') + '\n'
        destination = stage / blog_page_url(post['path'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n' + body, encoding='utf-8')
    # Quarto discovers linked inputs as well as explicit render targets. Keep only
    # the framework-owned published copies in this disposable tree.
    for post in data['blog']:
        (stage / post['path']).unlink()

def profile_links(person, allowed=None):
    """Render existing member destinations as accessible, tooltip-labelled icons."""
    destinations = dict(person.get('links', {}))
    if person.get('orcid'):
        destinations['ORCID'] = 'https://orcid.org/' + person['orcid']
    if person.get('website'):
        destinations['Website'] = person['website']
    if person.get('email'):
        destinations['Email'] = 'mailto:' + person['email']
    icons = {'google-scholar': ('Google Scholar', 'mortarboard'), 'scholar': ('Google Scholar', 'mortarboard'), 'home-page': ('Website', 'globe2'), 'website': ('Website', 'globe2'), 'github': ('GitHub', 'github'), 'linkedin': ('LinkedIn', 'linkedin'), 'bluesky': ('Bluesky', 'bluesky'), 'twitter': ('Twitter / X', 'twitter'), 'orcid': ('ORCID', 'orcid'), 'email': ('Email', 'envelope')}
    entries, seen = [], set()
    for key, destination in destinations.items():
        normalized = str(key).lower().replace('_', '-').replace(' ', '-')
        if allowed is not None and normalized not in allowed:
            continue
        if destination in seen:
            continue
        seen.add(destination)
        label, icon = icons.get(normalized, (str(key).replace('-', ' ').replace('_', ' '), 'box-arrow-up-right'))
        if icon == 'orcid':
            glyph = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="11" fill="currentColor"/><text x="4" y="16" font-family="Arial, sans-serif" font-size="12" font-weight="bold" fill="var(--lab-bg, #FAFAF8)">iD</text></svg>'
        else:
            glyph = f'<i class="bi bi-{icon}" aria-hidden="true"></i>'
        entries.append(f'<a class="profile-link" href="{esc(destination)}" aria-label="{esc(label)}" title="{esc(label)}">{glyph}</a>')
    return ''.join(entries)

def source(item, show_sources=True):
    return '<p class="source-link">' + link('Original source', item['source_url']) + '</p>' if show_sources and item.get('source_url') else ''

def title(item):
    return item.get('title', item.get('name', ''))

def research_href(item):
    return item['path'] if item.get('detail_page', False) else 'pages/research.qmd#' + item['id']

def news_href(item):
    return item['path'] if item.get('detail_page', False) else 'pages/news.qmd#' + item['id']

def news_feed(lab, site_url, news, section='news'):
    """Keep the existing RSS URL and latest-20 scope without requiring article pages."""
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    for key, value in (('title', lab['name'] + ' — ' + section.title()), ('link', urljoin(site_url.rstrip('/') + '/', main_page_url('pages/' + section + '.html'))), ('description', lab['description'])):
        ET.SubElement(channel, key).text = value
    for item in sorted(news, key=lambda p: str(p['date']), reverse=True)[:20]:
        target = main_page_url(blog_page_url((item['path'] if section == 'blog' else news_href(item)).replace('.qmd', '.html')))
        destination = urljoin(site_url.rstrip('/') + '/', target)
        entry = ET.SubElement(channel, 'item')
        for key, value in (('title', item['title']), ('link', destination), ('description', item['description'])):
            ET.SubElement(entry, key).text = value
        ET.SubElement(entry, 'guid', isPermaLink='true').text = destination
        date = dt.datetime.combine(dt.date.fromisoformat(str(item['date'])), dt.time(), tzinfo=dt.timezone.utc)
        ET.SubElement(entry, 'pubDate').text = format_datetime(date, usegmt=True)
        for category in item['categories']:
            ET.SubElement(entry, 'category').text = str(category)
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def news_listing_items(news):
    items = []
    latest_id = max(news, key=lambda item: str(item['date']), default={}).get('id')
    for item in news:
        fence = ':' * (max([len(line.strip()) for line in item['body'].splitlines() if line.strip() and set(line.strip()) == {':'}] or [3]) + 3)
        items.append({
            'title': item['title'], 'description': item['description'], 'date': str(item['date']),
            'entry-title': item['title'], 'entry-description': item['description'],
            'categories': item['categories'], 'entry-id': item['id'], 'entry-date': str(item['date']),
            'entry-href': '../' + news_href(item), 'entry-source': item['path'],
            'entry-body': item['body'], 'entry-fence': fence, 'detail-page': item['detail_page'],
            'entry-image': '../' + item['image'] if item.get('image') else '',
            'entry-image-alt': item.get('image_alt', ''),
            'external-url': item.get('url', '') if item.get('url') and item['url'] not in item['body'] else '',
            'more-url': item.get('url', ''),
            'is-latest': item['id'] == latest_id,
        })
    return items

def research_rows(data, show_sources=True, summary_figure=None, native_headings=False):
    rows = []
    for item in sorted(data['projects'], key=lambda p: title(p).casefold()):
        image = item.get('image')
        image_alt = item.get('image_alt') or title(item)
        # Long fences keep ordinary authored Markdown divs nested inside the row.
        fence = ':' * (max([len(line.strip()) for line in item['body'].splitlines() if line.strip() and set(line.strip()) == {':'}] or [3]) + 4)
        row = f'{fence} {{#{item["id"]} .research-direction' + (' .research-has-image' if image else '') + '}\n\n'
        row += fence[:-1] + ' {.research-copy}\n\n'
        heading = link(title(item), '../' + item['path']) if item['detail_page'] else esc(title(item))
        if native_headings:
            safe_title = re.sub(r'([\\`*\[\]{}])', r'\\\1', esc(title(item)))
            if item['detail_page']: safe_title = '[' + safe_title + '](../' + item['path'] + ')'
            row += '## ' + safe_title + ' {#research-heading-' + item['id'] + ' .research-heading}\n\n'
            row += raw('<p class="research-description">' + esc(item['description']) + '</p>')
        else:
            row += raw('<h2 class="research-heading">' + heading + '</h2><p class="research-description">' + esc(item['description']) + '</p>')
        if not item['detail_page']:
            row += '\n' + fence[:-2] + ' {.research-body data-research-origin="' + esc(item['path']) + '" data-research-id="' + item['id'] + '"}\n\n' + item['body'] + '\n\n' + fence[:-2] + '\n'
            row += relationships('projects', item['id'], data, prefix='../', heading_level=3)
            for key, label in (('collaborators', 'Collaborators'), ('funders', 'Funding')):
                if item.get(key):
                    row += raw('<section><h3>' + label + '</h3><ul>' + ''.join('<li>' + esc(value) + '</li>' for value in item[key]) + '</ul></section>')
            if item.get('source_url'):
                row += raw(source(item, show_sources))
        row += '\n' + fence[:-1] + '\n\n'
        if image:
            row += raw('<figure class="research-visual"><img src="../' + esc(image) + '" alt="' + esc(image_alt) + '" loading="lazy"></figure>')
        row += '\n' + fence + '\n'
        rows.append(row)
    if not rows:
        return 'Research directions will be shared here.\n'
    content = '\n'.join(rows)
    if summary_figure:
        # Keep the shared illustration outside every individual direction.
        fence = ':' * (max(len(line.strip()) for line in content.splitlines() if line.strip() and set(line.strip()) == {':'}) + 2)
        figure = raw('<figure class="research-summary-figure"><img src="../' + esc(summary_figure['image']) + '" alt="' + esc(summary_figure['image_alt']) + '" decoding="async"></figure>')
        content = fence + ' {.research-overview}\n\n' + figure + '\n' + fence[:-1] + ' {.research-directions}\n\n' + content + '\n\n' + fence[:-1] + '\n\n' + fence + '\n'
    return content

def cards(items, href=None):
    return '<div class="lab-grid">' + ''.join(f'<article class="lab-card"><h3>{link(title(p), href(p)) if href else esc(title(p))}</h3><p>{esc(p.get("description", ""))}</p></article>' for p in items) + '</div>'

def resource_actions(item):
    actions = []
    if item.get('repo'):
        icon = 'github' if urlsplit(item['repo']).hostname in ('github.com', 'www.github.com') else 'git'
        actions.append(f'<a class="resource-link resource-code" href="{esc(item["repo"])}" title="Source code" aria-label="Source code for {esc(title(item))}"><i class="bi bi-{icon}" aria-hidden="true"></i><span class="resource-link-caption" aria-hidden="true">Source code</span></a>')
    actions.append(f'<a class="resource-link resource-website" href="{esc(item["url"])}" title="Website" aria-label="Website for {esc(title(item))}"><i class="bi bi-globe2" aria-hidden="true"></i><span class="resource-link-caption" aria-hidden="true">Website</span></a>')
    return '<div class="resource-links">' + ''.join(actions) + '</div>'

def resource_header(item):
    return '<div class="resource-header"><p class="eyebrow">' + esc(item['type']) + '</p>' + resource_actions(item) + '</div>'

def academic_footer(cfg, people=()):
    lab, options = cfg['lab'], cfg.get('footer', {})
    pi_profiles = []
    if options.get('pi_links', False):
        for person in people:
            if person.get('group', person['role']) != 'pi':
                continue
            selected = {'links': {key: value for key, value in person.get('links', {}).items() if str(key).lower().replace('_', '-').replace(' ', '-') in ('github', 'google-scholar', 'scholar', 'orcid')}}
            if person.get('orcid'):
                selected['orcid'] = person['orcid']
            icons = profile_links(selected)
            if icons:
                pi_profiles.append('<div class="footer-pi-profile" role="group" aria-label="Profiles for ' + esc(person['name']) + '"><div class="profile-links">' + icons + '</div></div>')
    department = '<p>' + esc(lab['department']) + '</p>' if lab.get('department') else ''
    email = '<p>' + link(lab['email'], 'mailto:' + lab['email']) + '</p>' if options.get('show_email', True) else ''
    identity = '<div class="footer-identity"><div class="footer-details"><p class="footer-lab-name">' + esc(lab['name']) + '</p>' + department + '<p>' + esc(lab['institution']) + '</p>' + email + '</div>'
    destinations = [('pages/' + name + '.html', LABELS[name]) for name in ('research', 'publications', 'join', 'contact') if name == 'contact' or name in cfg.get('navigation', LABELS)]
    brand_logo = '<img class="footer-brand-logo" src="/' + esc(cfg['branding']['logo']) + '" alt="' + esc(lab['name']) + '" loading="lazy" decoding="async">' if options.get('show_logo', False) else ''
    logos = []
    for logo in options.get('logos', []):
        img = '<img src="/' + esc(logo['src']) + '" alt="' + esc(logo['alt']) + '" loading="lazy">'
        logos.append('<a href="' + esc(logo['url']) + '">' + img + '</a>' if logo.get('url') else img)
    partners = '<div class="footer-logos" aria-label="Affiliated institutions">' + ''.join(logos) + '</div>' if logos else ''
    identity += partners + '</div>'
    marks = '<div class="footer-marks">' + brand_logo + '</div>' if brand_logo else ''
    navigation = '<div class="footer-navigation"><nav class="footer-links" aria-label="Footer links">' + ''.join(link(label, '/' + href) for href, label in destinations) + '</nav>' + ''.join(pi_profiles) + marks + '</div>'
    guide = options.get('documentation_url') or 'https://khan-lab.github.io/researchlabfolio/'
    actions = '<a class="footer-guide" href="' + esc(guide) + '"><i class="bi bi-book" aria-hidden="true"></i><span>Documentation</span></a>'
    if options.get('source_url'):
        actions += '<a class="footer-source" href="' + esc(options['source_url']) + '" title="GitHub source code"><i class="bi bi-github" aria-hidden="true"></i><span>Source code</span></a>'
    return '<div class="lab-footer"><div class="footer-main">' + identity + navigation + '</div><div class="footer-bottom"><p>Built with ' + link('ResearchLabFolio', 'https://github.com/khan-lab/researchlabfolio') + ' · Quarto</p><div class="footer-template-links">' + actions + '</div></div></div>'

def recruitment_media(options):
    """A framed gallery; a single legacy image remains a supported input."""
    slides = options.get('slides', []) or ([options] if options.get('image') else [])
    if not slides:
        return ''
    photos = options.get('photos', {})
    treatment = 'grayscale(' + ('1' if photos.get('grayscale', False) else '0') + f') blur({photos.get("blur", 0):g}px)'
    reveal = 'grayscale(0) blur(0px)' if photos.get('reveal_on_hover', True) else treatment
    figures = ''.join('<figure class="recruitment-slide"><img src="' + esc(slide['image']) + '" alt="' + esc(slide['image_alt']) + '" loading="lazy" decoding="async">' + ('<figcaption>' + esc(slide['caption']) + '</figcaption>' if slide.get('caption') else '') + '</figure>' for slide in slides)
    controls = '<div class="recruitment-gallery-controls" hidden><button type="button" data-gallery-previous aria-label="Previous photo"><span aria-hidden="true">←</span></button><span class="recruitment-gallery-status" role="status" aria-atomic="true"></span><button type="button" data-gallery-next aria-label="Next photo"><span aria-hidden="true">→</span></button></div>' if len(slides) > 1 else ''
    return '<div class="home-recruitment-photo" data-recruitment-gallery role="group" aria-label="Lab photographs" style="--recruitment-photo-filter:' + treatment + ';--recruitment-photo-reveal:' + reveal + '"><div class="recruitment-slides">' + figures + '</div>' + controls + '</div>'

def homepage(cfg, data, papers):
    """Compose the homepage from authored identity and curated, public records."""
    lab, flags = cfg['lab'], cfg.get('homepage', {})
    people = [p for p in data['people'] if p.get('group', p['role']) != 'alumni']
    leads = [p for p in people if p.get('group', p['role']) == 'pi']
    options = cfg.get('hero', {})
    aside = ''
    if options.get('image'):
        caption = '<figcaption>' + esc(options['image_caption']) + '</figcaption>' if options.get('image_caption') else ''
        aside += '<figure class="home-hero-figure"><img src="' + esc(options['image']) + '" alt="' + esc(options['image_alt']) + '" fetchpriority="high">' + caption + '</figure>'
    if options.get('overview', False):
        affiliation = ' · '.join(filter(None, [lab.get('department'), lab['institution']]))
        overview = '<div class="home-overview" role="complementary" aria-label="About the lab"><p class="home-affiliation">' + esc(affiliation) + '</p>'
        if leads:
            overview += '<p class="home-lead"><span>Led by</span> ' + ', '.join(link(p['name'], 'people/' + p['id'] + '.qmd') for p in leads) + '</p>'
        aside += overview + '</div>'
    if options.get('metrics'):
        facts = []
        for metric in options['metrics']:
            value = link(metric['value'], metric['url']) if metric.get('url') else esc(metric['value'])
            facts.append('<div class="home-fact"><dt>' + esc(metric['label']) + '</dt><dd class="home-fact-value">' + value + '</dd></div>')
        aside += '<dl class="home-facts">' + ''.join(facts) + '</dl>'
    navigation = cfg.get('navigation', LABELS)
    if 'actions' in options:
        actions = options['actions']
    else:
        candidates = [('join', 'Join the lab', flags.get('recruitment', True) and bool(lab.get('recruitment'))),
                      ('publications', 'Publications', flags.get('publications', True)),
                      ('people', 'Meet the people', flags.get('people', True)),
                      ('research', 'Our research', flags.get('research', True)), ('contact', 'Contact', True)]
        actions = [{'section': section, 'label': label} for section, label, enabled in candidates if enabled and section in navigation][:2]
    action_html = ''.join(link(action['label'], 'pages/' + action['section'] + '.qmd', 'lab-button' if i == 0 else '') for i, action in enumerate(actions))
    aside_html = '<div class="home-hero-aside">' + aside + '</div>' if aside else ''
    home = '<header id="title-block-header" class="hero quarto-title-block home-hero' + ('' if aside else ' home-hero-text-only') + '" aria-labelledby="home-title"><div class="hero-main"><p class="home-lab-name">' + esc(lab['name']) + '</p><h1 id="home-title">' + esc(lab['tagline']) + '</h1><p class="lede">' + esc(lab['description']) + '</p>' + ('<div class="hero-actions">' + action_html + '</div>' if action_html else '') + '</div>' + aside_html + '</header>'
    statements = [(key, label, lab.get(key, '').strip()) for key, label in (('mission', 'Our mission'), ('vision', 'Our vision'))
                  if flags.get(key, False) and lab.get(key, '').strip()]
    if statements:
        headings = ' '.join('home-' + key + '-title' for key, _, _ in statements)
        home += '<section class="home-statements' + (' home-statements-pair' if len(statements) == 2 else '') + '" aria-labelledby="' + headings + '">' + ''.join(
            '<div class="home-statement"><h2 id="home-' + key + '-title">' + label + '</h2><p>' + esc(value) + '</p></div>'
            for key, label, value in statements) + '</section>'

    def section(name, heading, content, label, page):
        return f'<section class="home-section home-{name}" aria-labelledby="home-{name}-title"><div class="home-section-heading"><h2 id="home-{name}-title">{heading}</h2>' + link(label + ' →', 'pages/' + page + '.qmd', 'home-section-link') + '</div>' + content + '</section>'

    updates = []
    if flags.get('research', True) and data['projects']:
        selected = [p for p in data['projects'] if p.get('featured')] or data['projects']
        research = '<div class="home-research-list">' + ''.join('<article><span class="home-research-number" aria-hidden="true">' + f'{i:02d}' + '</span><div><h3>' + link(title(p), research_href(p)) + '</h3><p>' + esc(p.get('description', '')) + '</p></div></article>' for i, p in enumerate(selected[:3], 1)) + '</div>'
        updates.append(section('research', 'Research directions', research, 'All research', 'research'))
    if flags.get('news', True) and data['news']:
        news = '<div class="news-rows">' + ''.join(f'<article class="{"news-latest" if index == 0 else ""}"><time datetime="{esc(p["date"])}">{esc(p["date"])}</time><h3>{link(p["title"], news_href(p))}</h3><p class="news-description"><span data-news-preview>{esc(p["description"])}</span> <a class="news-more" href="{esc(news_href(p))}" aria-label="More about {esc(p["title"])}">More</a></p></article>' for index, p in enumerate(sorted(data['news'], key=lambda p: str(p['date']), reverse=True)[:3])) + '</div>'
        updates.append(section('news', 'From the lab', news, 'All news', 'news'))
    if updates:
        home += '<div class="home-updates' + (' home-updates-pair' if len(updates) == 2 else '') + '">' + ''.join(updates) + '</div>'
    if flags.get('publications', True) and papers:
        selected = [p for p in papers if p.get('featured')] or papers[:2]
        home += section('publications', 'Selected publications', ('<p class="paper-author-key">Lab members in <strong>bold</strong>.</p>' if publication_author_names(cfg, data['people']) else '') + ''.join(paper_html(p, heading_level=3, compact=True, altmetric=cfg.get('publications', {}).get('altmetric', False), lab_authors=publication_author_names(cfg, data['people'])) for p in selected[:3]), 'All publications', 'publications')
    if flags.get('software', True) and data['software']:
        selected = sorted(data['software'], key=lambda p: not p.get('featured', False))[:3]
        tools = '<div class="lab-grid">' + ''.join('<article class="lab-card home-resource">' + resource_header(p) + '<h3>' + esc(title(p)) + '</h3><p>' + esc(p.get('description', '')) + '</p></article>' for p in selected) + '</div>'
        home += section('resources', 'Shared tools &amp; resources', tools, 'All resources', 'software')
    if flags.get('people', True) and people:
        members = sorted(people, key=lambda p: ROLES.index(p.get('group', p['role'])))
        previews = []
        for index, person in enumerate(members):
            initials = ''.join(word[0] for word in person['name'].split()[:2])
            portrait = f'<img src="{esc(person["photo"])}" alt="" width="56" height="56" loading="lazy">' if person.get('photo') else f'<span class="person-initials" aria-hidden="true">{esc(initials)}</span>'
            role = person.get('position') or (person['role'] if person.get('group') else GROUPS[person['role']])
            previews.append('<a class="home-person" href="people/' + esc(person['id']) + '.qmd"' + (' hidden' if index >= 3 else '') + '>' + portrait + '<span><span class="home-person-name">' + esc(person['name']) + '</span><span class="home-person-role">' + esc(role) + '</span></span></a>')
        home += section('people', 'People behind the research', '<div class="home-people-grid" data-random-people="3">' + ''.join(previews) + '</div>', 'Meet the team', 'people')
    quote = lab.get('quote', {})
    if flags.get('quote', False) and quote.get('text', '').strip():
        home += '<figure class="home-quote"><blockquote><p>“' + esc(quote['text'].strip()) + '”</p></blockquote><figcaption>— ' + esc(quote['author'].strip()) + '</figcaption></figure>'
    if flags.get('recruitment', True) and lab.get('recruitment'):
        copy = '<p class="eyebrow">Work with us</p><h2 id="home-join-title">' + esc(lab.get('recruitment_heading', 'Join the lab')) + '</h2><p class="home-recruitment-description">' + esc(lab['recruitment']) + '</p>'
        actions = '<div class="home-recruitment-actions">' + link('Join the lab →', 'pages/join.qmd', 'lab-button') + '</div>'
        recruitment = cfg.get('recruitment', {})
        media = recruitment_media(recruitment)
        if media:
            content = '<div class="home-recruitment-content">' + copy + actions + '</div>' + media
        else:
            content = '<div>' + copy + '</div>' + actions
        home += '<section class="recruitment home-recruitment' + (' home-recruitment-with-image' if media else '') + '" aria-labelledby="home-join-title">' + content + '</section>'
    return raw(home)

def authors(p):
    return ', '.join(p['authors']) if isinstance(p['authors'], list) else p['authors']

def pi_scholar_links(people):
    entries = []
    for person in people:
        if person.get('group', person['role']) != 'pi':
            continue
        for label, destination in person.get('links', {}).items():
            if str(label).lower().replace('_', '-').replace(' ', '-') in ('scholar', 'google-scholar'):
                entries.append('<a class="pi-scholar" href="' + esc(destination) + '" title="Google Scholar: ' + esc(person['name']) + '" aria-label="Google Scholar profile for ' + esc(person['name']) + '"><i class="bi bi-mortarboard" aria-hidden="true"></i><span>Google Scholar</span></a>')
                break
    return ''.join(entries)

def publication_author_names(cfg, people):
    if not cfg.get('publications', {}).get('highlight_authors', True):
        return set()
    return {author_key(alias) for person in people for alias in person.get('publication_names', [])}


def paper_author_html(p, compact=False, lab_authors=None):
    approved = lab_authors or set()
    def author_name(name):
        text = esc(name)
        return '<strong class="paper-lab-author">' + text + '</strong>' if author_key(name) in approved else text
    names = p['authors'] if isinstance(p['authors'], list) else []
    if not names:
        full = author_name(p['authors'])
        limit = 120 if compact else 320
        preview = esc(p['authors'][:100 if compact else 200].rsplit(' ', 1)[0] + '…') if len(p['authors']) > limit else full
    else:
        full = ', '.join(author_name(name) for name in names)
        if len(names) <= (3 if compact else 8):
            preview = full
        else:
            indices = set(range(min(3 if compact else 5, len(names))))
            if not compact:
                indices.update(range(max(0, len(names) - 3), len(names)))
            indices.update(i for i, name in enumerate(names) if author_key(name) in approved)
            ordered = sorted(indices)
            pieces = []
            for position, index in enumerate(ordered):
                if position:
                    pieces.append(', ' if index == ordered[position - 1] + 1 else ' … ')
                pieces.append(author_name(names[index]))
            if ordered[-1] < len(names) - 1:
                pieces.append(' et al.')
            preview = ''.join(pieces)
    if preview != full:
        return '<details class="paper-authors"><summary>' + preview + ' <span class="paper-author-action">(all authors)</span></summary><p>' + full + '</p></details>'
    return '<p class="paper-authors">' + full + '</p>'


def paper_html(p, heading_level=2, compact=False, altmetric=False, show_sources=True, lab_authors=None, member_ids=()):
    doi = normalize_doi(p.get('doi'))
    doi_url = 'https://doi.org/' + quote(doi, safe='/():;._-') if doi else ''
    paper_url = doi_url or p.get('url') or p.get('pdf') or p.get('preprint') or p.get('website')
    actions = []
    destinations = [('doi', 'DOI', 'link-45deg', doi_url)]
    if not doi:
        destinations.append(('url', 'Read publication', 'box-arrow-up-right', p.get('url')))
    destinations.extend((key, label, icon, p.get(key)) for key, label, icon in (
        ('website', 'Website', 'globe'), ('preprint', 'Preprint', 'file-earmark-text'), ('pdf', 'PDF', 'file-earmark-pdf'),
        ('code', 'Code', 'github' if urlsplit(p.get('code', '')).hostname in ('github.com', 'www.github.com') else 'code-slash'),
        ('data', 'Data', 'database')))
    if not compact and show_sources:
        destinations.append(('source', 'Metadata source', 'info-circle', p.get('source_url')))
    for key, label, icon, destination in destinations:
        if destination:
            actions.append(f'<a class="paper-link paper-link-{key}" href="{esc(destination)}" title="{esc(label)}" aria-label="{esc(label)} for {esc(p["title"])}"><i class="bi bi-{icon}" aria-hidden="true"></i><span class="paper-link-caption" aria-hidden="true">{esc(label)}</span></a>')
    kind = p.get('type', 'article')
    author_html = paper_author_html(p, compact, lab_authors)
    featured = bool(p.get('featured'))
    badge = '<p class="paper-featured-label"><span aria-hidden="true">★</span> Featured</p>' if featured and not compact else ''
    metrics = ''
    if altmetric and doi:
        badge_markup = '<div class="altmetric-embed" data-badge-type="donut" data-hide-no-mentions="true" data-doi="' + esc(doi) + '"></div>'
        metrics = '<div class="paper-altmetric">' + badge_markup + '</div>'
    classes = 'paper' + (' paper-compact' if compact else '') + (' paper-featured' if featured else '') + (' paper-with-altmetric' if metrics else '')
    year = '' if compact else f'<p class="paper-year">{p["year"]}</p>'
    venue = (str(p['year']) + ' · ' if compact else '') + esc(p['venue'])
    heading = link(p['title'], paper_url) if paper_url else esc(p['title'])
    action_links = '<div class="paper-links' + (' paper-links-with-sources' if show_sources and not compact else '') + '">' + ''.join(actions) + '</div>' if actions else ''
    footer_actions = '<div class="paper-actions">' + action_links + metrics + '</div>' if action_links or metrics else ''
    footer = '<div class="paper-footer">' + f'<p class="paper-venue">{venue}<span class="paper-kind"> · {esc(kind)}</span></p>' + footer_actions + '</div>'
    return f'<article class="{classes}" id="{esc(p["id"])}" data-year="{p["year"]}" data-type="{esc(kind)}" data-featured="{str(featured).lower()}" data-members="{esc(json.dumps(list(member_ids)))}">' + year + '<div class="paper-body">' + badge + f'<h{heading_level}>{heading}</h{heading_level}>' + author_html + footer + '</div></article>'

def bibliography(papers):
    def bibsafe(s):
        table = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%', '&': r'\&', '_': r'\_', '#': r'\#', '$': r'\$'}
        return ''.join(table.get(c, c) for c in str(s)).replace('\n', ' ')
    bib = []
    for p in papers:
        names = ' and '.join(p['authors']) if isinstance(p['authors'], list) else p['authors']
        fields = {'title': p['title'], 'author': names, 'year': p['year'], 'journal': p['venue']}
        if p.get('doi'):
            fields['doi'] = normalize_doi(p['doi'])
        if p.get('url'):
            fields['url'] = p['url']
        bib.append('@article{' + p['id'] + ',\n' + ',\n'.join(f'  {k} = {{{bibsafe(v)}}}' for k,v in fields.items()) + '\n}\n')
    return '\n'.join(bib)

def prepare(root=ROOT, stage=None):
    root = Path(root).resolve()
    framework = next((path for path in (root, *root.parents, ROOT)
                      if (path / 'styles/theme.scss').is_file() and (path / 'framework').is_dir()
                      and (path / '_quarto.yml').is_file()), None)
    if framework is None:
        raise ContentError('The selected website is missing its template framework.')
    cfg, data = validate(root)
    qcfg = yaml.safe_load((framework / '_quarto.yml').read_text(encoding='utf-8'))
    if root != framework and (root / '_quarto.yml').exists():
        merge_config(qcfg, yaml.safe_load((root / '_quarto.yml').read_text(encoding='utf-8')) or {})
    site_url = cfg['lab'].get('site_url') or qcfg['website'].get('site-url') or 'https://example.org/researchlabfolio/'
    if stage is None:
        stage = framework / '.scratch/builds' / ('generic' if root == framework else root.name) / 'source'
    stage = Path(stage)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    # Framework belongs to ResearchLabFolio; lab content belongs to the selected site.
    for name in ('styles', 'assets', 'pages', 'framework'):
        shutil.copytree(framework / name, stage / name)
    shutil.copy(framework / 'index.qmd', stage / 'index.qmd')
    cname = root / 'CNAME'
    if cname.exists():
        domain = cname.read_text(encoding='utf-8').strip()
        if cname.is_symlink() or not re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}', domain):
            raise ContentError('CNAME must contain one valid public hostname.')
        (stage / 'CNAME').write_text(domain + '\n', encoding='utf-8')
    shutil.copytree(root / 'content', stage / 'content')
    if root != framework:
        for name in ('assets', 'pages'):
            if (root / name).exists():
                shutil.copytree(root / name, stage / name, dirs_exist_ok=True)
        if (root / 'index.qmd').exists():
            shutil.copy(root / 'index.qmd', stage / 'index.qmd')
    legacy_join = stage / 'pages/opportunities.qmd'
    if legacy_join.exists():
        if (root / 'pages/join.qmd').exists():
            raise ContentError('Both pages/join.qmd and pages/opportunities.qmd exist; keep only pages/join.qmd.')
        # Preserve an older site's custom recruitment page without publishing an old URL.
        legacy_join.replace(stage / 'pages/join.qmd')
    # Authors may keep logos and photos outside assets/; copy validated paths too.
    paths = [cfg['branding'].get(k) for k in ('logo', 'favicon')]
    paths.append(cfg.get('hero', {}).get('image'))
    paths.append(cfg.get('recruitment', {}).get('image'))
    paths.extend(slide['image'] for slide in cfg.get('recruitment', {}).get('slides', []))
    paths.extend(logo['src'] for logo in cfg.get('footer', {}).get('logos', []))
    paths.extend(item.get(k) for items in data.values() for item in items for k in ('photo', 'image'))
    for value in filter(None, paths):
        relative = (root / value).resolve().relative_to(root)
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / relative, target)
    for page_name, collection, message in (('news', 'news', 'News updates will be shared here.'),):
        if not data[collection]:
            path = stage / 'pages' / (page_name + '.qmd')
            metadata, body = frontmatter(path)
            metadata.pop('listing', None)
            path.write_text('---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n' + body + '\n' + message + '\n', encoding='utf-8')
    out = stage / '_generated'
    out.mkdir()
    prepare_blog(stage, cfg, data, site_url)
    courses = data['teaching'] if cfg.get('teaching', {}).get('enabled', False) else []
    course_contents = 'teaching' in cfg.get('toc', {}).get('pages', [])
    course_text = teaching_rows(courses, data['people'], '../', native_headings=course_contents)
    if courses and cfg.get('teaching', {}).get('search', True):
        controls = teaching_controls(courses)
        empty = '<p id="teaching-empty" hidden>No teaching matches these filters.</p>'
        course_text = (raw(controls) + course_text + raw(empty)) if course_contents else controls + course_text + empty
    (out / 'teaching.md').write_text((course_text if course_contents else raw(course_text)) if courses else 'Course details will be shared here.\n', encoding='utf-8')
    summary_figure = cfg['hero'] if cfg.get('research', {}).get('summary_figure', False) else None
    (out / 'research.md').write_text(research_rows(data, cfg.get('provenance', {}).get('show_links', True), summary_figure,
                                               native_headings='research' in cfg.get('toc', {}).get('pages', [])), encoding='utf-8')
    summary = cfg.get('research', {}).get('summary', cfg['lab']['description'])
    research_intro = '<p class="research-summary">' + esc(summary) + '</p>'
    (out / 'research-summary.md').write_text(raw(research_intro), encoding='utf-8')
    (out / 'news-items.yml').write_text(yaml.safe_dump(news_listing_items(data['news']), sort_keys=False, allow_unicode=True), encoding='utf-8')
    targets = {'/' + item['path']: {'url': '/' + research_href(item), 'id': item['id'], 'inline': not item['detail_page']} for item in data['projects']}
    (out / 'research-targets.json').write_text(json.dumps(targets, ensure_ascii=False), encoding='utf-8')
    targets.update({'/' + item['path']: {'url': '/' + news_href(item), 'id': item['id'], 'inline': not item['detail_page'], 'more_url': item.get('url', ''), 'title': item['title']} for item in data['news']})
    (out / 'inline-targets.json').write_text(json.dumps(targets, ensure_ascii=False), encoding='utf-8')
    lab = cfg['lab']
    papers = sorted([p for p in data['publications'] if p.get('status', 'confirmed') == 'confirmed'], key=lambda p: (-p['year'], p['title']))
    brand = cfg['branding']
    colors = brand['colors']
    tokens = {f'--lab-{name}': colors[name] for name in ('primary', 'secondary')}
    for name, value in cfg.get('hero', {}).get('font_sizes', {}).items():
        tokens['--lab-hero-' + name.replace('_', '-') + '-size'] = f'{value:g}rem'
    photos = cfg.get('people', {}).get('photos', {})
    photo_filter = 'grayscale(' + ('1' if photos.get('grayscale', True) else '0') + ')'
    if photos.get('blur', 0):
        photo_filter += f' blur({photos["blur"]:g}px)'
    tokens['--lab-photo-filter'] = photo_filter
    tokens['--lab-photo-hover-filter'] = 'grayscale(0)' if photos.get('reveal_on_hover', True) else photo_filter
    for name in ('primary', 'secondary'):
        tokens[f'--lab-{name}-text'] = accent_text(colors[name])
        tokens[f'--lab-on-{name}'] = on_accent(colors[name])
    (out / 'brand.scss').write_text('/*-- scss:defaults --*/\n' + f'$primary: {colors["primary"]};\n$secondary: {colors["secondary"]};\n$link-color: {tokens["--lab-primary-text"]};\n$link-hover-color: {tokens["--lab-secondary-text"]};\n$font-family-sans-serif: "{brand["fonts"]["body"]}", Arial, sans-serif;\n$headings-font-family: "{brand["fonts"]["headings"]}", Georgia, serif;\n' + '/*-- scss:rules --*/\n:root {' + ' '.join(f'{key}: {value};' for key, value in tokens.items()) + '}\n', encoding='utf-8')
    dark_tokens = dict(tokens)
    for name in ('primary', 'secondary'):
        dark_tokens[f'--lab-{name}-text'] = accent_text_dark(colors[name])
    (out / 'brand-dark.scss').write_text('/*-- scss:defaults --*/\n' + f'$primary: {colors["primary"]};\n$secondary: {colors["secondary"]};\n$link-color: {dark_tokens["--lab-primary-text"]};\n$link-hover-color: {dark_tokens["--lab-secondary-text"]};\n$navbar-hl: {dark_tokens["--lab-primary-text"]};\n$font-family-sans-serif: "{brand["fonts"]["body"]}", Arial, sans-serif;\n$headings-font-family: "{brand["fonts"]["headings"]}", Georgia, serif;\n' + '/*-- scss:rules --*/\n:root {' + ' '.join(f'{key}: {value};' for key, value in dark_tokens.items()) + '}\n', encoding='utf-8')
    (out / 'home.md').write_text(homepage(cfg, data, papers), encoding='utf-8')
    # Individual profiles and grouped directory.
    profiles = stage / 'people'
    profiles.mkdir()
    directory = ''
    for group, label in GROUPS.items():
        members = [p for p in data['people'] if p.get('group', p['role']) == group]
        if not members:
            continue
        chunks = []
        for p in members:
            photo = ''
            if p.get('photo'):
                photo = f'<img src="../{esc(p["photo"])}" alt="{esc(p["name"])}" width="320" height="320" loading="lazy">'
            display = p.get('position', p['role'] if p.get('group') else label.rstrip('s'))
            names = p['name'].split()
            initials = ''.join(word[0] for word in (names[:1] + names[-1:] if len(names) > 1 else names))
            avatar = photo or f'<span class="person-initials" aria-hidden="true">{esc(initials)}</span>'
            profile_url = '../people/' + p['id'] + '.qmd'
            next_position = (p.get('next_position') or '').strip() if group == 'alumni' else ''
            destination_html = '<p class="alumni-destination"><strong>Now:</strong> ' + esc(next_position) + '</p>' if next_position else ''
            education = (p.get('education') or '').strip()
            education_html = '<p class="person-education"><strong>Education:</strong> ' + esc(education) + '</p>' if education and cfg.get('people', {}).get('show_education', False) else ''
            years = (p.get('years') or '').strip() if group == 'alumni' else ''
            years_html = '<span class="alumni-years"> · ' + esc(years) + '</span>' if years else ''
            icons = profile_links(p)
            directory_icons = profile_links(p, allowed={'google-scholar', 'scholar', 'orcid', 'github', 'email'})
            actions = '<nav class="profile-links person-links" aria-label="External profiles and contact for ' + esc(p['name']) + '">' + directory_icons + '</nav>' if directory_icons and group != 'alumni' else ''
            tag = 'li' if group == 'alumni' else 'article'
            classes = 'person-card alumni-entry' if group == 'alumni' else 'person-card'
            alumni_options = cfg.get('people', {}).get('alumni', {})
            show_photo = group != 'alumni' or alumni_options.get('show_photos', True)
            directory_name = link(p['name'], profile_url) if group != 'alumni' or alumni_options.get('link_profiles', False) else esc(p['name'])
            directory_avatar = '<div class="person-avatar">' + avatar + '</div>' if show_photo else ''
            if not show_photo:
                classes += ' alumni-text-only'
            chunks.append(f'<{tag} class="{classes}">' + directory_avatar + '<div class="person-info">' + f'<h3>{directory_name}</h3><p class="person-position">{esc(display)}{years_html}</p>' + education_html + actions + destination_html + f'</div></{tag}>')
            profile_education = '<strong>Education:</strong> ' + esc(education) if education else ''
            profile = yaml.safe_dump({'title': p['name'], 'description': p.get('summary') or display, 'profile-portrait': avatar, 'profile-role': display, 'profile-education': profile_education, 'profile-links': icons, 'format': {'html': {'template-partials': ['../framework/partials/profile/title-block.html']}}}, sort_keys=False, allow_unicode=True)
            profile_years = '<p class="alumni-years"><strong>Years in lab:</strong> ' + esc(years) + '</p>' if years else ''
            body = (raw(profile_years + destination_html) + '\n' if profile_years or destination_html else '') + p.get('bio', '') + '\n\n'
            if p.get('interests'):
                body += raw('<p><strong>Research interests:</strong> ' + esc(', '.join(p['interests'])) + '</p>')
            body += raw(source(p, cfg.get('provenance', {}).get('show_links', True))) if p.get('source_url') else ''
            body += relationships('people', p['id'], data, prefix='../', exclude_targets=('publications',))
            related_papers = member_publications(p, data['publications'])
            if related_papers:
                body += raw('<section class="profile-publications" aria-labelledby="profile-publications-title"><h2 id="profile-publications-title">Recent publications</h2>' + ''.join(paper_html(paper, heading_level=3, compact=True, altmetric=cfg.get('publications', {}).get('altmetric', False), show_sources=cfg.get('provenance', {}).get('show_links', True), lab_authors=publication_author_names(cfg, data['people'])) for paper in related_papers[:5]) + '<p class="profile-view-all">' + link(f'View all publications ({len(related_papers)}) →', '../pages/publications.html?member=' + quote(p['id'])) + '</p></section>')
            taught = member_courses(p, courses) if cfg.get('teaching', {}).get('profile_courses', True) else []
            if taught:
                body += raw('<section class="profile-teaching" aria-labelledby="profile-teaching-title"><h2 id="profile-teaching-title">Teaching</h2>' + teaching_rows(taught, data['people'], '../', compact=True) + '</section>')
            posts = member_posts(p, data['blog']) if cfg.get('blog', {}).get('enabled', False) else []
            if posts:
                body += raw('<section class="profile-blog" aria-labelledby="profile-blog-title"><h2 id="profile-blog-title">Blog posts</h2><div class="blog-list">' + blog_rows(posts, data['people'], '../', heading_level=3) + '</div></section>')
            (profiles / (p['id'] + '.qmd')).write_text('---\n' + profile + '---\n\n' + body, encoding='utf-8')
        collection = '<ul class="alumni-list">' + ''.join(chunks) + '</ul>' if group == 'alumni' else '<div class="people-grid">' + ''.join(chunks) + '</div>'
        directory += raw(f'<section class="people-section" aria-labelledby="people-group-{group}"><h2 class="people-group-title" id="people-group-{group}">{esc(label)}</h2>' + collection + '</section>')
    community = community_map(cfg, data['people'])
    if community:
        directory += raw(community)
        page = stage / 'pages/people.qmd'
        metadata, body = frontmatter(page)
        formats = metadata.setdefault('format', {}).setdefault('html', {})
        includes = formats.get('include-after-body', [])
        formats['include-after-body'] = ([includes] if isinstance(includes, str) else includes) + ['../framework/includes/community-map.html']
        page.write_text('---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n' + body, encoding='utf-8')
    (out / 'people.md').write_text(directory or 'Team details will be shared here.\n', encoding='utf-8')
    software_html = []
    for s in data['software']:
        software_html.append(f'<article class="lab-card resource" id="{esc(s["id"])}" data-type="{esc(s["type"])}">' + resource_header(s) + f'<h2>{esc(title(s))}</h2><p>{esc(s.get("description", ""))}</p>' + relationships('software', s['id'], data, prefix='../', as_html=True, heading_level=3) + '</article>')
    resource_count = ''
    resource_controls = ''
    if software_html and cfg.get('resources', {}).get('search', True):
        kinds = sorted({s['type'] for s in data['software']})
        resource_count = '<p id="resource-count" role="status" aria-live="polite">' + str(len(software_html)) + ' resource' + ('s' if len(software_html) != 1 else '') + '</p>'
        resource_controls = '<details class="resource-filters" open hidden><summary>Search &amp; filter</summary><div class="resource-controls"><div><label for="resource-search">Search resources</label><input id="resource-search" type="search" placeholder="Name, description, or research direction"></div><div><label for="resource-type">Type</label><select id="resource-type"><option value="">All types</option>' + ''.join('<option>' + kind + '</option>' for kind in kinds) + '</select></div></div></details>'
    resource_toolbar = '<div class="resource-toolbar">' + resource_count + '<div class="resource-view-switch" role="group" aria-label="Resource view" hidden><button type="button" data-resource-view="grid" aria-controls="resource-results" aria-pressed="true" title="Grid view"><i class="bi bi-grid" aria-hidden="true"></i> Grid</button><button type="button" data-resource-view="list" aria-controls="resource-results" aria-pressed="false" title="List view"><i class="bi bi-list-ul" aria-hidden="true"></i> List</button></div></div>'
    resource_empty = '<p id="resource-empty" hidden>No resources match these filters.</p>' if resource_controls else ''
    (out / 'software.md').write_text(raw(resource_toolbar + resource_controls + '<div class="lab-grid" id="resource-results" data-resources data-view="grid">' + ''.join(software_html) + '</div>' + resource_empty) if software_html else 'Resources will be shared here.\n', encoding='utf-8')
    if papers:
        years = sorted({p['year'] for p in papers}, reverse=True)
        kinds = sorted({p.get('type', 'article') for p in papers})
        member_papers = {person['id']: {paper['id'] for paper in member_publications(person, papers)} for person in data['people']}
        members = [person for person in data['people'] if member_papers[person['id']]]
        controls = f'<div class="publication-toolbar"><p id="paper-count" role="status" aria-live="polite">{len(papers)} publication{"s" if len(papers) != 1 else ""}</p><div class="publication-toolbar-actions"><button id="paper-featured" type="button" aria-pressed="false" hidden><span aria-hidden="true">★</span> Featured only</button>' + pi_scholar_links(data['people']) + '</div></div>'
        controls += '<details class="publication-filters" open><summary>Search &amp; filter</summary><div class="publication-controls"><div><label for="paper-search">Search publications</label><input id="paper-search" type="search" placeholder="Title, author, or venue"></div><div><label for="paper-year">Year</label><select id="paper-year"><option value="">All years</option>' + ''.join(f'<option>{year}</option>' for year in years) + '</select></div><div><label for="paper-type">Type</label><select id="paper-type"><option value="">All types</option>' + ''.join(f'<option>{kind}</option>' for kind in kinds) + '</select></div></div></details>'
        if members:
            member_control = '<div class="publication-member-filter"><label for="paper-member">Lab member</label><select id="paper-member"><option value="">All members</option>' + ''.join('<option value="' + esc(person['id']) + '">' + esc(person['name']) + '</option>' for person in members) + '</select></div>'
            controls = controls.replace('</div></details>', member_control + '</div></details>')
        publication_md = raw(controls + ('<p class="paper-author-key">Lab members in <strong>bold</strong>.</p>' if publication_author_names(cfg, data['people']) else '') + '<div data-publications>' + ''.join(paper_html(p, altmetric=cfg.get('publications', {}).get('altmetric', False), show_sources=cfg.get('provenance', {}).get('show_links', True), lab_authors=publication_author_names(cfg, data['people']), member_ids=[person['id'] for person in members if p['id'] in member_papers[person['id']]]) for p in papers) + '</div><p id="paper-empty" hidden>No publications match these filters.</p>')
        publication_md += '\n[Download BibTeX](../assets/publications.bib) · [Download citation data (CSL JSON)](../assets/publications.json)\n'
    else:
        publication_md = 'Publications will appear here after they have been verified and curated.\n'
    (out / 'publications.md').write_text(publication_md, encoding='utf-8')
    (stage / 'assets/publications.bib').write_text(bibliography(papers), encoding='utf-8')
    csl = [{'id': p['id'], 'type': 'article-journal' if p.get('type', 'article') == 'article' else 'document', 'title': p['title'], 'author': [{'literal': n} for n in (p['authors'] if isinstance(p['authors'], list) else [p['authors']])], 'issued': {'date-parts': [[p['year']]]}, 'container-title': p['venue'], 'DOI': normalize_doi(p.get('doi')), 'URL': p.get('url', '')} for p in papers]
    (stage / 'assets/publications.json').write_text(json.dumps(csl, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    department = '<p>' + esc(lab['department']) + '</p>' if lab.get('department') else ''
    (out / 'contact.md').write_text(raw('<p class="lede">' + esc(lab['description']) + '</p>' + department + '<p>' + esc(lab['institution']) + '</p><p>' + link(lab['email'], 'mailto:' + lab['email']) + '</p>'), encoding='utf-8')
    (out / 'contact-link.md').write_text(raw('<p>' + link('Contact the lab →', 'mailto:' + lab['email']) + '</p>'), encoding='utf-8')
    for project in data['projects']:
        path = stage / project['path']
        with path.open('a', encoding='utf-8') as handle:
            handle.write(relationships('projects', project['id'], data, prefix='../../'))
            if project.get('source_url'):
                handle.write(raw(source(project, cfg.get('provenance', {}).get('show_links', True))))
            for key, label in (('collaborators', 'Collaborators'), ('funders', 'Funding')):
                if project.get(key):
                    handle.write(raw(f'<section><h2>{label}</h2><ul>' + ''.join('<li>' + esc(value) + '</li>' for value in project[key]) + '</ul></section>'))
    web = qcfg['website']
    web.update({'title': lab['name'], 'description': lab['description'], 'site-url': lab.get('site_url') or web.get('site-url') or 'https://example.org/researchlabfolio/'})
    navbar_title = False if brand.get('logo') and web['navbar'].get('title') is False else lab.get('short_name', lab['name'])
    web['navbar'].update({'title': navbar_title, 'left': [{'href': f'pages/{name}.qmd', 'text': LABELS[name]} for name in cfg.get('navigation', LABELS) if name not in ('blog', 'teaching') or cfg.get(name, {}).get('enabled', False)]})
    if brand.get('logo'):
        web['navbar']['logo'] = brand['logo']
        web['navbar']['logo-alt'] = lab['name']
    if brand.get('favicon'):
        web['favicon'] = brand['favicon']
    web['page-footer'] = {'center': academic_footer(cfg, data['people']), 'border': True}
    (stage / 'pages/news.xml').write_bytes(news_feed(lab, web['site-url'], data['news']))
    qcfg['project']['resources'] = ['assets/**', 'pages/news.xml'] + ([cfg['hero']['image']] if cfg.get('hero', {}).get('image') else [])
    if community:
        qcfg['project']['resources'].extend(['framework/maps/countries-50m.json', 'framework/maps/*-LICENSE',
                                           'framework/vendor/*.js', 'framework/vendor/*-LICENSE', 'framework/includes/community-map.js'])
    if cfg.get('recruitment', {}).get('image'):
        qcfg['project']['resources'].append(cfg['recruitment']['image'])
    qcfg['project']['resources'].extend(slide['image'] for slide in cfg.get('recruitment', {}).get('slides', []))
    qcfg['project']['render'].append('blog/*.qmd')
    if not cfg.get('teaching', {}).get('enabled', False):
        qcfg['project']['render'].append('!pages/teaching.qmd')
    if cfg.get('blog', {}).get('enabled', False):
        (stage / 'pages/blog.xml').write_bytes(news_feed(lab, web['site-url'], published_posts(data['blog']), section='blog'))
        qcfg['project']['resources'].append('pages/blog.xml')
    else:
        qcfg['project']['render'].append('!pages/blog.qmd')
    qcfg['project']['render'].extend('!' + blog_page_url(post['path']) for post in data['blog'] if post.get('draft', False) or not cfg.get('blog', {}).get('enabled', False))
    if cname.exists():qcfg['project']['resources'].append('CNAME')
    qcfg['project']['output-dir'] = '_site'
    qcfg['project']['render'].extend('!' + item['path'] for item in data['projects'] if not item['detail_page'])
    qcfg['project']['render'].extend('!' + item['path'] for item in data['news'] if not item['detail_page'])
    if len(cfg.get('recruitment', {}).get('slides', [])) > 1 and cfg.get('homepage', {}).get('recruitment', True) and lab.get('recruitment'):
        includes = qcfg['format']['html'].get('include-after-body', [])
        qcfg['format']['html']['include-after-body'] = ([includes] if isinstance(includes, str) else includes) + ['framework/includes/recruitment-gallery.html']
    if courses and cfg.get('teaching', {}).get('search', True):
        includes = qcfg['format']['html'].get('include-after-body', [])
        qcfg['format']['html']['include-after-body'] = ([includes] if isinstance(includes, str) else includes) + ['framework/includes/teaching.html']
    if cfg.get('publications', {}).get('altmetric', False):
        includes = qcfg['format']['html'].get('include-after-body', [])
        qcfg['format']['html']['include-after-body'] = ([includes] if isinstance(includes, str) else includes) + ['framework/includes/altmetric.html']
    qcfg['_lab_toc'] = cfg.get('toc', {})
    qcfg = stage_main_pages(stage, qcfg)
    (stage / '_quarto.yml').write_text(yaml.safe_dump(qcfg, sort_keys=False, allow_unicode=True), encoding='utf-8')
    (stage / 'lab.yml').write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return stage

def relationships(entity, key, data, prefix, as_html=False, heading_level=2, exclude_targets=()):
    selected = next(p for p in data[entity] if p['id'] == key)
    blocks = []
    for target, label in (('projects', 'Related research'), ('people', 'People'), ('software', 'Resources'), ('publications', 'Publications')):
        if target == entity or target in exclude_targets:
            continue
        matches = [p for p in data[target] if p['id'] in selected.get(target, []) or key in p.get(entity, [])]
        if target == 'publications':
            matches = [p for p in matches if p.get('status', 'confirmed') == 'confirmed']
        if not matches:
            continue
        links = []
        for p in matches:
            if target == 'projects':
                href = research_href(p)
            elif target == 'people':
                href = 'people/' + p['id'] + '.qmd'
            else:
                href = 'pages/' + ('software' if target == 'software' else 'publications') + '.qmd#' + p['id']
            links.append('<li>' + link(title(p), prefix + href) + '</li>')
        blocks.append(f'<section class="related"><h{heading_level}>{label}</h{heading_level}><ul>' + ''.join(links) + '</ul></section>')
    return (''.join(blocks) if as_html else raw(''.join(blocks))) if blocks else ''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        _, data = validate(args.site)
        print('Validated:', ', '.join(f'{len(v)} {k}' for k,v in data.items()))
    else:
        print('Prepared:', prepare(args.site))

if __name__ == '__main__':
    main()
