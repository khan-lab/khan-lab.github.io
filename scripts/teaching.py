"""Validated teaching activities and chronological, independently credited offerings."""
from datetime import date
import hashlib
import math
import re
from content import load, require, text_fields, url

TYPES = {'course': 'Course', 'workshop': 'Workshop', 'guest-lecture': 'Guest lecture'}
TEXT_FIELDS = ('code', 'institution', 'description', 'teaching_role', 'duration')
OVERRIDES = set(TEXT_FIELDS) | {'type', 'people', 'instructors', 'credits'}


def validate_details(record, where, person_ids):
    for key in TEXT_FIELDS:
        require(isinstance(record.get(key, ''), str), where + '.' + key, 'must be plain text')
    require(isinstance(record.get('type', 'course'), str) and record.get('type', 'course') in TYPES,
            where + '.type', 'expected course, workshop or guest-lecture')
    people = record.get('people', [])
    require(isinstance(people, list) and all(isinstance(value, str) for value in people), where + '.people', 'expected instructor IDs')
    require(len(people) == len(set(people)), where + '.people', 'duplicate instructor ID')
    require(set(people) <= person_ids, where + '.people', f'unresolved people references: {set(people) - person_ids}')
    instructors = record.get('instructors', [])
    require(isinstance(instructors, list), where + '.instructors', 'expected a list of external instructors')
    for index, instructor in enumerate(instructors):
        label = f'{where}.instructors[{index}]'
        text_fields(instructor, ['name'], label)
        require(set(instructor) <= {'name', 'url'}, label, 'expected name and optional url; use people for lab members')
        if 'url' in instructor:
            url(instructor['url'], label + '.url')
    credits = record.get('credits', '')
    require(isinstance(credits, str) or (type(credits) is int and credits > 0) or (type(credits) is float and math.isfinite(credits) and credits > 0),
            where + '.credits', 'expected plain text or a positive finite number; omit unknown credits')
    links = record.get('links', {})
    require(isinstance(links, dict), where + '.links', 'links must map labels to HTTP(S) URLs')
    seen_labels = set()
    for name, destination in links.items():
        require(isinstance(name, str) and bool(name.strip()), where + '.links', 'link labels must be nonempty text')
        normalized = name.strip().casefold()
        require(normalized not in seen_labels, where + '.links', 'duplicate case-insensitive link label')
        seen_labels.add(normalized)
        url(destination, f'{where}.links.{name}')


def offering_details(course, offering):
    """Offering fields override course defaults; labelled links merge case-insensitively."""
    result = {key: value for key, value in course.items() if key != 'offerings'}
    result.update(offering)
    links = {}
    for name, destination in [*course.get('links', {}).items(), *offering.get('links', {}).items()]:
        links[name.strip().casefold()] = (name, destination)
    result['links'] = dict(links.values())
    result.setdefault('type', 'course')
    return result


def read_courses(root, people):
    path = root / 'content/teaching/courses.yml'
    courses = load(path, [])
    require(isinstance(courses, list), path, 'expected a list of courses')
    person_ids = {person['id'] for person in people if isinstance(person, dict) and isinstance(person.get('id'), str)}
    for index, course in enumerate(courses):
        where = f'{path}[{index}]'
        text_fields(course, ['id', 'title'], where)
        require(not ({'date', 'end_date'} & set(course)), where, 'put exact dates inside offerings')
        validate_details(course, where, person_ids)
        offerings = course.get('offerings')
        require(isinstance(offerings, list) and bool(offerings), where, 'offerings must be a nonempty list')
        seen, anchors = set(), set()
        for number, offering in enumerate(offerings):
            label = f'{where}.offerings[{number}]'
            require(isinstance(offering, dict), label, 'expected an offering mapping')
            require(set(offering) <= OVERRIDES | {'term', 'year', 'links', 'date', 'end_date'}, label, 'unknown offering field')
            require(type(offering.get('year')) is int and 1600 <= offering['year'] <= 2200, label, 'year must be an integer in 1600..2200')
            require(isinstance(offering.get('term', ''), str), label + '.term', 'must be plain text')
            validate_details(offering, label, person_ids)
            effective = offering_details(course, offering)
            validate_details(effective, label, person_ids)
            for key in ('date', 'end_date'):
                if key not in offering:
                    continue
                value = offering[key]
                require(type(value) is date or (isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)), label + '.' + key, 'expected an ISO YYYY-MM-DD date')
                try:
                    parsed = date.fromisoformat(str(value))
                except ValueError:
                    require(False, label + '.' + key, 'invalid calendar date')
                offering[key] = parsed.isoformat()
                if key == 'date':
                    require(parsed.year == offering['year'], label + '.date', 'date must match the offering year')
            require('end_date' not in offering or 'date' in offering, label + '.end_date', 'requires a start date')
            if 'end_date' in offering:
                require(offering['end_date'] >= offering['date'], label + '.end_date', 'must not precede the start date')
            require(bool(offering.get('term', '').strip()) or (effective['type'] == 'workshop' and 'date' in offering), label, 'provide a term, or a date for a workshop')
            identity = (offering['year'], 'date', offering['date']) if effective['type'] == 'workshop' and offering.get('date') else (offering['year'], 'term', offering.get('term', '').strip().casefold())
            anchor = offering_anchor(course, offering)
            require(identity not in seen and anchor not in anchors, label, 'duplicate term/year offering (dated workshops require distinct dates)')
            seen.add(identity)
            anchors.add(anchor)
    return courses


def offering_sort_key(offering):
    if offering.get('date'):
        value = date.fromisoformat(offering['date'])
        month, day = value.month, value.day
    else:
        # Standard northern-calendar terms; supply exact dates for other calendars.
        month = {'fall': 9, 'autumn': 9, 'summer': 6, 'spring': 3, 'winter': 1}.get(offering.get('term', '').strip().casefold(), 0)
        day = 0
    return -offering['year'], -month, -day


def sorted_offerings(course):
    return sorted(course['offerings'], key=offering_sort_key)


def chronological_offerings(courses):
    rows = [(course, offering) for course in courses for offering in course['offerings']]
    return sorted(rows, key=lambda pair: offering_sort_key(pair[1]))


def offering_anchor(course, offering):
    term = offering.get('term', '').strip().casefold()
    token = term + '|' + offering.get('date', '')
    return f'offering-{course["id"]}-{offering["year"]}-' + hashlib.sha256(token.encode()).hexdigest()[:10]


def member_courses(person, courses):
    result = []
    for course in courses:
        matches = [offering for offering in course['offerings'] if person['id'] in offering_details(course, offering).get('people', [])]
        if matches:
            latest = sorted_offerings({**course, 'offerings': matches})[0]
            anchor = course['id'] if latest == sorted_offerings(course)[0] else offering_anchor(course, latest)
            result.append({**course, 'offerings': matches, '_profile_anchor': anchor})
    return sorted(result, key=lambda course: (-max(item['year'] for item in course['offerings']), course['title'].casefold()))
