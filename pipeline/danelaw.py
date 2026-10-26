"""The Danelaw Way: a long-distance ride from Derby to York along the Trent, Ermine Street, the Humber and the Ouse,
the waterways and roads of the Danelaw. Writes data/danelaw.json for danelaw.html.

Each stage is routed through its waypoints with BRouter's touring profile ('trekking', which prefers cycle routes and
quiet roads); responses are cached in raw/danelaw/. Every 25 m along the route is then checked against the
OpenStreetMap data already downloaded for the areas it crosses:
  traffic-free  within 12 m of a cycleway or a path designated for bikes
  quiet road    a named residential, unclassified or service road
  main road     a secondary or tertiary road (mostly B and C roads)
  busy road     an A road (primary or trunk)
  track/lane    none of these within 12 m: unnamed lanes, farm tracks, towpaths not designated for bikes
plus whether it follows a signed National, Regional or local cycle route, and the police-reported cycle collisions
(STATS19 2021-25) within 30 m. Runs of 300 m or more on A roads are listed as gaps to fix."""
import collections, csv, json, math, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
CACHE = os.path.join(RAW, 'danelaw')
AREAS = ['derbyshire', 'nottinghamshire', 'lincolnshire', 'grimsby-scunthorpe', 'east-riding', 'hull', 'north-yorkshire', 'york']
UA = {'User-Agent': 'CycleStats/1.0 (https://github.com/KevinMayfield/CycleStats)'}

# stages and their waypoints (lat, lon). Waypoints hold the line to the rivers and old roads.
STAGES = [
    dict(name='Derby to Newark', note='Down the Trent through Long Eaton and Nottingham', pts=[
        ('Derby', 52.9250, -1.4775), ('Long Eaton', 52.8980, -1.2710), ('Beeston Lock', 52.9174, -1.2083),
        ('Trent Bridge, Nottingham', 52.9370, -1.1460), ('Gunthorpe', 52.9830, -0.9960), ('Hoveringham', 53.0110, -0.9540), ('Fiskerton', 53.0520, -0.9130),
        ('Kelham', 53.0900, -0.8460), ('Newark-on-Trent', 53.0770, -0.8130)]),
    dict(name='Newark to Lincoln', note='North with the Trent to the Great Army camp at Torksey, then the Fossdyke', pts=[
        ('Newark-on-Trent', 53.0770, -0.8130), ('Collingham', 53.1440, -0.7490), ('Torksey Lock', 53.2990, -0.7420),
        ('Saxilby', 53.2690, -0.6640), ('Lincoln', 53.2307, -0.5406)]),
    dict(name='Lincoln to Barton-upon-Humber', note='North along Ermine Street to the Humber', pts=[
        ('Lincoln', 53.2307, -0.5406), ('Spital in the Street', 53.4295, -0.5434), ('Brigg', 53.5520, -0.4920),
        ('Barton-upon-Humber', 53.6840, -0.4390)]),
    dict(name='Barton-upon-Humber to Howden', note='Over the Humber Bridge, then west along the estuary', pts=[
        ('Barton-upon-Humber', 53.6840, -0.4390), ('Hessle', 53.7230, -0.4380), ('North Ferriby', 53.7210, -0.5040),
        ('Brough', 53.7290, -0.5720), ('Howden', 53.7450, -0.8680)]),
    dict(name='Howden to York', note='Up the Ouse through Selby to Jorvik', pts=[
        ('Howden', 53.7450, -0.8680), ('Hemingbrough', 53.7690, -0.9770), ('Selby', 53.7840, -1.0670),
        ('Riccall', 53.8330, -1.0590), ('Naburn', 53.9135, -1.0875), ('Fulford', 53.9370, -1.0710), ('York', 53.9620, -1.0815)]),
]

