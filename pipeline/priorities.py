"""Where well-engineered cycle infrastructure would do most good, for one area.

For each named road stretch that has cycle collisions or a DfT cycle count, works out:
  harm       collisions per km per year, with killed or seriously injured counted three times
  protection share of the stretch with a protected track (OSM cycleway=track/separate, or a cycleway alongside that is
             segregated from walkers), partial provision (painted lane or shared-use pavement), or nothing
  use now    DfT bikes/day, and Propensity to Cycle Tool (PCT) commuters cycling on it (2011 Census)
  potential  PCT 'Go Dutch' commuters + school pupils, and the commuter level if women cycled as much as men
  who        share of cyclist casualties who were women, and children under 16
and writes raw/<area>/work/priorities.json for summary.py to rank across areas."""
import csv, json, statistics
from area import *

rg, roadways = load_roads()
tags = {w['id']: w['tags'] for w in json.load(open(A + 'osm/roads.json'))['elements']}
PROTECTED = {'track', 'separate', 'opposite_track'}


def cyc_tags(t):
    vals = {t.get(k) for k in ('cycleway', 'cycleway:both', 'cycleway:left', 'cycleway:right')}
    return 'protected' if vals & PROTECTED else 'lane' if vals & {'lane', 'opposite_lane'} else None


# separate cycleways beside a road: a track segregated from walkers counts as protection; a shared-use pavement
# (foot=designated without segregated=yes) is only partial provision, like a painted lane
cg, sg = Grid(40), Grid(40)
for w in json.load(open(A + 'osm/paths.json'))['elements']:
    t = w.get('tags', {})
    if w['type'] == 'way' and t.get('highway') == 'cycleway':
        shared = t.get('segregated') != 'yes' and t.get('foot') in ('designated', 'yes', 'permissive')
        g = [P(p['lat'], p['lon']) for p in w['geometry']]
        for i in range(len(g) - 1): (sg if shared else cg).add(w['id'], g[i], g[i + 1])

# PCT route network for the area's region: commute and school
pct = {}
for kind in ('commute', 'school'):
    grid = Grid(60); props = {}
    for i, ft in enumerate(json.load(open(S + f"pct/{CFG['pct_region']}_{kind}.geojson"))['features']):
        g = ft['geometry']
        lines = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
        pts = [[P(la, lo) for lo, la in line] for line in lines]
        if not any(inside(*line[len(line) // 2][::-1]) for line in lines): continue
        props[i] = ft['properties']
        for line in pts:
            for j in range(len(line) - 1): grid.add(i, line[j], line[j + 1])
    pct[kind] = (grid, props)

# cyclist casualties: sex and age by collision
cas = collections.defaultdict(list)
for r in csv.DictReader(open(S + 'dft/cycle_cas.csv')):
    cas[r['collision_index']].append((r['sex_of_casualty'], r['age_band_of_casualty']))
coll = [(r['collision_index'], P(la, lo)) for r, la, lo in collision_rows()]
collgrid = collections.defaultdict(list)
for ci, p in coll: collgrid[(int(p[0] // 100), int(p[1] // 100))].append((ci, p))

# neighbourhood deprivation at the middle of a stretch
imd = json.load(open(os.path.join(HERE, '..', 'data', AREA + '-imd.json')))['f']


def lsoa_at(la, lo):
    for f in imd:
        for ring in f[5]:
            c = False
            for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
                if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / (y2 - y1) + x1: c = not c
            if c: return f
    return None


def samples(geom, step=30):
    """points every ~step metres along each line, as (lat, lon)"""
    for g in geom:
        for a, b in zip(g, g[1:]):
            pa, pb = P(*a), P(*b); n = max(1, int(dist(pa, pb) // step))
            for k in range(n):
                t = k / n; yield (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def measure(c):
    pts = list(samples(c['geom']))
    if not pts: return None
    prot = lane = 0; speeds = []; vals = collections.defaultdict(list)
    for la, lo in pts:
        p = P(la, lo)
        _, k = rg.near(p, 25, lambda kk: roadways[kk][0] == c['name'])
        t = tags.get(k, {}) if k else {}
        kind = cyc_tags(t)
        if kind != 'protected' and cg.near(p, 15)[1]: kind = 'protected'
        elif kind is None and sg.near(p, 15)[1]: kind = 'lane'
        prot += kind == 'protected'; lane += kind == 'lane'
        ms = t.get('maxspeed', '').split()
        if ms and ms[0].isdigit(): speeds.append(int(ms[0]))
        for kind_, (grid, props) in pct.items():
            _, i = grid.near(p, 25)
            if i is not None:
                for key in ('bicycle', 'dutch_slc', 'gendereq_slc'):
                    if key in props[i]: vals[(kind_, key)].append(props[i][key] or 0)
    n = len(pts)
    med = lambda key: round(statistics.median(vals[key])) if vals[key] else 0
    # casualties within 30 m of the stretch
    seen = set()
    for la, lo in pts:
        p = P(la, lo); i, j = int(p[0] // 100), int(p[1] // 100)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for ci, q in collgrid.get((i + di, j + dj), ()):
                    if dist(p, q) < 30: seen.add(ci)
    people = [x for ci in seen for x in cas.get(ci, [])]
    known_sex = [s for s, _ in people if s in ('1', '2')]
    known_age = [a for _, a in people if a not in ('-1', '')]
    mid = pts[len(pts) // 2]; f = lsoa_at(*mid)
    return dict(
        name=c['name'], ref=c['ref'], km=c['km'], n=c['n'], ksi=c['ksi'], aadf=c.get('aadf'),
        lat=round(mid[0], 5), lon=round(mid[1], 5), geom=c['geom'],
        protected=round(prot / n, 2), lane=round(lane / n, 2), speed=max(set(speeds), key=speeds.count) if speeds else None,
        pct_now=med(('commute', 'bicycle')), pct_dutch=med(('commute', 'dutch_slc')), pct_women=med(('commute', 'gendereq_slc')),
        school_now=med(('school', 'bicycle')), school_dutch=med(('school', 'dutch_slc')),
        casualties=len(people), women=round(100 * known_sex.count('2') / len(known_sex)) if known_sex else None,
        children=round(100 * sum(a in ('1', '2', '3') for a in known_age) / len(known_age)) if known_age else None,
        imd=f[2] if f else None, nocar=f[4] if f else None)


# candidates: every counted road, plus the high-collision stretches without a count
cands = json.load(open(A + 'work/safe_all.json'))
for c in json.load(open(A + 'work/corr_risk.json')):
    m = [p for g in c['geom'] for p in g][len([p for g in c['geom'] for p in g]) // 2]
    if not any(o['name'] == c['name'] and min(dist(P(*m), P(*q)) for g in o['geom'] for q in g) < 300 for o in cands):
        cands.append(c)
out = [m for m in (measure(c) for c in cands if c['km'] >= 0.5) if m]
json.dump(out, open(A + 'work/priorities.json', 'w'))
print(f"{CFG['name']}: {len(out)} stretches measured")
