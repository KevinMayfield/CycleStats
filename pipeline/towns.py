"""Flat towns with little cycling: compares every built-up area (town) in the CycleStats areas on route hilliness
and cycling to work, against Hull and York, the two flat places where cycling is high.

Per town (ONS built-up area 2022, from its LSOAs):
  slope     average gradient of commute routes under 10 km, PCT (2011 zones), weighted by commuters
  short     share of commutes under 10 km, PCT
  cycle21   Census 2021: people cycling to work / people travelling to work (excluding working from home)
  cycle11   Census 2011 share cycling to work, PCT
  dutch     PCT Go Dutch share of commuters cycling
  missing   extra people a day who would cycle to work if the town matched the Hull and York benchmark
Writes data/towns.json."""
import csv, json, math, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
DATA = os.path.join(HERE, '..', 'data')
AREAS = json.load(open(os.path.join(HERE, 'areas.json')))
# credit for partial provision (a painted lane, or a pavement shared with walkers or split by a painted line): little
# protection at side roads and junctions, so a quarter of a protected track
PARTIAL = 0.25
MIN_TRAVEL = 3000          # people travelling to work: roughly a town of 10,000 or more
BENCH = ('Kingston upon Hull', 'York')
# flagged on the page: at least one household in four with no car (Census 2021), and over a third of neighbourhoods in
# England's most deprived fifth (IMD 2025), against a fifth nationally
NOCAR_HIGH, DEPRIVED_HIGH = 25, 35

# LSOAs in each built area, with the centre of each neighbourhood for the map
area_of, centre, imd = {}, {}, {}
for aid in AREAS:
    path = os.path.join(DATA, aid + '-imd.json')
    if not os.path.exists(path): continue
    for f in json.load(open(path))['f']:
        area_of[f[0]] = aid
        ring = max(f[5], key=len); centre[f[0]] = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
        imd[f[0]] = (f[2], f[4])
bua = {r['lsoa']: (r['bua'], r['bua_name'], r['lad_name']) for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv')))}
ttw = collections.defaultdict(dict)
for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'ttw2021.csv'))): ttw[r['lsoa']][r['method']] = int(r['people'])
# cycle collisions (STATS19) by the neighbourhood they happened in: all, killed or seriously injured, on 40 mph+ roads
cyc_veh = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
coll, years = collections.defaultdict(collections.Counter), set()
for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv'))):
    if r['collision_index'] not in cyc_veh: continue
    c = coll[r['lsoa_of_accident_location']]; years.add(r['collision_year'])
    c['n'] += 1; c['ksi'] += r['collision_severity'] in ('1', '2')
    c['fast'] += r['speed_limit'].isdigit() and int(r['speed_limit']) >= 40
pct = {}
for region in {c['pct_region'] for c in AREAS.values()}:
    for r in csv.DictReader(open(os.path.join(RAW, 'pct', f'{region}_z.csv'))):
        pct[r['geo_code']] = r

towns = collections.defaultdict(lambda: collections.defaultdict(float))
meta = {}
for code, aid in area_of.items():
    b = bua.get(code)
    if not b or not b[0]: continue          # rural LSOAs belong to no built-up area
    t = towns[b[0]]; meta.setdefault(b[0], dict(name=b[1], lad=b[2], areas=collections.Counter()))['areas'][aid] += 1
    w = ttw.get(code, {})
    travel = w.get('0', 0) - w.get('1', 0)
    t['travel'] += travel; t['cycle21'] += w.get('9', 0); t['lsoas'] += 1
    for k in ('n', 'ksi', 'fast'): t['coll_' + k] += coll[code][k]
    la, lo = centre[code]; t['lat'] += la; t['lon'] += lo
    dec, nocar = imd[code]; t['deprived'] += dec <= 2; t['nocar_w'] += (nocar or 0) * travel
    p = pct.get(code)                       # PCT uses 2011 LSOAs; most codes are unchanged in 2021
    if p and p['avslope_perc_u10km'] not in ('', 'NA'):
        n = float(p['all']); t['pct_all'] += n; t['cycle11'] += float(p['bicycle']); t['dutch'] += float(p['dutch_slc'])
        t['slope_w'] += float(p['avslope_perc_u10km']) * n
        t['short_w'] += float(p['perc_rf_dist_u10km'] or 0) * n