# places on or near the route with a Danelaw or Viking-age story
SITES = [
    dict(name='Derby', lat=52.9250, lon=-1.4775, on=True, text='One of the Five Boroughs of the Danelaw. Its name is Old Norse, Djúrabý, "deer farm". Æthelflæd, Lady of the Mercians, took it back from the Danes in 917.'),
    dict(name='Repton', lat=52.8390, lon=-1.5500, on=False, text='13 km up the Trent from Derby, off the route. The Great Heathen Army wintered here in 873–874 and drove out the Mercian king; a Viking camp and burials have been excavated by the church.'),
    dict(name='Nottingham', lat=52.9370, lon=-1.1460, on=True, text='Another of the Five Boroughs. The Great Heathen Army wintered here in 867–868. The route crosses the Trent at Trent Bridge.'),
    dict(name='Torksey', lat=53.2990, lon=-0.7420, on=True, text='The Great Army\'s winter camp of 872–873, where the Fossdyke meets the Trent. Metal-detecting and excavation have found thousands of finds: hack silver, weights and lead gaming pieces.'),
    dict(name='Fossdyke', lat=53.2690, lon=-0.6640, on=True, text='A canal joining the Trent at Torksey to the Witham at Lincoln, probably Roman and still navigable: the route follows its towpath into Lincoln.'),
    dict(name='Lincoln', lat=53.2307, lon=-0.5406, on=True, text='One of the Five Boroughs, with a busy Viking-age mint. The route leaves north along Ermine Street, the Roman road to the Humber.'),
    dict(name='Gainsborough', lat=53.3990, lon=-0.7750, on=False, text='Off the route, north of Torksey on the Trent. Sweyn Forkbeard, king of Denmark, made it his base when he conquered England in 1013 and died there in 1014.'),
    dict(name='Barton-upon-Humber', lat=53.6840, lon=-0.4390, on=True, text='The old ferry town on the south bank of the Humber. St Peter\'s Church has an Anglo-Saxon tower from around the end of the 10th century.'),
    dict(name='Humber', lat=53.7090, lon=-0.4500, on=True, text='The estuary the Great Army crossed on its way to York in 866. The route crosses it on the Humber Bridge.'),
    dict(name='Selby', lat=53.7840, lon=-1.0670, on=True, text='A name of Old Norse origin, probably "willow farm", like many -by places along the route.'),
    dict(name='Riccall', lat=53.8330, lon=-1.0590, on=True, text='Harald Hardrada\'s fleet came up the Ouse and landed here in September 1066, the last great Viking invasion of England.'),
    dict(name='Fulford', lat=53.9370, lon=-1.0710, on=True, text='Harald Hardrada beat the northern earls here on 20 September 1066, five days before his defeat at Stamford Bridge.'),
    dict(name='York', lat=53.9620, lon=-1.0815, on=True, text='Jorvik. The Great Heathen Army took it on 1 November 866, and it was the capital of a Viking kingdom until Eric Bloodaxe was driven out in 954.'),
]

K = math.cos(math.radians(53.4)) * 111320; KY = 110574
P = lambda la, lo: ((lo + 1.0) * K, (la - 53.4) * KY)


def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])


def brouter(pts):
    lonlats = '|'.join(f'{lo},{la}' for _, la, lo in pts)
    url = f'https://brouter.de/brouter?lonlats={urllib.request.quote(lonlats, safe=",|")}&profile=trekking&alternativeidx=0&format=geojson'
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180))
        except Exception as e:
            print('  brouter retry', e); time.sleep(10 * (attempt + 1))
    sys.exit('BRouter failed')


