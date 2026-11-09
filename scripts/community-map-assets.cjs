/* Maintainer-only offline refresh. Normal Python/Quarto builds do not need Node. */
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const root = path.resolve(__dirname, '..'), folder = path.join(root, 'framework/maps');
const d3 = require(path.join(root, 'framework/vendor/d3.min.js'));
const topojson = require(path.join(root, 'framework/vendor/topojson-client.min.js'));
const topology = JSON.parse(fs.readFileSync(path.join(folder, 'countries-50m.json')));
const countries = JSON.parse(fs.readFileSync(path.join(folder, 'iso-countries.json')));
const numeric = new Map(Object.entries(countries).map(([code, value]) => [value.numeric, code]));
const projection = d3.geoNaturalEarth1().fitExtent([[8, 8], [952, 492]], {type: 'Sphere'});
const geoPath = d3.geoPath(projection).digits(2);
const features = topojson.feature(topology, topology.objects.countries).features;
const geometries = features.map((feature, index) => ({
  key: String(index), id: String(feature.id ?? '').padStart(3, '0'),
  code: numeric.get(String(feature.id ?? '').padStart(3, '0')) || '',
  name: feature.properties.name, path: geoPath(feature)
}));
for (const code of ['PK', 'NO', 'DE', 'CN', 'AE']) {
  if (!geometries.some(g => g.code === code && g.path)) throw Error('Missing country geometry: ' + code);
}
const file = path.join(folder, 'country-paths.json');
fs.writeFileSync(file, JSON.stringify({projection: 'natural_earth', viewBox: '0 0 960 500', geometries}) + '\n');
const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'provenance.json')));
manifest.country_paths_sha256 = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
fs.writeFileSync(path.join(folder, 'provenance.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({geometries: geometries.length, mapped: geometries.filter(g => g.code).length,
  unmapped: geometries.filter(g => !g.code).map(g => ({id:g.id, name:g.name})), bytes:fs.statSync(file).size}));