rows = []
for k, t in towns.items():
    if t['travel'] < MIN_TRAVEL or not t['pct_all']: continue
    m = meta[k]
    rows.append(dict(id=k, name=m['name'], lad=m['lad'], area=m['areas'].most_common(1)[0][0], lsoas=int(t['lsoas']),
                     lat=round(t['lat'] / t['lsoas'], 4), lon=round(t['lon'] / t['lsoas'], 4),
                     travel=int(t['travel']), cyclists=int(t['cycle21']), cycle21=round(100 * t['cycle21'] / t['travel'], 1),
                     cycle11=round(100 * t['cycle11'] / t['pct_all'], 1), dutch=round(100 * t['dutch'] / t['pct_all'], 1),
                     slope=round(t['slope_w'] / t['pct_all'], 2), short=round(t['short_w'] / t['pct_all']),
                     deprived=round(100 * t['deprived'] / t['lsoas']), nocar=round(t['nocar_w'] / t['travel']),
                     coll=int(t['coll_n']), coll_ksi=int(t['coll_ksi']), coll_fast=int(t['coll_fast'])))
for r in rows: r['area_name'] = AREAS[r['area']]['name']
YEARS = len(years)


def coll_rates(r):
    """cycle collisions a year per 100 people who cycle to work (all cycling, not only commuting, so a rough guide),
    and the shares killed or seriously injured and on roads of 40 mph or more"""
    r['coll_rate'] = round(100 * r['coll'] / r['cyclists'] / YEARS, 1) if r['cyclists'] else None
    r['ksi_pct'] = round(100 * r['coll_ksi'] / r['coll']) if r['coll'] else None
    r['fast_pct'] = round(100 * r['coll_fast'] / r['coll']) if r['coll'] else None


for r in rows: coll_rates(r)
bench = [r for r in rows if r['name'] in BENCH]
b_share = sum(r['cyclists'] for r in bench) / sum(r['travel'] for r in bench) * 100
b_slope = max(r['slope'] for r in bench)
FLAT, GENTLE = round(b_slope + 0.3, 2), 2.0   # flat: no hillier than Hull and York plus a margin; gentle: up to 2%
for r in rows:
    r['tier'] = 'bench' if r['name'] in BENCH else 'flat' if r['slope'] <= FLAT else 'gentle' if r['slope'] <= GENTLE else 'hilly'
    r['flat'] = r['tier'] == 'flat'
    r['missing'] = max(0, round(r['travel'] * (b_share - r['cycle21']) / 100))
flat_low = sorted([r for r in rows if r['flat'] and r['name'] not in BENCH], key=lambda r: -r['missing'])
# --- suggested roads per town: stretches measured by priorities.py, placed in the town most of their length runs
# through, ranked half on unprotected harm and half on Go Dutch potential within the town ---
lsoa_rings, cell = {}, collections.defaultdict(list)
for aid in AREAS:
    path = os.path.join(DATA, aid + '-imd.json')
    if not os.path.exists(path): continue
    for f in json.load(open(path))['f']:
        if f[0] in lsoa_rings: continue
        lsoa_rings[f[0]] = f[5]
        las = [p[0] for r in f[5] for p in r]; los = [p[1] for r in f[5] for p in r]
        for i in range(int(min(las) / .02), int(max(las) / .02) + 1):
            for j in range(int(min(los) / .02) - 1, int(max(los) / .02) + 1): cell[(i, j)].append(f[0])


def lsoa_at(la, lo):
    for code in cell.get((int(la / .02), int(lo / .02) - (lo < 0)), ()):
        for ring in lsoa_rings[code]:
            c = False
            for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
                if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / (y2 - y1) + x1: c = not c
            if c: return code
    return None


def simp(g, tol):
    """Douglas-Peucker on [lat, lon] points, tolerance in metres"""
    if len(g) < 3: return [[round(a, 5), round(b, 5)] for a, b in g]
    k = math.cos(math.radians(g[0][0])) * 111320
    P = [(lo * k, la * 110574) for la, lo in g]; keep = [False] * len(g); keep[0] = keep[-1] = True; st = [(0, len(g) - 1)]
    while st:
        a, b = st.pop(); (x1, y1), (x2, y2) = P[a], P[b]; L = math.hypot(x2 - x1, y2 - y1) or 1e-9; mi, md = None, tol
        for i in range(a + 1, b):
            d = abs((y2 - y1) * (P[i][0] - x1) - (x2 - x1) * (P[i][1] - y1)) / L
            if d > md: mi, md = i, d
        if mi: keep[mi] = True; st += [(a, mi), (mi, b)]
    return [[round(p[0], 5), round(p[1], 5)] for p, k_ in zip(g, keep) if k_]


def simp_ring(g, tol):
    """simp for a closed ring: its first and last points are the same, so simplify each half on its own"""
    h = len(g) // 2
    return simp(g[:h + 1], tol) + simp(g[h:], tol)[1:]


