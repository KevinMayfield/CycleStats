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
MIN_TRAVEL = 3000          # people travelling to work: roughly a town of 10,000 or more
BENCH = ('Kingston upon Hull', 'York')

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
                     deprived=round(100 * t['deprived'] / t['lsoas']), nocar=round(t['nocar_w'] / t['travel'])))
for r in rows: r['area_name'] = AREAS[r['area']]['name']
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
        unprot = max(0.0, 1 - c['protected'] - 0.5 * c['lane'])
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
    for x in cand: x['safety'] = (x['n'] + 2 * x['ksi']) / 5 * max(0.0, 1 - x['protected'] - 0.5 * x['lane'])
    ms = max([x['safety'] for x in cand], default=0) or 1; mu = max([x['uplift'] for x in cand], default=0) or 1
    for x in cand: x['score'] = round(0.5 * x['safety'] / ms + 0.5 * x['uplift'] / mu, 3)
    r['roads'] = sorted(cand, key=lambda x: -x['score'])[:8]   # the page shows five, then three more

gentle = sorted([r for r in rows if r['tier'] == 'gentle'], key=lambda r: -r['missing'])
# area outlines for the overview map, simplified to ~300 m
outlines = []
for aid in AREAS:
    path = os.path.join(DATA, aid + '.json')
    if os.path.exists(path):
        outlines.append(dict(id=aid, name=AREAS[aid]['name'], rings=[simp(r, 300) for r in json.load(open(path))['boundary']]))
out = dict(towns=sorted(rows, key=lambda r: -r['travel']), outlines=outlines, bench=dict(share=round(b_share, 1), slope=b_slope, towns=bench),
           flat_low=[r['id'] for r in flat_low], gentle_low=[r['id'] for r in gentle], flat_max=FLAT, gentle_max=GENTLE,
           min_travel=MIN_TRAVEL)
json.dump(out, open(os.path.join(DATA, 'towns.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(rows)} towns; benchmark Hull+York {b_share:.1f}% cycling, slope up to {b_slope}%")
for r in bench: print('  bench', r['name'], r['cycle21'], r['slope'], r['travel'])
print('flat towns ranked by people missing from cycling:')
for r in flat_low[:25]:
    print(f"  {r['name'][:26]:26} {r['area_name'][:22]:22} slope={r['slope']:4} cycle21={r['cycle21']:4}% (2011 {r['cycle11']}%) dutch={r['dutch']}% travel={r['travel']:6} missing={r['missing']:5} dep={r['deprived']}% nocar={r['nocar']}%")
