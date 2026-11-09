"""Explicit publication discovery. Cached candidates require human inclusion before display."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import yaml
from content import ROOT, ContentError, load, normalize_doi, records, validate
METADATA_ERRORS = (ContentError, KeyError, TypeError, ValueError, AttributeError, IndexError)


def identity(p):
    doi = normalize_doi(p.get('doi'))
    if doi:
        return 'doi:' + doi
    return 'title:' + ' '.join(p['title'].lower().split()) + ':' + str(p['year'])


def deduplicate(items):
    merged = {}
    for original in items:
        p = dict(original)
        p['doi'] = normalize_doi(p.get('doi'))
        key = identity(p)
        if key in merged:
            previous = merged[key]
            provenance = sorted(set(previous.get('sources', [])) | set(p.get('sources', [])))
            # Keep curated fields/stable IDs when a cache entry already exists.
            for field, value in p.items():
                if field not in previous or not previous[field]:
                    previous[field] = value
            previous['sources'] = provenance
        else:
            merged[key] = p
    return sorted(merged.values(), key=lambda p: (-p['year'], p['id']))


def get_json(url):
    headers = {'Accept': 'application/json', 'User-Agent': 'ResearchLabFolio/0.1 (publication curation; https://github.com/khan-lab/researchlabfolio)'}
    # Public record access can be credential-free; honor optional API credentials.
    if url.startswith('https://pub.orcid.org/') and os.environ.get('ORCID_ACCESS_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['ORCID_ACCESS_TOKEN']
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                # Avoid leaking API keys from a URL in exception messages.
                status = f' (HTTP {exc.code})' if isinstance(exc, HTTPError) else ''
                raise ContentError(f'Publication source request failed after 3 attempts{status}; cache unchanged') from None
            time.sleep(2**attempt)


def candidate(title, names, year, venue, doi='', kind='article', source_url=''):
    key = normalize_doi(doi) or source_url or title + str(year)
    return {'id': 'work-' + hashlib.sha256(key.encode()).hexdigest()[:16], 'title': title, 'authors': names or ['Unknown author'], 'year': int(year), 'venue': venue or 'Venue not supplied', 'doi': normalize_doi(doi), 'type': kind, 'status': 'candidate', 'source_url': source_url, 'sources': [source_url] if source_url else []}


def from_openalex(work):
    names = [a['author']['display_name'] for a in work.get('authorships', []) if a.get('author', {}).get('display_name')]
    location = work.get('primary_location') or {}
    venue = (location.get('source') or {}).get('display_name', '')
    return candidate(work.get('title') or work.get('display_name') or 'Untitled work', names, work['publication_year'], venue, work.get('doi', ''), 'preprint' if work.get('type') == 'preprint' else 'article', work['id'])


def openalex(author, fetch=get_json):
    cursor = '*'
    results = []
    for _ in range(100):
        params = {'filter': f'author.id:{author}', 'per-page': 200, 'cursor': cursor}
        if os.environ.get('OPENALEX_API_KEY'):
            params['api_key'] = os.environ['OPENALEX_API_KEY']
        data = fetch('https://api.openalex.org/works?' + urlencode(params))
        results.extend(from_openalex(p) for p in data['results'])
        cursor = data.get('meta', {}).get('next_cursor')
        if not cursor:
            return results
    raise ContentError('OpenAlex exceeded 100 pages; cache unchanged rather than truncated')


def orcid(author, fetch=get_json, diagnostics=None):
    data = fetch(f'https://pub.orcid.org/v3.0/{author}/works')
    result = []
    for group in data.get('group', []):
        for work in group.get('work-summary', []):
            try:
                ids = work.get('external-ids', {}).get('external-id', [])
                doi = next((x['external-id-value'] for x in ids if x.get('external-id-type') == 'doi'), '')
                year = ((work.get('publication-date') or {}).get('year') or {}).get('value')
                if not year:
                    raise ContentError(f'ORCID work {work.get("put-code")} has no year; resolve at source or import manually')
                venue = (work.get('journal-title') or {}).get('value', '')
                result.append(candidate(work['title']['title']['value'], [], year, venue, doi, 'preprint' if work.get('type') == 'preprint' else 'article', f'https://orcid.org/{author}/work/{work["put-code"]}'))
            except METADATA_ERRORS as exc:
                if diagnostics is None: raise
                failure(diagnostics, 'ORCID', author + '/work/' + str(work.get('put-code', 'unknown') if isinstance(work, dict) else 'unknown'), exc)
    return result


def crossref(doi, fetch=get_json):
    doi = normalize_doi(doi)
    data = fetch('https://api.crossref.org/works/' + quote(doi, safe=''))['message']
    require_doi = normalize_doi(data.get('DOI'))
    if require_doi != doi:
        raise ContentError('Crossref returned a mismatched DOI; cache unchanged')
    dates = data.get('published') or data.get('issued') or data.get('created')
    names = [' '.join([a.get('given', ''), a.get('family', '')]).strip() or a.get('name', 'Unknown author') for a in data.get('author', [])]
    return candidate(data['title'][0], names, dates['date-parts'][0][0], (data.get('container-title') or ['Venue not supplied'])[0], doi, 'preprint' if data.get('type') == 'posted-content' else 'article', 'https://doi.org/' + doi)


def redacted(value):
    value = str(value)
    for key, secret in os.environ.items():
        if secret and len(secret) >= 4 and any(part in key.upper() for part in ('TOKEN', 'SECRET', 'API_KEY', 'PASSWORD')):
            value = value.replace(secret, '[redacted]')
    return value


def failure(report, source, identifier, exc):
    message = str(exc) if isinstance(exc, ContentError) else 'Provider returned incomplete or invalid metadata.'
    report['errors'].append({'source': source, 'identifier': redacted(identifier), 'message': redacted(message),
                             'action': 'Check this identifier and source, then retry; the previous cache is retained.'})


def inspect_publications(root):
    cfg, data = validate(root)
    papers = data['publications']
    unresolved = unresolved_records(papers)
    return {'format': 1, 'status': 'checked', 'cache_changed': False,
            'counts': {'cached': len(records(root / 'content/publications/cache.yml')), 'confirmed': sum(p.get('status', 'confirmed') == 'confirmed' for p in papers),
                       'candidates': sum(p.get('status', 'confirmed') == 'candidate' for p in papers), 'excluded': sum(p.get('status', 'confirmed') == 'excluded' for p in papers)},
            'sources': [], 'added': [], 'updated': [], 'retained': [], 'unresolved': unresolved,
            'excluded': [p['id'] for p in papers if p.get('status') == 'excluded'], 'warnings': [], 'errors': []}


def unresolved_records(papers):
    unresolved = []
    for paper in papers:
        missing = [field for field, placeholder in (('authors', ['Unknown author']), ('venue', 'Venue not supplied'), ('title', 'Untitled work')) if paper.get(field) == placeholder]
        if missing:
            unresolved.append({'id': paper['id'], 'status': paper.get('status', 'confirmed'), 'fields': missing,
                               'action': 'Review source metadata or supply verified manual values.'})
    return unresolved


def synchronize(root, fetch=get_json, report=None):
    root = Path(root)
    cfg, _ = validate(root)
    details = inspect_publications(root)
    if report is not None:
        report.clear(); report.update(details); details = report
    opts = cfg.get('publications', {})
    cachepath = root / 'content/publications/cache.yml'
    old = records(cachepath)
    if not opts.get('openalex') and not opts.get('orcid'):
        details['status'] = 'not-configured'
        details['retained'] = [p['id'] for p in old]
        return old, False
    found = []
    for key, label, discover in (('openalex', 'OpenAlex', openalex), ('orcid', 'ORCID', orcid)):
        if not opts.get(key): continue
        count = len(found); prior_errors = len(details['errors'])
        try:
            found.extend(discover(opts[key], fetch, details) if key == 'orcid' else discover(opts[key], fetch))
        except METADATA_ERRORS as exc:
            failure(details, label, opts[key], exc)
        details['sources'].append({'source': label, 'identifier': opts[key], 'records': len(found) - count,
                                   'status': 'failed' if len(details['errors']) > prior_errors else 'ok'})
    details['counts']['discovered'] = len(found)
    found = deduplicate(found)
    for p in found:
        if p.get('doi'):
            try:
                enriched = crossref(p['doi'], fetch)
                for field in ('title', 'authors', 'year', 'venue', 'type'):
                    p[field] = enriched[field]
                p['sources'] = sorted(set(p['sources'] + enriched['sources']))
            except METADATA_ERRORS as exc:
                failure(details, 'Crossref', p['doi'], exc)
    if details['errors']:
        details['status'] = 'failed'
        raise ContentError('Publication sync failed; cache unchanged. ' + '; '.join(item['identifier'] + ': ' + item['message'] for item in details['errors']))
    result = deduplicate(old + found)
    previous = {identity(p): p for p in old}
    details['added'] = [p['id'] for p in result if identity(p) not in previous]
    details['updated'] = [p['id'] for p in result if identity(p) in previous and p != previous[identity(p)]]
    details['retained'] = [p['id'] for p in result if identity(p) in previous and p == previous[identity(p)]]
    details['status'] = 'ready' if result != old else 'unchanged'
    details['unresolved'] = unresolved_records(result)
    details['counts'].update({'result': len(result), 'added': len(details['added']), 'updated': len(details['updated']),
                              'retained': len(details['retained']), 'unique_discovered': len(found),
                              'duplicates_removed': details['counts']['discovered'] - len(found)})
    return result, result != old


def summary(report):
    lines = ['Publication diagnostics: ' + report['status'], ', '.join(f'{key}: {value}' for key, value in report.get('counts', {}).items())]
    for key in ('added', 'updated', 'excluded'):
        if report.get(key): lines.append(key.title() + ': ' + ', '.join(report[key]))
    for item in report.get('unresolved', []): lines.append('Review ' + item['id'] + ': ' + ', '.join(item['fields']))
    for item in report.get('errors', []): lines.append('ERROR ' + item['source'] + ' ' + item['identifier'] + ': ' + item['message'])
    lines.append('Cache updated.' if report.get('cache_changed') else 'Cache unchanged.')
    return '\n'.join(lines)


def save_report(root, report, path=None):
    root = Path(root).resolve()
    destination = Path(path) if path is not None else Path('.scratch/reports/publications.json')
    destination = destination if destination.is_absolute() else root / destination
    if destination.is_symlink() or not destination.resolve().is_relative_to(root / '.scratch/reports'):
        raise ContentError('Publication reports must be inside the site’s .scratch/reports/ directory.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    if temporary.is_symlink(): raise ContentError('Unsafe publication report path.')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(destination)
    return destination


def run_sync(root, offline=False, dry_run=False, report_path=None, fetch=get_json):
    from transactions import commit_changes, site_lock, validate_changes
    root = Path(root).resolve()
    # Validate the report destination before any cache edit.
    report = {'format': 1, 'status': 'checking', 'cache_changed': False, 'counts': {},
              'errors': [], 'warnings': [], 'unresolved': [], 'sources': [], 'added': [], 'updated': [], 'excluded': []}
    save_report(root, report, report_path)
    with site_lock(root):
        try:
            report.update(inspect_publications(root))
            if offline:
                report['status'] = 'offline'
            else:
                result, changed = synchronize(root, fetch, report)
                text = yaml.safe_dump(result, sort_keys=False, allow_unicode=True)
                if changed:
                    _, proposed = validate_changes(root, {'content/publications/cache.yml': text})
                    papers = proposed['publications']
                    report['excluded'] = [paper['id'] for paper in papers if paper.get('status') == 'excluded']
                    report['unresolved'] = unresolved_records(papers)
                    for label, state in (('confirmed', 'confirmed'), ('candidates', 'candidate'), ('excluded', 'excluded')):
                        report['counts'][label] = sum(paper.get('status', 'confirmed') == state for paper in papers)
                if changed and not dry_run:
                    commit_changes(root, {'content/publications/cache.yml': text})
                    report['cache_changed'] = True
                    report['counts']['cached'] = len(result)
                    report['status'] = 'updated'
                elif dry_run: report['status'] = 'dry-run'
            report['counts']['errors'] = len(report['errors'])
            report['counts']['unresolved'] = len(report['unresolved'])
        except METADATA_ERRORS as exc:
            report['status'] = 'failed'
            if not report['errors']: failure(report, 'validation', 'site', exc)
            report['counts']['errors'] = len(report['errors'])
            save_report(root, report, report_path)
            raise ContentError(summary(report)) from None
        save_report(root, report, report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=ROOT)
    parser.add_argument('--offline', action='store_true', help='Validate existing cache without API requests')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--report', type=Path, default=None, help='JSON path inside SITE/.scratch/reports/')
    args = parser.parse_args()
    root = args.site.resolve()
    report = run_sync(root, args.offline, args.dry_run, args.report)
    print(summary(report))
    print('New candidates remain hidden until included in overrides.yml.')

if __name__ == '__main__':
    try:
        main()
    except (ContentError, KeyError, TypeError, ValueError) as exc:
        print(f'Sync failed: {exc}. Existing curated content retained.', file=sys.stderr)
        sys.exit(1)
