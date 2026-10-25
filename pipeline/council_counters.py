"""Bike counts for the Bike counts tab: Leeds City Council automatic counters for Leeds,
the busiest DfT traffic count points everywhere else. Also attaches the busiest count to each path and route."""
import csv, collections, json
from area import *


def daily(files):
    """average bikes/day per counter over complete days (every lane has 24 hourly rows)"""
    vol = collections.defaultdict(collections.Counter); hrs = collections.defaultdict(collections.Counter)
    for f in files:
        for r in csv.DictReader(open(f, encoding='utf-8-sig')):
            try: v = int(float(r['Volume'])); c = int(r['Cosit'])
            except (ValueError, KeyError): continue
            if v < 0: continue
            d = r['Sdate'][:10]; vol[c][d] += v; hrs[c][(d, r['LaneNumber'])] += 1
    res = {}
    for c in vol:
        lanes = collections.defaultdict(dict)
        for (d, l), h in hrs[c].items(): lanes[d][l] = h
        full = [d for d, ls in lanes.items() if all(h >= 24 for h in ls.values())]
        if full:
            ms = sorted({d[3:] for d in full}, key=lambda m: (m[3:], m[:2]))
            res[c] = dict(days=len(full), avg=round(sum(vol[c][d] for d in full) / len(full)), months=len(ms), first=ms[0], last=ms[-1])
    return res


def leeds_counts():
    sites = {}
    for r in list(csv.reader(open(S + 'lcc/sites.csv', encoding='utf-8-sig')))[2:]:
        if len(r) > 5 and r[0].strip(): sites[int(r[0])] = dict(desc=r[2].strip(), lat=float(r[4]), lon=float(r[5]))
    M = S + 'lcc/months/'
    have = sorted(f[:-4] for f in os.listdir(M) if f.endswith('.csv'))
    recent = daily([M + m + '.csv' for m in have[-12:]])
    # counters that have since stopped reporting fall back to their last full year
    old = daily([M + m + '.csv' for m in have if '2023-12' <= m <= '2024-11'])
    o22 = daily([M + m + '.csv' for m in have if m == '2022-07'])
    OFF = {90810, 90120, 100217, 170127}
    NAME = {90810: 'Leeds–Liverpool Canal towpath, Armley Mills', 90120: 'Leeds–Liverpool Canal towpath, Kirkstall Forge',
            100217: 'Wyke Beck Way, Wykebeck Woods', 170127: 'Castleford Greenway'}
    mon = lambda m: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][int(m[:2]) - 1] + ' ' + m[3:]
    cs = []
    for c, s in sites.items():
        r = recent.get(c) or old.get(c) or o22.get(c)
        if not r: continue
        print(f"{r['avg']:5}/day {r['days']:3}d  {s['desc']}")
        cs.append(dict(name=NAME.get(c, s['desc']), kind='Off-road path' if c in OFF else 'Cycle track or lane on a road', avg=r['avg'],
                       src='Leeds City Council automatic counter', period=f"{mon(r['first'])} – {mon(r['last'])}",
                       chip=f"{r['days']} days counted", note='partial data' if r['days'] < 60 else '', lat=s['lat'], lon=s['lon'], id=c))
    # ELOR has no council counter: use the DfT one-day manual counts (2023)
    cs.append(dict(name='ELOR cycle track (A6120, A64 to A58)', kind='Cycle track beside a road', avg=127, src='DfT count point 95049 (single manual count, 2023)',
                   period='2023', chip='DfT one-day count', note='', lat=53.84017, lon=-1.44663, id='DfT95049'))
    cs.append(dict(name='ELOR cycle track (A6120, M1 J46 to A64)', kind='Cycle track beside a road', avg=151, src='DfT count point 95047 (single manual count, 2023)',
                   period='2023', chip='DfT one-day count', note='', lat=53.80379, lon=-1.41964, id='DfT95047'))
    blurb = ('Average bikes per day from Leeds City Council automatic counters (12 months to the latest data where available), plus two DfT counts on the ELOR track. '
             'Green dots are off-road paths. Counters on one-way lanes count one direction only, so a road with two counters carries roughly their sum. '
             'Police collision data does not cover off-road paths, so they have usage figures but no safety rating.')
    return cs, blurb


def dft_counts(top=15):
    """busiest DfT count points that were manually counted at least once in 2021-25"""
    rg, roadways = load_roads()
    cps = collections.defaultdict(list)
    for r in aadf_rows(): cps[r['count_point_id']].append(r)
    cs = []
    for cid, rs in cps.items():
        counted = sum(r['estimation_method'] == 'Counted' for r in rs)
        if not counted: continue
        r0 = rs[0]; la, lo = float(r0['latitude']), float(r0['longitude'])
        _, k = rg.near(P(la, lo), 40)
        road = roadways[k][0] if k else None
        ref = r0['road_name'] if r0['road_name'] not in ('U', 'C') else None
        name = f"{road} ({ref})" if road and ref else road or ref or 'Minor road'
        years = sorted(r['year'] for r in rs)
        cs.append(dict(name=name, kind='Road (DfT count point)', avg=round(sum(int(r['pedal_cycles']) for r in rs) / len(rs)),
                       src=f'DfT count point {cid}', period=years[0] if years[0] == years[-1] else f'{years[0]}–{years[-1]}',
                       chip=f"{counted} manual count{'s' if counted > 1 else ''}", note='', lat=la, lon=lo, id=f'DfT{cid}'))
    cs.sort(key=lambda c: -c['avg'])
    # both carriageways of a dual carriageway can have their own point with the same figure
    seen = set(); cs = [c for c in cs if (c['name'], c['avg']) not in seen and not seen.add((c['name'], c['avg']))]
    for c in cs[:top]: print(f"{c['avg']:5}/day  {c['name']}")
    blurb = (f"Average bikes per day at the busiest DfT traffic count points {CFG['in']}, 2021–25 (only points manually counted at least once). "
             'Most are single weekday counts on main roads, so weekend leisure riding is undercounted and off-road paths are not covered. '
             'Leeds is the only area here with open data from automatic council counters.')
    return cs[:top], blurb


cs, blurb = leeds_counts() if CFG['counters'] == 'leeds' else dft_counts()
cs.sort(key=lambda c: -c['avg'])
d = json.load(open(A + 'work/data.json'))
d['counts'] = cs; d['meta']['counts_blurb'] = blurb


def mind(p, geoms):
    return min((segd(p, P(*g[i]), P(*g[i + 1])) for g in geoms for i in range(len(g) - 1)), default=1e9)


for k in ('paths', 'routes'):
    for r in d[k]:
        hits = [c for c in cs if mind(P(c['lat'], c['lon']), r['geom']) < 60]
        r['counters'] = [[c['name'], c['avg'], c['period'], c['src'].startswith('DfT')] for c in hits]
json.dump(d, open(A + 'work/data.json', 'w'), separators=(',', ':'))