class Grid:
    def __init__(s, cell=50): s.c = cell; s.d = collections.defaultdict(list)
    def add(s, key, a, b):
        for i in range(int(min(a[0], b[0]) // s.c), int(max(a[0], b[0]) // s.c) + 1):
            for j in range(int(min(a[1], b[1]) // s.c), int(max(a[1], b[1]) // s.c) + 1): s.d[(i, j)].append((key, a, b))
    def near(s, p, maxd):
        best = (maxd, None); i, j = int(p[0] // s.c), int(p[1] // s.c); r = int(maxd // s.c) + 1
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                for key, a, b in s.d.get((i + di, j + dj), ()):
                    dx, dy = b[0] - a[0], b[1] - a[1]; L = dx * dx + dy * dy
                    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
                    d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
                    if d < best[0]: best = (d, key)
        return best


def main():
    os.makedirs(CACHE, exist_ok=True)
    routes = []
    for n, st in enumerate(STAGES, 1):
        path = os.path.join(CACHE, f'stage{n}.geojson')
        if not os.path.exists(path) or '--refresh' in sys.argv:
            print('routing', st['name']); json.dump(brouter(st['pts']), open(path, 'w')); time.sleep(2)
        routes.append(json.load(open(path)))

    # OpenStreetMap data for the areas the route crosses
    paths, roads, ncn = Grid(), Grid(), Grid(); rinfo, ninfo, places = {}, {}, []
    for a in AREAS:
        d = os.path.join(RAW, a, 'osm')
        for w in json.load(open(os.path.join(d, 'paths.json')))['elements']:
            if w['type'] != 'way': continue
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): paths.add(w['id'], g[i], g[i + 1])
        for w in json.load(open(os.path.join(d, 'roads.json')))['elements']:
            t = w['tags']; rinfo[w['id']] = (t.get('name'), t.get('ref'), t.get('highway', ''), t.get('maxspeed'))
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): roads.add(w['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'routes.json')))['elements']:
            if e['type'] != 'relation': continue
            t = e.get('tags', {}); nm = t.get('name') or (('NCN ' + t['ref']) if t.get('ref') else None)
            if not nm or t.get('network') not in ('ncn', 'rcn', 'lcn'): continue
            ninfo[e['id']] = (nm, t.get('network'))
            for m in e['members']:
                g = [P(p['lat'], p['lon']) for p in (m.get('geometry') or []) if p]
                for i in range(len(g) - 1): ncn.add(e['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'ctx.json')))['elements']:
            if e['type'] == 'node' and e['tags'].get('name') and e['tags'].get('place') in ('city', 'town', 'village', 'suburb'):
                places.append((e['tags']['name'], P(e['lat'], e['lon'])))

    # cyclist collisions
    cyc = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
    cg = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv'))):
        if r['collision_index'] not in cyc: continue
        try: la, lo = float(r['latitude']), float(r['longitude'])
        except ValueError: continue
        if 52.8 < la < 54.1 and -1.6 < lo < -0.3:
            p = P(la, lo); cg[(int(p[0] // 100), int(p[1] // 100))].append((r['collision_index'], p, la, lo, int(r['collision_severity'])))

    def classify(p):
        if paths.near(p, 12)[1]: return 'path', None
        d, k = roads.near(p, 12)
        if not k: return 'track', None
        hw = rinfo[k][2].replace('_link', '')
        return ('busy' if hw in ('motorway', 'trunk', 'primary') else 'main' if hw in ('secondary', 'tertiary') else 'quiet'), k

    stages, segs, profile, coll_all, gaps = [], [], [], {}, []
    total_km = 0.0
    for n, (st, rt) in enumerate(zip(STAGES, routes), 1):
        coords = rt['features'][0]['geometry']['coordinates']   # [lon, lat, ele]
        props = rt['features'][0]['properties']
        # resample every 25 m
        samples = []; acc = 0.0
        for a, b in zip(coords, coords[1:]):
            pa, pb = P(a[1], a[0]), P(b[1], b[0]); L = dist(pa, pb); k = max(1, int(L // 25))
            for i in range(k):
                f = i / k
                samples.append(dict(lat=a[1] + (b[1] - a[1]) * f, lon=a[0] + (b[0] - a[0]) * f, ele=(a[2] if len(a) > 2 else 0) + ((b[2] if len(b) > 2 else 0) - (a[2] if len(a) > 2 else 0)) * f,
                                    km=total_km + (acc + L * f) / 1000))
            acc += L
        mix = collections.Counter(); onroute = collections.Counter(); seen = set(); ksi = 0
        run = None
        for s in samples:
            p = P(s['lat'], s['lon']); cls, k = classify(p); s['cls'] = cls
            mix[cls] += 25
            _, rid = ncn.near(p, 15)
            if rid: onroute[ninfo[rid][0]] += 25
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for ci, q, la, lo, sev in cg.get((int(p[0] // 100) + di, int(p[1] // 100) + dj), ()):
                        if ci not in seen and dist(p, q) < 30:
                            seen.add(ci); coll_all[ci] = [round(la, 5), round(lo, 5), sev, n]; ksi += sev <= 2
            # busy-road runs
            if cls == 'busy':
                if run is None: run = dict(start=s, pts=[s], keys=collections.Counter())
                else: run['pts'].append(s)
                run['keys'][k] += 1
            elif run is not None:
                if len(run['pts']) * 25 >= 300: gaps.append((n, run))
                run = None
        if run is not None and len(run['pts']) * 25 >= 300: gaps.append((n, run))
        # map segments: consecutive samples of one class
        cur = None
        for s in samples:
            if cur is None or s['cls'] != cur['cls']:
                if cur: cur['pts'].append([round(s['lat'], 5), round(s['lon'], 5)]); segs.append(cur)
                cur = dict(cls=s['cls'], stage=n, pts=[])
            cur['pts'].append([round(s['lat'], 5), round(s['lon'], 5)])
        if cur: segs.append(cur)
        for s in samples[::20]: profile.append([round(s['km'], 2), round(s['ele'])])
        km = int(props['track-length']) / 1000; total_km += km
        stages.append(dict(n=n, name=st['name'], note=st['note'], via=[x[0] for x in st['pts']], km=round(km, 1),
                           ascent=int(props.get('filtered ascend', 0)), mix={c: round(v / 1000, 1) for c, v in mix.items()},
                           routes=[dict(name=k, km=round(v / 1000, 1)) for k, v in onroute.most_common(4) if v >= 1000],
                           signed=round(sum(onroute.values()) / max(1, sum(mix.values())) * 100), collisions=len(seen), ksi=ksi))

    # name each gap by its main road and nearest place
    gap_list = []
    for n, run in gaps:
        k = run['keys'].most_common(1)[0][0]; nm, ref, hw, ms = rinfo[k]
        mid = run['pts'][len(run['pts']) // 2]; pm = P(mid['lat'], mid['lon'])
        place = min(places, key=lambda x: dist(x[1], pm))[0] if places else ''
        nc = sum(1 for c in coll_all.values() if c[3] == n and any(dist(P(c[0], c[1]), P(q['lat'], q['lon'])) < 30 for q in run['pts'][::4]))
        gap_list.append(dict(stage=n, road=nm or ref or 'A road', ref=ref, speed=ms, near=place, km=round(len(run['pts']) * 25 / 1000, 1),
                             at_km=round(run['start']['km'], 1), collisions=nc, lat=round(mid['lat'], 5), lon=round(mid['lon'], 5)))
    # a short break between two runs on the same road is one gap
    merged = []
    for g in sorted(gap_list, key=lambda g: (g['stage'], g['at_km'])):
        m = merged[-1] if merged else None
        if m and m['stage'] == g['stage'] and m['road'] == g['road'] and g['at_km'] - (m['at_km'] + m['km']) < 1:
            m['km'] = round(g['at_km'] + g['km'] - m['at_km'], 1); m['collisions'] += g['collisions']
        else: merged.append(g)
    gap_list = sorted(merged, key=lambda g: -g['km'])

    # simplify map segments a little (keep every 3rd point plus ends)
    for sg in segs: sg['pts'] = sg['pts'][::3] + ([sg['pts'][-1]] if len(sg['pts']) % 3 != 1 else [])
    mix = collections.Counter()
    for st in stages:
        for c, v in st['mix'].items(): mix[c] += v
    out = dict(km=round(total_km, 1), ascent=sum(s['ascent'] for s in stages), mix={c: round(v, 1) for c, v in mix.items()},
               signed=round(sum(s['signed'] * s['km'] for s in stages) / total_km), stages=stages, segments=segs, profile=profile,
               collisions=list(coll_all.values()), gaps=gap_list, sites=SITES)
    json.dump(out, open(os.path.join(HERE, '..', 'data', 'danelaw.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f"{out['km']} km, {out['ascent']} m climbing; mix {dict(out['mix'])}; signed routes {out['signed']}%; "
          f"{len(coll_all)} cycle collisions within 30 m; {len(gap_list)} A-road gaps")
    for s in stages: print(' ', s['n'], s['name'], s['km'], 'km', s['ascent'], 'm', s['mix'], 'signed', s['signed'], '%', s['routes'][:2], 'coll', s['collisions'])
    for g in gap_list[:12]: print('  gap', g)


if __name__ == '__main__':
    main()