town_ids = {r['id'] for r in rows}
roads = collections.defaultdict(dict)
for aid in AREAS:
    path = os.path.join(RAW, aid, 'work', 'priorities.json')
    if not os.path.exists(path): continue
    for c in json.load(open(path)):
        pts = [p for g in c['geom'] for p in g]; pts = pts[::max(1, len(pts) // 40)]
        votes = collections.Counter(bua.get(lsoa_at(*p), ('',))[0] for p in pts)
        town, k = max(((t, v) for t, v in votes.items() if t in town_ids), key=lambda x: x[1], default=(None, 0))
        if not town or k < 0.4 * len(pts): continue
        unprot = max(0.0, 1 - c['protected'] - PARTIAL * c['lane'])
        if c['protected'] >= 0.8: continue              # already protected; partly protected roads stay, as routes to complete
        uplift = max(0, c['pct_dutch'] - c['pct_now']) + max(0, c['school_dutch'] - c['school_now'])
        r = roads[town].get(c['name'])
        geom = [simp(g, 15) for g in c['geom']]
        if r:                                           # another section of the same road: add it in
            r['geom'] += geom
            w = r['km'] + c['km']
            r.update(n=r['n'] + c['n'], ksi=r['ksi'] + c['ksi'], protected=round((r['protected'] * r['km'] + c['protected'] * c['km']) / w, 2),
                     lane=round((r['lane'] * r['km'] + c['lane'] * c['km']) / w, 2), km=round(w, 2))
            if uplift > r['uplift']:
                r.update(uplift=uplift, pct_now=c['pct_now'], pct_dutch=c['pct_dutch'], school_now=c['school_now'], school_dutch=c['school_dutch'])
        else:
            roads[town][c['name']] = dict(name=c['name'], ref=c['ref'], km=c['km'], n=c['n'], ksi=c['ksi'], protected=c['protected'],
                                          lane=c['lane'], speed=c['speed'], pct_now=c['pct_now'], pct_dutch=c['pct_dutch'],
                                          school_now=c['school_now'], school_dutch=c['school_dutch'], uplift=uplift, aadf=c.get('aadf'), geom=geom)
for r in rows:
    cand = [x for x in roads.get(r['id'], {}).values() if x['n'] >= 2 or x['uplift'] >= 50]
    for x in cand: x['safety'] = (x['n'] + 2 * x['ksi']) / 5 * max(0.0, 1 - x['protected'] - PARTIAL * x['lane'])
    ms = max([x['safety'] for x in cand], default=0) or 1; mu = max([x['uplift'] for x in cand], default=0) or 1
    for x in cand: x['score'] = round(0.5 * x['safety'] / ms + 0.5 * x['uplift'] / mu, 3)
    r['roads'] = sorted(cand, key=lambda x: -x['score'])[:8]   # the page shows five, then three more

gentle = sorted([r for r in rows if r['tier'] == 'gentle'], key=lambda r: -r['missing'])
# --- town outlines and networks: ONS built-up area polygons; towns whose built-up edges come within GAP metres of each
# other touch. Flat and gentle towns that touch form a network: short, level trips between them that one connected
# set of routes could serve ---
GAP = 250
shapes = {}
for f in json.load(open(os.path.join(RAW, 'imd', 'bua22.geojson')))['features']:
    g = f['geometry']; polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    shapes[f['properties']['BUA22CD']] = [[[la, lo] for lo, la in p[0]] for p in polys]   # outer rings only
K0 = math.cos(math.radians(53)) * 111320
xy = lambda q: (q[1] * K0, q[0] * 110574)
fine = {r['id']: [[xy(q) for q in simp_ring(ring, 30)] for ring in shapes.get(r['id'], [])] for r in rows}
pts_cell = collections.defaultdict(set)
for k, rings in fine.items():
    for ring in rings:
        for x, y in ring: pts_cell[(int(x // GAP), int(y // GAP))].add(k)


def seg_d(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def touch(a, b):
    """a vertex of one outline within GAP of an edge of the other, either way round"""
    for u, v in ((a, b), (b, a)):
        for ru in fine[u]:
            for p in ru:
                if not any(v in pts_cell.get((int(p[0] // GAP) + i, int(p[1] // GAP) + j), ()) for i in (-1, 0, 1) for j in (-1, 0, 1)):
                    continue                    # no vertex of the other town nearby
                if any(seg_d(p, rv[i], rv[i + 1]) <= GAP for rv in fine[v] for i in range(len(rv) - 1)): return True
    return False


near = collections.defaultdict(set)
for k, rings in fine.items():
    cand = {o for ring in rings for x, y in ring for i in (-1, 0, 1) for j in (-1, 0, 1)
            for o in pts_cell.get((int(x // GAP) + i, int(y // GAP) + j), ()) if o > k}
    for o in cand:
        if touch(k, o): near[k].add(o); near[o].add(k)
by_id = {r['id']: r for r in rows}
for r in rows:
    r['near'] = sorted(near[r['id']], key=lambda i: -by_id[i]['travel'])
    # overview map outline: ~100 m detail is plenty at county scale
    r['shape'] = [[[round(a, 4), round(b, 4)] for a, b in s] for s in (simp_ring(ring, 100) for ring in shapes.get(r['id'], [])) if len(s) >= 4]
# networks: flat and gentle towns (not Hull or York) joined by touching, with at least one flat town
member = lambda r: r['tier'] in ('flat', 'gentle')
networks, done = [], set()
for r in sorted(rows, key=lambda r: -r['travel']):
    if r['id'] in done or not member(r): continue
    comp, todo = [], [r['id']]
    while todo:
        i = todo.pop()
        if i in done: continue
        done.add(i); comp.append(i); todo += [o for o in near[i] if member(by_id[o]) and o not in done]
    ts = sorted((by_id[i] for i in comp), key=lambda t: -t['travel'])
    if len(ts) < 2 or not any(t['flat'] for t in ts): continue
    travel = sum(t['travel'] for t in ts); cyc = sum(t['cyclists'] for t in ts)
    networks.append(dict(towns=[t['id'] for t in ts], travel=travel, cyclists=cyc, cycle21=round(100 * cyc / travel, 1),
                         dutch=round(sum(t['dutch'] * t['travel'] for t in ts) / travel, 1), missing=sum(t['missing'] for t in ts),
                         slope=round(sum(t['slope'] * t['travel'] for t in ts) / travel, 2),
                         nocar=round(sum(t['nocar'] * t['travel'] for t in ts) / travel),
                         deprived=round(sum(t['deprived'] * t['lsoas'] for t in ts) / sum(t['lsoas'] for t in ts)),
                         coll=sum(t['coll'] for t in ts), coll_ksi=sum(t['coll_ksi'] for t in ts), coll_fast=sum(t['coll_fast'] for t in ts),
                         links=sorted({tuple(sorted((a, b))) for a in comp for b in near[a] if b in comp}),
                         borders=sorted({o for a in comp for o in near[a] if o not in comp}, key=lambda i: -by_id[i]['travel']),
                         areas=sorted({t['area_name'] for t in ts})))
for n in networks: coll_rates(n)
networks.sort(key=lambda n: -n['missing'])
for n in networks:
    # named after its largest town, or the two largest when they are close in size
    a, b = (by_id[i]['name'] for i in n['towns'][:2])
    n['name'] = a if by_id[n['towns'][0]]['travel'] > 2 * by_id[n['towns'][1]]['travel'] else f'{a} & {b}'
# area outlines for the overview map, simplified to ~300 m
outlines = []
for aid in AREAS:
    path = os.path.join(DATA, aid + '.json')
    if os.path.exists(path):
        outlines.append(dict(id=aid, name=AREAS[aid]['name'], rings=[simp_ring(r, 300) for r in json.load(open(path))['boundary']]))
out = dict(towns=sorted(rows, key=lambda r: -r['travel']), outlines=outlines, bench=dict(share=round(b_share, 1), slope=b_slope, towns=bench),
           flat_low=[r['id'] for r in flat_low], gentle_low=[r['id'] for r in gentle], flat_max=FLAT, gentle_max=GENTLE,
           min_travel=MIN_TRAVEL, networks=networks, gap=GAP,
           nocar_high=NOCAR_HIGH, deprived_high=DEPRIVED_HIGH,
           coll_years=sorted(years))
json.dump(out, open(os.path.join(DATA, 'towns.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(rows)} towns; benchmark Hull+York {b_share:.1f}% cycling, slope up to {b_slope}%")
for r in bench: print('  bench', r['name'], r['cycle21'], r['slope'], r['travel'])
print('flat towns ranked by people missing from cycling:')
for r in flat_low[:25]:
    print(f"  {r['name'][:26]:26} {r['area_name'][:22]:22} slope={r['slope']:4} cycle21={r['cycle21']:4}% (2011 {r['cycle11']}%) dutch={r['dutch']}% travel={r['travel']:6} missing={r['missing']:5} dep={r['deprived']}% nocar={r['nocar']}%")
print('networks of touching flat and gentle towns:')
for n in networks:
    print(f"  {n['name'][:30]:30} {len(n['towns'])} towns travel={n['travel']:6} cycle21={n['cycle21']}% missing={n['missing']:5}: "
          + ', '.join(by_id[i]['name'] for i in n['towns']) + (' | borders ' + ', '.join(by_id[i]['name'] for i in n['borders']) if n['borders'] else ''))
