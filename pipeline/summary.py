"""Cross-area top 10s for summary.html: busiest counts, most collisions, highest risk per rider, and safe & busy roads.
Reads data/<area>.json and raw/<area>/work/ for every area that has been built."""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
RAW = os.path.join(HERE, '..', 'raw')
AREAS = json.load(open(os.path.join(HERE, 'areas.json')))
BUSY = 150  # bikes/day for "safe & busy" across areas (individual areas may use a lower bar)


def km(a, b):
    k = math.cos(math.radians(a[0])) * 111.32
    return math.hypot((a[1] - b[1]) * k, (a[0] - b[0]) * 110.57)


def mid(geom):
    pts = [p for g in geom for p in g]
    return pts[len(pts) // 2]


def where(p, places):
    """'Suburb, Town': the nearest town or city (a city counts as nearer, as it covers more ground),
    with the nearest suburb or village in front when one is close and different"""
    towns = [(km(p, (la, lo)) * (0.5 if t == 'city' else 1), n) for n, la, lo, t in places if t in ('city', 'town')]
    local = [(km(p, (la, lo)), n) for n, la, lo, t in places if t in ('suburb', 'village')]
    town = min(towns)[1] if towns else ''
    near = min(local) if local else (99, '')
    return f'{near[1]}, {town}' if near[0] < 1.5 and near[1] and near[1] != town else town


def main():
    counts, roads, safe = [], [], []
    for aid, cfg in AREAS.items():
        path = os.path.join(DATA, aid + '.json')
        if not os.path.exists(path): continue
        d = json.load(open(path)); places = d['places']
        base = dict(area=aid, area_name=cfg['name'])
        for c in d['counts']:
            counts.append(dict(base, name=c['name'], town=where((c['lat'], c['lon']), places), avg=c['avg'], kind=c['kind'],
                               src=c['src'], period=c['period'], lat=c['lat'], lon=c['lon']))
        for c in json.load(open(os.path.join(RAW, aid, 'work', 'corr_risk.json'))):
            p = mid(c['geom'])
            roads.append(dict(base, name=c['name'], ref=c['ref'], town=where(p, places), km=c['km'], n=c['n'], fatal=c['fatal'],
                              serious=c['serious'], ksi=c['ksi'], aadf=c.get('aadf'), rate=round(c['rate'], 1) if c.get('rate') else None,
                              match=c.get('match'), lat=p[0], lon=p[1]))
        for c in json.load(open(os.path.join(RAW, aid, 'work', 'safe_all.json'))):
            if c['aadf'] < BUSY: continue
            p = mid(c['geom'])
            safe.append(dict(base, name=c['name'], ref=c['ref'], town=where(p, places), km=c['km'], n=c['n'], ksi=c['ksi'],
                             aadf=c['aadf'], rate=c['rate'], lat=p[0], lon=p[1]))
    out = dict(
        popular=sorted(counts, key=lambda c: -c['avg'])[:10],
        collisions=sorted(roads, key=lambda c: (-c['n'], -c['ksi']))[:10],
        risk=sorted([c for c in roads if c['aadf'] and c['aadf'] >= 20 and c['n'] >= 5], key=lambda c: -c['rate'])[:10],
        safe=sorted(safe, key=lambda c: (c['rate'], -c['aadf']))[:10],
        areas=[dict(id=a, name=AREAS[a]['name']) for a in AREAS if os.path.exists(os.path.join(DATA, a + '.json'))],
        busy=BUSY)
    json.dump(out, open(os.path.join(DATA, 'summary.json'), 'w'), ensure_ascii=False, indent=1)
    for k in ('popular', 'collisions', 'risk', 'safe'):
        print(k)
        for c in out[k]:
            print(f"   {c['name'][:30]:30} {c['town'][:28]:28} {c['area_name'][:22]:22} {c.get('avg') or c.get('n')} {c.get('aadf','')} {c.get('rate','')}")


if __name__ == '__main__':
    main()
