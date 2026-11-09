"""Opt-in country aggregation and a static, progressively enhanced People-page map."""
from functools import lru_cache
import html
import json
from pathlib import Path
from content import require

ASSETS=Path(__file__).resolve().parents[1]/'framework/maps'
DISPLAY_NAMES={'GB':'United Kingdom','US':'United States','AE':'United Arab Emirates'}
DEFAULTS={'enabled':False,'position':'bottom','title':'Our Global Community',
          'description':'The countries represented by our current and former lab members.',
          'include_alumni':True,'default_filter':'all','show_statistics':True,'show_member_names':False,
          'show_country_labels':'on_hover','projection':'natural_earth'}


@lru_cache(maxsize=1)
def country_reference():
    return json.loads((ASSETS/'iso-countries.json').read_text(encoding='utf-8'))


def validate_options(value):
    where='people.global_map'
    require(isinstance(value,dict),where,'expected mapping')
    require(set(value)<=set(DEFAULTS),where,'unknown global map option')
    options={**DEFAULTS,**value}
    for key in ('enabled','include_alumni','show_statistics','show_member_names'):
        require(isinstance(options[key],bool),where+'.'+key,'must be boolean')
    for key in ('title','description'):
        require(isinstance(options[key],str) and bool(options[key].strip()),where+'.'+key,'must be nonempty text')
    for key,allowed in (('position',('bottom',)),('projection',('natural_earth',)),
                        ('default_filter',('all','current','alumni')),('show_country_labels',('on_hover','none'))):
        require(isinstance(options[key],str) and options[key] in allowed,where+'.'+key,'must be one of '+', '.join(allowed))
    require(options['include_alumni'] or options['default_filter']!='alumni',where+'.default_filter','alumni requires include_alumni: true')
    return options


def normalize_countries(person,where):
    """Normalize only declared fields; never derive country information or consent."""
    if 'show_on_global_map' in person:
        require(isinstance(person['show_on_global_map'],bool),where+'.show_on_global_map','must be boolean; participation requires explicit true')
    def code(value):
        require(isinstance(value,str),where+'.countries','expected ISO 3166-1 alpha-2 text codes')
        normalized=value.strip().upper()
        require(normalized in country_reference(),where+'.countries',f'unknown ISO 3166-1 alpha-2 code {value!r}; use codes such as PK, NO, DE, CN or AE')
        return normalized
    countries=[]
    if 'countries' in person:
        require(isinstance(person['countries'],list),where+'.countries','must be a list of ISO alpha-2 codes')
        countries=list(dict.fromkeys(code(value) for value in person['countries']))
    if 'country' in person:
        alias=code(person['country'])
        require('countries' not in person or alias in countries,where+'.country','conflicts with countries; use the canonical countries list')
        if not countries:countries=[alias]
        del person['country']
    if countries or 'countries' in person:person['countries']=countries


def aggregate(people,include_alumni=True):
    result={};reference=country_reference()
    for person in people:
        if person.get('show_on_global_map') is not True:continue
        alumni=person.get('group',person['role'])=='alumni'
        if alumni and not include_alumni:continue
        for code in set(person.get('countries',[])):
            country=result.setdefault(code,{'code':code,**reference[code],
                                          'name':DISPLAY_NAMES.get(code,reference[code]['name']),'members':[]})
            if any(member['id']==person['id'] for member in country['members']):continue
            country['members'].append({'id':person['id'],'name':person['name'],'status':'alumni' if alumni else 'current',
                                       'url':'../people/'+person['id']+'.html'})
    for country in result.values():country['members'].sort(key=lambda member:member['name'].casefold())
    return sorted(result.values(),key=lambda country:country['name'].casefold())


def visible_members(country,selected):
    return [member for member in country['members'] if selected=='all' or member['status']==selected]


def statistics(countries,selected):
    return {'members':len({member['id'] for country in countries for member in visible_members(country,selected)}),
            'countries':sum(bool(visible_members(country,selected)) for country in countries)}


def country_flag(code):
    return ''.join(chr(0x1F1E6+ord(letter)-ord('A')) for letter in code)


def ranked_countries(countries,selected):
    return sorted(countries,key=lambda country:(-len(visible_members(country,selected)),country['name'].casefold()))


def country_bar(country,count,maximum,mapped):
    """Visible country name, flag, proportional bar and exact member count."""
    esc=lambda value:html.escape(str(value),quote=True)
    name=country['name']+(' — not drawn at this map scale' if country['code'] not in mapped else '')
    width=100*count/maximum if maximum else 0
    return ('<span class="community-country-bar-row"><span class="community-country-flag" aria-hidden="true">'+country_flag(country['code'])+
            '</span><span class="community-country-label" aria-hidden="true">'+esc(country['name'])+'</span><span class="community-bar-track" aria-hidden="true"><span class="community-bar-fill" data-community-bar style="width:'+f'{width:.6f}'+
            '%"></span></span><span class="community-bar-count" data-community-bar-count aria-hidden="true">'+str(count)+
            '</span></span><span class="community-country-tooltip" role="tooltip">'+esc(name)+'</span>')


