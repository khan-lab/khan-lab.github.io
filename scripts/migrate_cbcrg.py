"""Reproducible, read-only import from an explicit local public source snapshot."""
import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import yaml
from content import ROOT, normalize_doi


def read(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110), encoding='utf-8')


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def plain(value):
    return html.unescape(re.sub(r'<[^>]*>', '', value or '')).strip()


def page(path, metadata, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n' + body.strip() + '\n', encoding='utf-8')


def migrate(source, destination):
    if (destination / 'lab.yml').exists():
        raise ValueError('Destination already has lab.yml. Import into an empty directory and review differences to preserve curation.')
    sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    base = 'https://github.com/khan-lab/khan-lab.github.io/blob/' + sha + '/'
    seen_assets = {}
    def copy_asset(value):
        value = value.lstrip('/')
        origin = source / value
        if not origin.is_file():
            raise ValueError(f'Source image missing: {value}')
        relative = 'assets/migrated/' + value
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(origin, target)
        seen_assets[relative] = {'source_url': base + value, 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest()}
        return relative
    lab = {
        'lab': {'name': 'Computational Biology & Cancer Regulatory Genomics Lab', 'short_name': 'CBCRG · MBZUAI', 'tagline': 'Understanding gene regulation. Advancing precision medicine.', 'description': 'Our research bridges biology, multi-omics, machine learning, and data science to understand how gene regulation shapes health and diseases like cancer.', 'institution': 'Mohamed bin Zayed University of Artificial Intelligence', 'email': 'aziz.khan@mbzuai.ac.ae', 'site_url': '', 'recruitment': 'We are building a collaborative team of researchers working across computational biology, genomics and AI. Explore joining the lab.'},
        'branding': {'logo': '', 'favicon': '', 'colors': {'primary': '#2B94C8', 'secondary': '#596779'}, 'fonts': {'headings': 'Source Serif 4', 'body': 'Source Sans 3'}},
        'navigation': ['research', 'people', 'publications', 'software', 'news', 'join', 'contact'],
        'homepage': {'research': True, 'publications': True, 'software': True, 'news': True, 'recruitment': True},
        'publications': {'orcid': '0000-0002-6459-6224', 'openalex': ''},
        'provenance': {'show_links': False, 'source_url': base + 'index.md', 'source_commit': sha, 'accessed': '2026-10-31'}}
    # Tagline is an editorial summary of the public research statement; no new project claims.
    write(destination / 'lab.yml', lab)
    write(destination / '_quarto.yml', {'website': {'site-url': 'https://example.org/cbcrg/'}, 'format': {'html': {'include-in-header': [{'text': '<meta name="robots" content="noindex, nofollow">'}]}}})
    people = []
    for path in sorted((source / '_members').glob('*.md')):
        _, head, body = path.read_text(encoding='utf-8').split('---', 2)
        p = yaml.safe_load(head)
        position = p.get('description', 'Principal Investigator')
        role = 'pi' if p['role'] == 'principal-investigator' else 'masters' if position == 'MS Student' else 'visitor' if 'Visiting' in position else 'staff'
        if p.get('alumni'):
            role = 'alumni'
        body = re.sub(r'{%.*?%}', '', body, flags=re.S)
        body = re.sub(r'{:[^}]*}', '', body)
        body = body.replace('](/tools)', '](../pages/software.qmd)')
        body = body.replace(' -->', '').strip()
        links = {}
        for key, value in p.get('links', {}).items():
            if key in ('email', 'orcid'):
                continue
            if value.startswith(('https://', 'http://')):
                links[key] = value
            elif key == 'google-scholar':
                links[key] = 'https://scholar.google.com/citations?user=' + value
            elif key in ('github', 'linkedin', 'bluesky', 'twitter'):
                links[key] = {'github': 'https://github.com/', 'linkedin': 'https://www.linkedin.com/in/', 'bluesky': 'https://bsky.app/profile/', 'twitter': 'https://twitter.com/'}[key] + value
            else:
                raise ValueError(f'Unmapped member link: {key}')
        summary = plain(re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', body.split('\n\n')[0]).replace('**', ''))
        person = {'id': path.stem, 'name': p['name'], 'role': role, 'position': position, 'summary': summary[:260].rsplit(' ', 1)[0] + '…' if len(summary) > 260 else summary, 'bio': body, 'photo': copy_asset(p['image']), 'links': links, 'projects': [], 'source_url': base + '_members/' + path.name}
        for key in ('orcid', 'email'):
            if p.get('links', {}).get(key):
                person[key] = p['links'][key]
        people.append(person)
    write(destination / 'content/people/people.yml', people)
    tools = []
    for item in read(source / '_data/tools.yaml'):
        repo = item.get('repo', '')
        if repo and not repo.startswith('https://'):
            repo = 'https://github.com/' + repo
        resource_type = 'database' if 'database' in item.get('tags', []) else 'software' if 'software' in item.get('tags', []) or 'web-server' in item.get('tags', []) else 'education' if item['title'] == 'ECRcentral' else 'dataset'
        tools.append({'id': slug(item['title']), 'name': item['title'], 'type': resource_type, 'description': item.get('description') or item['subtitle'], 'url': item['link'], 'repo': repo, 'image': copy_asset(item['image']), 'image_alt': item['title'] + ' project illustration', 'featured': item.get('group') == 'featured', 'projects': [], 'source_url': base + '_data/tools.yaml'})
    write(destination / 'content/software/software.yml', tools)
    news = read(source / '_data/news.yaml')
    for item in news:
        news_id = str(item['date']) + '-' + slug(item['title'])
        description = plain(item['description'])
        metadata = {'id': news_id, 'title': item['title'], 'date': item['date'], 'categories': ['publication' if 'publication' in item['title'].lower() or 'preprint' in item['title'].lower() else 'lab-news'], 'description': description, 'source_url': base + '_data/news.yaml'}
        body = item['description'].replace('href="/join"', 'href="../../pages/join.html"')
        if item.get('url'):
            metadata['url'] = item['url']
            body += '\n\n[Further details](' + item['url'] + ')'
        page(destination / 'content/news' / (news_id + '.qmd'), metadata, body)
    # Preserve all source citations as candidates; only explicit lab-news DOIs are included.
    citations = read(source / '_data/citations.yaml')
    confirmed = set()
    for item in news:
        if 'publication' in item['title'].lower() or 'preprint' in item['title'].lower():
            if item.get('url', '').startswith('https://doi.org/'):
                confirmed.add(normalize_doi(item['url']))
            confirmed.update(normalize_doi(v.rstrip('.')) for v in re.findall(r'doi:\s*(10\.\d{4,9}/[A-Za-z0-9./\-]+)', item['description']))
            for citation in citations:
                known_doi = normalize_doi(citation['id'][4:]) if citation['id'].startswith('doi:') else ''
                if known_doi and known_doi in item['description'] + str(item.get('url', '')):
                    confirmed.add(known_doi)
    cache, include = [], []
    for p in citations:
        doi = normalize_doi(p['id'][4:]) if p['id'].startswith('doi:') else ''
        key = 'work-' + hashlib.sha256(p['id'].encode()).hexdigest()[:16]
        record = {'id': key, 'title': p['title'], 'authors': p['authors'], 'year': int(str(p['date'])[:4]), 'venue': p.get('publisher') or 'Venue not supplied', 'type': 'preprint' if doi.startswith(('10.1101/', '10.64898/', '10.21203/')) else 'article', 'doi': doi, 'url': 'https://doi.org/' + doi if doi else p['link'], 'status': 'candidate', 'featured': doi in confirmed and not doi.startswith('10.1101/'), 'source_url': base + '_data/citations.yaml', 'source_id': p['id'], 'sources': [base + '_data/citations.yaml'], 'projects': []}
        cache.append(record)
        if doi in confirmed:
            include.append(key)
    write(destination / 'content/publications/cache.yml', cache)
    write(destination / 'content/publications/manual.yml', [])
    write(destination / 'content/publications/overrides.yml', {'include': include, 'exclude': [], 'overrides': {}})
    # Source-derived directions, not invented funded projects or affiliations.
    directions = [
        ('gene-regulation', 'Gene regulation and cancer', 'Understanding how gene regulation shapes health and diseases like cancer.', 'Our research bridges biology, multi-omics, machine learning, and data science to understand how gene regulation shapes health and diseases like cancer. We aim to advance precision medicine through innovative, collaborative research — using diverse multi-omic datasets and more complete, inclusive reference genomes.'),
        ('open-science', 'Open science and reproducibility', 'Open tools, software and resources for collaborative research.', 'We strongly believe in global access to open and reproducible science. Our tools, software, and resources are openly licensed and freely available for all to use and build upon.')]
    for key, name, description, body in directions:
        page(destination / 'content/research' / (key + '.qmd'), {'id': key, 'title': name, 'description': description, 'featured': True, 'people': [], 'publications': [], 'software': [], 'source_url': base + 'index.md'}, body)
    jointext = (source / 'join/index.md').read_text().split('---', 2)[2]
    jointext = re.sub(r'#.*?Join the Team', '', jointext, count=1)
    jointext = jointext.replace('{{ site.baseurl }}/contact', 'contact.qmd')
    page(destination / 'pages/join.qmd', {'title': 'Join the team'}, 'The opportunities below were listed on the source website at the time of migration. Confirm availability and deadlines with the lab and institution.\n\n' + jointext)
    page(destination / 'pages/contact.qmd', {'title': 'About & Contact'}, '{{< include ../_generated/contact.md >}}\n\nThe CBCRG Lab is part of the Computational Biology Department at MBZUAI, Masdar City, Abu Dhabi, UAE. The public contact page lists the first floor of Building 1B.\n\n[Campus map](https://maps.app.goo.gl/PE5hPbBgajcbfkfn6)\n\n## Our mission\n\nWe are training and building a collaborative team of responsible researchers united by a shared vision. We are committed to create an inclusive environment and recognize that diversity — in people, ideas, and data — is essential for scientific creativity and discovery.')
    write(destination / 'assets/provenance.yml', seen_assets)
    shutil.copy(source / 'LICENSE.md', destination / 'SOURCE_LICENSE.md')
    inventory = {'source_repository': 'https://github.com/khan-lab/khan-lab.github.io', 'source_commit': sha, 'accessed': '2026-10-31', 'counts': {'people': len(people), 'resources': len(tools), 'news': len(news), 'publication_candidates': len(cache), 'confirmed_from_news': len(include), 'source_derived_research_directions': len(directions), 'assets': len(seen_assets)}, 'excluded_template_posts': [p.name for p in sorted((source / '_posts').glob('*.md'))], 'unmatched_news_dois': sorted(confirmed - {p['doi'] for p in cache}), 'notes': ['Publication metadata preserved from source cache, not independently re-enriched.', 'PI publication history remains unpublished unless explicitly supported by lab news.', 'Member project assignments, funding and collaborators not inferred.', 'Source configuration khanlab.io differs from public khanlab.bio; source provenance retained.', 'Migration includes public photos for local review; source BSD license retained; confirm photo rights before public release.']}
    write(destination / 'migration.yml', inventory)
    print(json.dumps(inventory, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, default=ROOT / 'examples/cbcrg')
    args = parser.parse_args()
    migrate(args.source.resolve(), args.destination.resolve())
