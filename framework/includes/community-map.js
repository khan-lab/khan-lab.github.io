/* Country-level, opt-in data only. All assets are bundled on the same site. */
(() => {
  const section = document.querySelector('.global-community');
  if (!section) return;
  const topologyURL = new URL('../maps/countries-50m.json', document.currentScript.src);
  const unavailable = () => { section.querySelector('[data-community-error]').hidden = false; };
  if (!window.d3 || !window.topojson) { unavailable(); return; }
  const data = JSON.parse(section.querySelector('#community-map-data').textContent);
  const countries = new Map(data.countries.map(country => [country.code, country]));
  let filter = data.default_filter, selected = '';
  const members = country => country.members.filter(member => filter === 'all' || member.status === filter);
  const svg = d3.select(section.querySelector('svg'));

  fetch(topologyURL).then(response => {
    if (!response.ok) throw Error('Geography unavailable');
    return response.json();
  }).then(topology => {
    const features = topojson.feature(topology, topology.objects.countries).features;
    const projection = d3.geoNaturalEarth1().fitExtent([[8, 8], [952, 492]], {type: 'Sphere'});
    const path = d3.geoPath(projection).digits(2);
    const code = feature => data.numeric_codes[String(feature.id ?? '').padStart(3, '0')] || '';
    const active = feature => countries.has(code(feature)) && members(countries.get(code(feature))).length > 0;
    // Build off-DOM. Keep the meaningful static SVG intact until assets are ready.
    const layer = d3.create('svg:g').attr('class', 'community-geography');
    const shapes = layer.selectAll('path').data(features).join('path')
      .attr('class', 'community-country').attr('d', path)
      .attr('data-code', code).attr('data-active', feature => String(active(feature)));
    const fallbackCodes = new Set([...section.querySelectorAll('path[data-active="true"]')].map(p => p.dataset.code));
    for (const country of fallbackCodes) {
      if (!features.some(feature => code(feature) === country)) throw Error('Country matching failed');
    }
    svg.select('.community-geography').node().replaceWith(layer.node());
    svg.attr('role', 'group');
    const rows = [...section.querySelectorAll('[data-country]')].map(row => {
      if (row.localName === 'details') return row;
      // Static bars and focusable country labels survive asset failure. Only
      // successful enhancement turns them into native selection buttons.
      const button = document.createElement('button');
      button.type = 'button'; button.className = row.className; button.id = row.id;
      button.dataset.country = row.dataset.country; button.hidden = row.hidden;
      button.setAttribute('aria-label', row.getAttribute('aria-label'));
      if (row.title) button.title = row.title;
      button.append(...row.childNodes); row.replaceWith(button); return button;
    });
    const focusTarget = row => row.localName === 'details' ? row.querySelector('summary') : row;

    function clearSelection() {
      selected = '';
      shapes.classed('is-selected', false).attr('aria-pressed', feature => active(feature) ? 'false' : null);
      rows.forEach(row => {
        if (row.localName === 'details') row.open = false;
        else { row.classList.remove('is-selected'); row.setAttribute('aria-pressed', 'false'); }
      });
    }
    function selectCountry(country, focus = false) {
      const row = rows.find(row => row.dataset.country === country && !row.hidden);
      if (!row) return;
      selected = country;
      rows.forEach(item => {
        if (item.localName === 'details') item.open = item === row;
        else { item.classList.toggle('is-selected', item === row); item.setAttribute('aria-pressed', String(item === row)); }
      });
      shapes.classed('is-selected', feature => code(feature) === country)
        .attr('aria-pressed', feature => active(feature) ? String(code(feature) === country) : null);
      if (focus) focusTarget(row).focus();
    }
    function update() {
      const unique = new Set(), represented = data.countries.filter(country => members(country).length);
      const maximum = Math.max(1, ...represented.map(country => members(country).length));
      represented.forEach(country => members(country).forEach(member => unique.add(member.id)));
      section.querySelectorAll('[data-community-stat]').forEach(stat => {
        stat.textContent = stat.dataset.communityStat === 'members' ? unique.size : represented.length;
      });
      section.querySelectorAll('[data-community-stat-label]').forEach(label => {
        const isMembers = label.dataset.communityStatLabel === 'members';
        const count = isMembers ? unique.size : represented.length;
        label.textContent = isMembers ? (count === 1 ? 'member' : 'members') : (count === 1 ? 'country' : 'countries');
      });
      section.querySelectorAll('[data-community-filter]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.communityFilter === filter));
      });
      shapes.attr('data-active', feature => String(active(feature)))
        .attr('tabindex', feature => active(feature) ? 0 : null)
        .attr('role', feature => active(feature) ? 'button' : null)
        .attr('aria-hidden', feature => active(feature) ? null : 'true')
        .attr('aria-controls', feature => active(feature) ? 'community-country-' + code(feature) : null)
        .attr('aria-label', feature => {
          if (!active(feature)) return null;
          const country = countries.get(code(feature)), visible = members(country);
          const current = visible.filter(member => member.status === 'current').length;
          return `${country.name}: ${current} current members, ${visible.length - current} alumni. ` +
            (data.show_member_names ? 'Select for names and profiles.' : 'Select country.');
        });
      shapes.selectAll('title').remove();
      if (data.show_country_labels === 'on_hover') {
        shapes.filter(active).append('title').text(feature => countries.get(code(feature)).name);
      }
      rows.forEach(detail => {
        const country = countries.get(detail.dataset.country), visible = members(country);
        detail.hidden = visible.length === 0;
        const label = `${country.name}: ${visible.length} ${visible.length === 1 ? 'member' : 'members'}`;
        focusTarget(detail).setAttribute('aria-label', label);
        detail.querySelector('[data-community-bar]').style.width = `${100 * visible.length / maximum}%`;
        detail.querySelector('[data-community-bar-count]').textContent = visible.length;
        const current = visible.filter(member => member.status === 'current').length;
        const currentCount = detail.querySelector('[data-count="current"]');
        const alumniCount = detail.querySelector('[data-count="alumni"]');
        if (currentCount) currentCount.textContent = current;
        if (alumniCount) alumniCount.textContent = visible.length - current;
        detail.querySelectorAll('[data-member-status]').forEach(member => {
          member.hidden = filter !== 'all' && member.dataset.memberStatus !== filter;
        });
      });
      const ordered = [...rows].sort((a, b) => {
        const left = countries.get(a.dataset.country), right = countries.get(b.dataset.country);
        const difference = members(right).length - members(left).length;
        if (difference) return difference;
        const leftName = left.name.toLowerCase(), rightName = right.name.toLowerCase();
        return leftName < rightName ? -1 : leftName > rightName ? 1 : 0;
      });
      const list = section.querySelector('.community-country-list');
      ordered.forEach(row => list.appendChild(row));
      list.appendChild(section.querySelector('[data-community-empty]'));
      section.querySelector('[data-community-empty]').hidden = represented.length > 0;
      const next = represented.some(country => country.code === selected) ? selected : ordered.find(row => !row.hidden)?.dataset.country;
      if (next) selectCountry(next); else clearSelection();
    }
    shapes.on('mouseenter focus', (_, feature) => { if (active(feature)) selectCountry(code(feature)); })
      .on('click', (_, feature) => { if (active(feature)) selectCountry(code(feature), true); })
      .on('keydown', (event, feature) => {
        if (active(feature) && ['Enter', ' '].includes(event.key)) {
          event.preventDefault(); selectCountry(code(feature), true);
        }
      });
    // Hover may open details while keyboard focus is outside this section.
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        clearSelection();
        rows.forEach(row => row.classList.add('community-tooltip-dismissed'));
      }
    });
    rows.forEach(row => {
      const target = focusTarget(row);
      ['mouseenter', 'focusin'].forEach(type => target.addEventListener(type, () => row.classList.remove('community-tooltip-dismissed')));
      if (row.localName === 'details') row.addEventListener('toggle', () => {
        if (row.open && !row.hidden) selectCountry(row.dataset.country);
      });
      else row.addEventListener('click', () => selectCountry(row.dataset.country));
    });
    section.querySelectorAll('[data-community-filter]').forEach(button => {
      button.addEventListener('click', () => { filter = button.dataset.communityFilter; update(); });
    });
    update();
    section.querySelector('.community-filters').hidden = false;
    section.dataset.enhanced = 'true';
  }).catch(unavailable);
})();
