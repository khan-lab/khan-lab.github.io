"""Validated blog content and explicit member-content associations. No network I/O."""
import datetime as dt
import re
from content import frontmatter, text_fields, require, url, author_key, normalize_doi, ContentError


def read_posts(root, people):
    known = {person['id'] for person in people if isinstance(person, dict) and isinstance(person.get('id'), str)}
    posts = []
    for path in sorted((root / 'content/blog').glob('*.qmd')):
        item, body = frontmatter(path)
        text_fields(item, ['id', 'title', 'description'], path)
        item = dict(item, body=body, path=path.relative_to(root).as_posix())
        try:
            dt.date.fromisoformat(str(item.get('date', '')))
        except ValueError as exc:
            raise ContentError(f'{path}: date must be ISO YYYY-MM-DD') from exc
        require(isinstance(item.get('draft', False), bool), path, 'draft must be boolean')
        for key in ('toc', 'cite', 'image_cover'):
            if key in item:
                require(isinstance(item[key], bool), path, key + ' must be boolean')
        if 'doi' in item:
            require(isinstance(item['doi'], str), path, 'doi must be text')
            item['doi'] = normalize_doi(item['doi'])
            require(not item['doi'] or bool(re.fullmatch(r'10\.\d{4,9}/[^\s<>]+', item['doi'])), path, 'invalid DOI')
        for field in ('categories', 'tags'):
            values = item.get(field, [] if field == 'tags' else None)
            require(isinstance(values, list) and all(isinstance(v, str) and v.strip() for v in values), path, f'{field} must be a list of nonempty text values')
            require(field != 'categories' or bool(values), path, 'categories must not be empty')
            require(len(values) == len({author_key(v) for v in values}), path, f'duplicate {field}')
        authors = item.get('authors')
        require(isinstance(authors, list) and bool(authors), path, 'authors must be a nonempty list of member IDs or guest mappings')
        seen = set()
        for author in authors:
            member = author if isinstance(author, str) else author.get('person') if isinstance(author, dict) else None
            if member is not None:
                require(isinstance(member, str) and member in known, path, f'unknown member author {member!r}')
                require(isinstance(author, str) or set(author) == {'person'}, path, 'member author mappings accept only person; edit member details in people.yml')
                key = ('person', member)
            else:
                text_fields(author, ['name'], path)
                require(set(author) <= {'name', 'affiliation', 'bio', 'website'}, path, 'unknown guest author field')
                for field in ('affiliation', 'bio', 'website'):
                    require(isinstance(author.get(field, ''), str), path, f'guest {field} must be text')
                if author.get('website'):
                    url(author['website'], str(path) + ' guest.website')
                key = ('guest', author_key(author['name']))
            require(key not in seen, path, 'duplicate author')
            seen.add(key)
        posts.append(item)
    return posts


def published_posts(posts):
    return sorted((p for p in posts if not p.get('draft', False)), key=lambda p: (str(p['date']), p['id']), reverse=True)


def member_posts(person, posts):
    return [post for post in published_posts(posts) if any(
        (author if isinstance(author, str) else author.get('person')) == person['id'] for author in post['authors'])]


def member_publications(person, papers):
    aliases = {author_key(name) for name in person.get('publication_names', [])}
    excluded = set(person.get('exclude_publications', []))
    result = []
    for paper in papers:
        if paper.get('status', 'confirmed') != 'confirmed' or paper['id'] in excluded:
            continue
        authors = paper['authors'] if isinstance(paper['authors'], list) else [paper['authors']]
        explicit = paper['id'] in person.get('publications', []) or person['id'] in paper.get('people', [])
        if explicit or aliases.intersection(author_key(name) for name in authors):
            result.append(paper)
    return sorted(result, key=lambda p: (-p['year'], author_key(p['title'])))


def resolved_authors(post, people):
    by_id = {person['id']: person for person in people}
    result = []
    for author in post['authors']:
        member = author if isinstance(author, str) else author.get('person')
        if member:
            result.append(dict(by_id[member], person=member))
        else:
            result.append(author)
    return result
