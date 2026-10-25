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
import csv, json, os, collections

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
gentle = sorted([r for r in rows if r['tier'] == 'gentle'], key=lambda r: -r['missing'])
out = dict(towns=sorted(rows, key=lambda r: -r['travel']), bench=dict(share=round(b_share, 1), slope=b_slope, towns=bench),
           flat_low=[r['id'] for r in flat_low], gentle_low=[r['id'] for r in gentle], flat_max=FLAT, gentle_max=GENTLE,
           min_travel=MIN_TRAVEL)
json.dump(out, open(os.path.join(DATA, 'towns.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"{len(rows)} towns; benchmark Hull+York {b_share:.1f}% cycling, slope up to {b_slope}%")
for r in bench: print('  bench', r['name'], r['cycle21'], r['slope'], r['travel'])
print('flat towns ranked by people missing from cycling:')
for r in flat_low[:25]:
    print(f"  {r['name'][:26]:26} {r['area_name'][:22]:22} slope={r['slope']:4} cycle21={r['cycle21']:4}% (2011 {r['cycle11']}%) dutch={r['dutch']}% travel={r['travel']:6} missing={r['missing']:5} dep={r['deprived']}% nocar={r['nocar']}%")