def render(cfg,people):
    options=validate_options(cfg.get('people',{}).get('global_map',{}))
    if not options['enabled']:return ''
    countries=ranked_countries(aggregate(people,options['include_alumni']),'all')
    if not countries:return ''
    esc=lambda value:html.escape(str(value),quote=True)
    # The no-script/asset-failure view remains complete, even when an interactive
    # default (e.g. Current in an alumni-only lab) would otherwise be empty.
    selected='all';by_code={country['code']:country for country in countries}
    geography=json.loads((ASSETS/'country-paths.json').read_text())
    mapped={geometry['code'] for geometry in geography['geometries'] if geometry['code']}
    paths=[]
    for geometry in geography['geometries']:
        country=by_code.get(geometry['code']);members=visible_members(country,selected) if country else []
        label=country['name']+': '+str(len(members))+' '+('member' if len(members)==1 else 'members') if country else geometry['name']
        title='<title>'+esc(label)+'</title>' if members and options['show_country_labels']=='on_hover' else ''
        paths.append('<path class="community-country" data-key="'+geometry['key']+'" data-code="'+geometry['code']+'" data-active="'+str(bool(members)).lower()+'" d="'+geometry['path']+'">'+title+'</path>')
    controls='<div class="community-filters" role="group" aria-label="Community members" hidden>'
    for key,label in (('all','Everyone'),('current','Current'),('alumni','Alumni')):
        disabled=' disabled title="Alumni are excluded by site settings"' if key=='alumni' and not options['include_alumni'] else ''
        controls+='<button type="button" data-community-filter="'+key+'" aria-pressed="'+str(key==selected).lower()+'"'+disabled+'>'+label+'</button>'
    controls+='</div>'
    stats=statistics(countries,selected)
    stats_html='<p class="community-statistics" role="status" aria-live="polite"><strong data-community-stat="members">'+str(stats['members'])+'</strong> <span data-community-stat-label="members">'+('member' if stats['members']==1 else 'members')+'</span> · <strong data-community-stat="countries">'+str(stats['countries'])+'</strong> <span data-community-stat-label="countries">'+('country' if stats['countries']==1 else 'countries')+'</span></p>' if options['show_statistics'] else ''
    rows=[];opened=False;show_names=options['show_member_names']
    maximum=max(len(country['members']) for country in countries)
    for country in countries:
        members=visible_members(country,selected);current=sum(member['status']=='current' for member in members);alumni=len(members)-current
        active=bool(members);attrs=(' open' if active and not opened else '')+(' hidden' if not active else '')
        opened=opened or active
        heading=country_bar(country,len(members),maximum,mapped)
        accessible=esc(country['name']+': '+str(len(members))+' '+('member' if len(members)==1 else 'members'))
        note='<p class="community-scale-note">Available in this list; not drawn at this map scale.</p>' if country['code'] not in mapped else ''
        identity=' id="community-country-'+country['code']+'" data-country="'+country['code']+'"'
        if show_names:
            items=''
            for member in country['members']:
                hidden=' hidden' if selected!='all' and member['status']!=selected else ''
                items+='<li data-member-status="'+member['status']+'"'+hidden+'><a href="'+esc(member['url'])+'">'+esc(member['name'])+'</a><span class="community-member-status">'+('Alumni' if member['status']=='alumni' else 'Current')+'</span></li>'
            counts='<span class="community-country-counts"><span data-count="current">'+str(current)+'</span> current · <span data-count="alumni">'+str(alumni)+'</span> alumni</span>'
            rows.append('<details class="community-country-detail"'+identity+attrs+'><summary aria-label="'+accessible+'">'+heading+'</summary>'+counts+'<ul>'+items+'</ul>'+note+'</details>')
        else:
            hint=' title="Available in this list; not drawn at this map scale."' if note else ''
            rows.append('<div class="community-country-name" role="group" tabindex="0" aria-label="'+accessible+'"'+identity+hint+(' hidden' if not active else '')+'>'+heading+'</div>')
    # Country-only views need stable shared participant keys for unique totals,
    # but do not need to ship names, profile URLs or profile-slug associations.
    public_countries=countries
    if not show_names:
        keys={pid:'participant-'+str(index) for index,pid in enumerate(sorted({member['id'] for country in countries for member in country['members']}))}
        public_countries=[{**country,'members':[{'id':keys[member['id']],'status':member['status']} for member in country['members']]} for country in countries]
    numeric_codes={value['numeric']:code for code,value in country_reference().items()}
    payload=json.dumps({'countries':public_countries,'numeric_codes':numeric_codes,'default_filter':options['default_filter'],'show_member_names':show_names,
                        'show_country_labels':options['show_country_labels']},ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('&','\\u0026')
    description='Highlighted countries have opted-in members. Country bars show counts, largest first; each bar includes a flag, country name and member count.'
    return '<section class="global-community people-section" data-show-member-names="'+str(show_names).lower()+'" aria-labelledby="global-community-title"><h2 id="global-community-title">'+esc(options['title'])+'</h2><p class="community-description">'+esc(options['description'])+'</p>'+controls+stats_html+'<div class="community-layout"><div class="community-map-wrap"><svg class="community-map" viewBox="0 0 960 500" role="img" aria-labelledby="community-map-title community-map-description"><title id="community-map-title">Countries represented in our community</title><desc id="community-map-description">'+esc(description)+'</desc><g class="community-geography">'+''.join(paths)+'</g></svg><p class="community-legend"><span aria-hidden="true"></span> Countries represented in this view</p><p data-community-error role="status" hidden>Interactive map unavailable. Explore the country list.</p></div><div class="community-chart"><h3 id="community-chart-title" class="community-chart-title">Countries Represented</h3><div class="community-country-list" role="group" aria-labelledby="community-chart-title">'+''.join(rows)+'<p data-community-empty'+(' hidden' if stats['members'] else '')+'>No members in this view.</p></div></div></div><p class="community-privacy">Country connections are self-declared and do not imply citizenship, nationality or birthplace.</p><p class="community-credits">Map: <a href="https://www.naturalearthdata.com/">Natural Earth</a> · Country reference: <a href="https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes">lukes</a> (adapted, <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>).</p><script type="application/json" id="community-map-data">'+payload+'</script></section>'
