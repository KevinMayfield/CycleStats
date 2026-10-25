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


def dedupe(items):
    """keep the first of the same name within 300 m, in case areas overlap"""
    out = []
    for c in items:
        if not any(o['name'] == c['name'] and km((o['lat'], o['lon']), (c['lat'], c['lon'])) < 0.3 for o in out): out.append(c)
    return out


def main():
    counts, roads, safe, dep = [], [], [], []
    for aid, cfg in AREAS.items():
        path = os.path.join(DATA, aid + '.json')
        if not os.path.exists(path): continue
        d = json.load(open(path)); places = d['places']
        base = dict(area=aid, area_name=cfg['name'])
        if d['meta'].get('dep'):
            x = d['meta']['dep']
            dep.append(dict(base, coll=x['coll_share_most'], pop=x['pop_share_most'], n=x['coll_matched']))
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
        popular=dedupe(sorted(counts, key=lambda c: -c['avg']))[:10],
        collisions=dedupe(sorted(roads, key=lambda c: (-c['n'], -c['ksi'])))[:10],
        risk=dedupe(sorted([c for c in roads if c['aadf'] and c['aadf'] >= 20 and c['n'] >= 5], key=lambda c: -c['rate']))[:10],
        safe=dedupe(sorted(safe, key=lambda c: (c['rate'], -c['aadf'])))[:10],
        # share of cycle collisions in the most deprived 20% of neighbourhoods vs share of residents living there
        deprivation=sorted(dep, key=lambda c: -(c['coll'] - c['pop'])),
        areas=[dict(id=a, name=AREAS[a]['name']) for a in AREAS if os.path.exists(os.path.join(DATA, a + '.json'))],
        busy=BUSY)
    json.dump(out, open(os.path.join(DATA, 'summary.json'), 'w'), ensure_ascii=False, indent=1)
    for k in ('popular', 'collisions', 'risk', 'safe'):
        print(k)
        for c in out[k]:
            print(f"   {c['name'][:30]:30} {c['town'][:28]:28} {c['area_name'][:22]:22} {c.get('avg') or c.get('n')} {c.get('aadf','')} {c.get('rate','')}")
    priorities()


def priorities():
    """Where to build: road stretches where protected cycle infrastructure would most improve safety and use.
      safety  = harm per year x share of the stretch without protection
                harm = collisions + 2 x killed/seriously injured (so a KSI counts 3), over 5 years. A total for the
                stretch, not per km: a protected route along a whole corridor prevents the corridor's harm
      use     = PCT 'Go Dutch' commuters + school pupils minus those cycling now (2011 Census / school census)
      both    = geometric mean of the two, each scaled to the 90th percentile of eligible stretches
    Eligible: 0.5 km or longer and at least half without protection; safety and 'both' also need 5+ collisions."""
    rows, women, children, cas_n = [], [], [], 0
    for aid, cfg in AREAS.items():
        path = os.path.join(RAW, aid, 'work', 'priorities.json')
        if not os.path.exists(path): continue
        places = json.load(open(os.path.join(DATA, aid + '.json')))['places']
        for c in json.load(open(path)):
            unprot = max(0.0, 1 - c['protected'] - 0.5 * c['lane'])
            harm = (c['n'] + 2 * c['ksi']) / 5
            c.update(area=aid, area_name=cfg['name'], town=where((c['lat'], c['lon']), places), unprot=round(unprot, 2),
                     harm=round(harm, 2), per_km=round(harm / max(c['km'], 1), 2), safety=round(harm * unprot, 3),
                     uplift=max(0, c['pct_dutch'] - c['pct_now']) + max(0, c['school_dutch'] - c['school_now']))
            rows.append(c)
    elig = [c for c in rows if c['unprot'] >= 0.5]
    hurt = [c for c in elig if c['n'] >= 5]
    p90 = lambda key, xs: sorted(x[key] for x in xs)[int(0.9 * len(xs))] or 1
    ps, pu = p90('safety', hurt), p90('uplift', hurt)
    for c in hurt: c['both'] = round((min(c['safety'] / ps, 1.5) * min(c['uplift'] / pu, 1.5)) ** 0.5, 3)
    slim = lambda xs: [{k: v for k, v in c.items() if k != 'geom'} | dict(geom=c['geom']) for c in xs]
    best = dedupe(sorted(hurt, key=lambda c: -c['both']))
    per_area = {}
    for c in best:
        if len(per_area.setdefault(c['area'], [])) < 3: per_area[c['area']].append(c)
    # who gets hurt: across every measured stretch with casualties (each casualty counted once per stretch)
    tot = lambda key: sum(c[key] * c['casualties'] / 100 for c in rows if c[key] is not None)
    known = sum(c['casualties'] for c in rows if c['women'] is not None)
    out = dict(
        both=slim(best[:10]),
        safety=slim(dedupe(sorted(hurt, key=lambda c: -c['safety']))[:10]),
        use=slim(dedupe(sorted(elig, key=lambda c: -c['uplift']))[:10]),
        per_area={a: [{k: v for k, v in c.items() if k != 'geom'} for c in xs] for a, xs in per_area.items()},
        stats=dict(stretches=len(rows), eligible=len(hurt), women=round(100 * tot('women') / known) if known else None,
                   children=round(100 * tot('children') / known) if known else None,
                   pct_now=sum(c['pct_now'] for c in best[:10]), pct_dutch=sum(c['pct_dutch'] for c in best[:10]),
                   pct_women=sum(c['pct_women'] for c in best[:10])),
        areas=[dict(id=a, name=AREAS[a]['name']) for a in AREAS if os.path.exists(os.path.join(DATA, a + '.json'))])
    json.dump(out, open(os.path.join(DATA, 'priorities.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for k in ('both', 'safety', 'use'):
        print('priorities', k)
        for c in out[k]:
            print(f"   {c['name'][:24]:24} {c['town'][:24]:24} {c['area_name'][:14]:14} n={c['n']:2} ksi={c['ksi']:2} km={c['km']:5} "
                  f"prot={c['protected']} part={c['lane']} commuters {c['pct_now']}->{c['pct_dutch']} school {c['school_now']}->{c['school_dutch']} "
                  f"women%={c['women']}")
    print(out['stats'])


if __name__ == '__main__':
    main()
