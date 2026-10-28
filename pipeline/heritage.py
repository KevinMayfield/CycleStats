"""Geography and history: do towns with Norse place names around them cycle more? Writes data/heritage.json for
geography.html.

Every built-up area in the North of England (ONS Built-up Areas 2022, villages included, cached in raw/heritage/) is
classed by its name:
  Norse via Ireland  Norwegian-type endings (-thwaite, -scale(s), -gill, -fell, -keld, -breck, Gaelic-Norse -erg/-argh)
  Danish             -thorpe, -toft
  either             -by, -holme/-hulme, -beck, -garth, kirk-: Norse via Ireland west of the Pennines (about 2.15°W),
                     Danish east of them, as historians usually read the two settlements
  English            everything else
Each town (data/towns.json) gets the share of places within 10 km in each class and a heritage group: Holland (the
Boston and South Holland council areas: the drained Fens, a different landscape); Danish for the Five Boroughs
(Derby, Nottingham, Leicester, Lincoln, Stamford); otherwise the class of the town's own name where that is Norse
(Derby, Selby, Kirkby); otherwise Danish, Norse via Ireland, English or mixed by the places around it. Cycling is compared with what the town's gradient alone predicts (the towns page's fitted curve), and a
regression within the East checks whether Danish names add anything once gradient, deprivation, car ownership and
size are held equal.

The industrial revolution: towns the conurbations grew around against towns that stayed separate. For each town,
  around   people travelling to work in the other towns within 10 km (data/towns.json), a measure of how far it sits
           inside a conurbation rather than on its own
  pt       share commuting by bus, train, tram or metro (Census 2021 TS061 by LSOA, cached in raw/heritage/, matched to
           towns with raw/imd/lsoa_bua.csv)
and, holding hills, deprivation, car ownership and size equal, how much of the West's and North's gap to the East each
explains.
"""
import collections, csv, io, json, math, os, random, re, urllib.parse, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw', 'heritage')
DATA = os.path.join(HERE, '..', 'data')
BUA = 'https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/BUA_2022_GB/FeatureServer/0/query'
BOX = '-3.7,51.9,1.8,55.9'    # the North of England, the East Midlands and East Anglia, from the Scottish border to Suffolk
NEAR_KM = 10
WEST_LON = -2.15              # rough Pennine watershed
NORW = re.compile(r"(thwaite|scales?|gill|fell|keld|breck|erg|ergh|argh|arke)$", re.I)
DAN = re.compile(r"(thorpe|thorp|toft)$", re.I)
SHARED = re.compile(r"(by|bie|holme|hulme|beck|garth)$|^kirk", re.I)
REGION = {**{a: 'North' for a in ('north-east', 'tees-valley', 'cumbria')},
          **{a: 'West' for a in ('greater-manchester', 'liverpool-city-region', 'lancashire', 'cheshire-warrington')}}
HOLLAND = ('Boston', 'South Holland')
# the Five Boroughs, the fortified towns of the Danelaw in the East Midlands: Danish by history whatever the names round them
FIVE_BOROUGHS = ('Derby', 'Nottingham', 'Leicester', 'Lincoln', 'Stamford')
# Cambridge, a university city where 30% cycle to work, is in a class of its own: like Hull and York it is shown on the
# maps but left out of the averages and tests, which it would otherwise swamp
OUTLIERS = ('Cambridge (Cambridge)',)


def places():
    path = os.path.join(RAW, 'bua_north.json')
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        out, off = [], 0
        while True:
            q = dict(where='1=1', outFields='BUA22CD,BUA22NM', returnGeometry='false', returnCentroid='true', outSR='4326', f='json',
                     resultOffset=off, resultRecordCount=1000, geometry=BOX, geometryType='esriGeometryEnvelope', inSR='4326',
                     spatialRel='esriSpatialRelIntersects', orderByFields='OBJECTID')
            fs = json.load(urllib.request.urlopen(BUA + '?' + urllib.parse.urlencode(q), timeout=120))['features']
            out += [[f['attributes']['BUA22CD'], f['attributes']['BUA22NM'], f['centroid']['y'], f['centroid']['x']] for f in fs if f.get('centroid')]
            if len(fs) < 1000: break
            off += 1000
        json.dump(out, open(path, 'w'))
    return json.load(open(path))


def name_class(name, lon):
    words = [w for w in re.findall(r"[A-Za-z']+", re.sub(r"\(.*?\)", '', name)) if len(w) > 3]
    if any(NORW.search(w) for w in words): return 'irish'
    if any(DAN.search(w) for w in words): return 'danish'
    if any(SHARED.search(w) for w in words): return 'irish' if lon < WEST_LON else 'danish'
    return 'english'


def km(a, b, c, d):
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(c - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2))


def lstsq(X, y):
    n = len(X[0]); A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]; b = [sum(r[i] * v for r, v in zip(X, y)) for i in range(n)]
    for i in range(n):
        p = A[i][i]; A[i] = [v / p for v in A[i]]; b[i] /= p
        for k in range(n):
            if k != i:
                f = A[k][i]; A[k] = [u - f * w for u, w in zip(A[k], A[i])]; b[k] -= f * b[i]
    return b


def danish_effect(ts):
    """cycling multiplier for +10 points of Danish names, holding gradient, deprivation, car ownership and size equal,
    with a 95% bootstrap range"""
    X = [[1.0, t['slope'], t['deprived'] / 10, t['nocar'] / 10, math.log(t['travel']), t['danish'] * 10] for t in ts]
    Y = [math.log(t['cycle21']) for t in ts]
    c = lstsq(X, Y)[5]; random.seed(3); bs = []
    for _ in range(1000):
        idx = [random.randrange(len(X)) for _ in X]
        try: bs.append(lstsq([X[i] for i in idx], [Y[i] for i in idx])[5])
        except ZeroDivisionError: pass
    bs.sort()
    return dict(n=len(ts), x=round(math.exp(c), 3), lo=round(math.exp(bs[int(.025 * len(bs))]), 3), hi=round(math.exp(bs[int(.975 * len(bs))]), 3))


def fit(ts, extra):
    """cycling multipliers for the West and North against the East (and for each extra measure), with 95% ranges"""
    reg = lambda t: [float(t['region'] == 'West'), float(t['region'] == 'North')]
    X = [[1.0, t['slope'], t['deprived'] / 10, t['nocar'] / 10, math.log(t['travel'])] + [f(t) for f in extra] + reg(t) for t in ts]
    Y = [math.log(t['cycle21']) for t in ts]
    c = lstsq(X, Y); random.seed(4); bs = []
    for _ in range(500):
        idx = [random.randrange(len(X)) for _ in X]
        try: bs.append(lstsq([X[i] for i in idx], [Y[i] for i in idx]))
        except ZeroDivisionError: pass
    def est(j):
        v = sorted(b[j] for b in bs)
        return dict(x=round(math.exp(c[j]), 3), lo=round(math.exp(v[int(.025 * len(v))]), 3), hi=round(math.exp(v[int(.975 * len(v))]), 3))
    n = len(extra)
    return dict(west=est(5 + n), north=est(6 + n), extra=[est(5 + j) for j in range(n)])


def industrial(out):
    """conurbation and public transport around each town, by region and in the model"""
    z = os.path.join(RAW, 'census2021-ts061.zip')
    if not os.path.exists(z):
        open(z, 'wb').write(urllib.request.urlopen(urllib.request.Request('https://www.nomisweb.co.uk/output/census/2021/census2021-ts061.zip',
                                                                          headers={'User-Agent': 'CycleStats'}), timeout=300).read())
    ids = {t['id'] for t in out}
    lb = {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(HERE, '..', 'raw', 'imd', 'lsoa_bua.csv'))) if r['bua'] in ids}
    agg = collections.defaultdict(collections.Counter)
    pre = 'Method of travel to workplace: '
    for r in csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(z).open('census2021-ts061-lsoa.csv'), encoding='utf-8-sig')):
        b = lb.get(r['geography code'])
        if not b: continue
        k = lambda s: int(r[pre + s]); a = agg[b]
        a['commute'] += k('Total: All usual residents aged 16 years and over in employment the week before the census') - k('Work mainly at or from home')
        a['pt'] += k('Underground, metro, light rail, tram') + k('Train') + k('Bus, minibus or coach')
    for t in out:
        a = agg[t['id']]
        t['pt'] = round(100 * a['pt'] / a['commute'], 1) if a['commute'] else None
        t['around'] = sum(u['travel'] for u in out if u is not t and km(t['lat'], t['lon'], u['lat'], u['lon']) <= NEAR_KM)
    fg = [t for t in out if t['tier'] in ('flat', 'gentle') and t['pt'] is not None and not t['skip']]
    regions = []
    for r in ('East', 'West', 'North'):
        ts = [t for t in fg if t['region'] == r]; w = sum(t['travel'] for t in ts)
        regions.append(dict(region=r, towns=len(ts), cycle=round(sum(t['cycle21'] * t['travel'] for t in ts) / w, 1),
                            pt=round(sum(t['pt'] * t['travel'] for t in ts) / w, 1), around=round(sorted(t['around'] for t in ts)[len(ts) // 2])))
    # flat and gently sloping towns in bands of surrounding workforce: the typical town's cycling against what its hills
    # predict (each town counted once, so Manchester and Liverpool don't swamp their bands)
    bands = []
    for lo, hi, label in ((0, 20000, 'On its own'), (20000, 60000, 'A few towns nearby'), (60000, 150000, 'Edge of a conurbation'), (150000, 10 ** 9, 'Inside a conurbation')):
        ts = [t for t in fg if lo <= t['around'] < hi and not t['skip']]; w = sum(t['travel'] for t in ts)
        if not ts: continue
        bands.append(dict(label=label, lo=lo, hi=hi, towns=len(ts), regions=dict(collections.Counter(t['region'] for t in ts)),
                          cycle=round(sum(t['cycle21'] * t['travel'] for t in ts) / w, 2), expected=round(sum(t['expected'] * t['travel'] for t in ts) / w, 2),
                          ratio=round(math.exp(sum(math.log(t['cycle21'] / t['expected']) for t in ts) / len(ts)), 3),
                          pt=round(sum(t['pt'] * t['travel'] for t in ts) / w, 1),
                          examples=[t['name'] for t in sorted(ts, key=lambda t: -t['travel'])[:4]]))
    U = [t for t in out if not t['skip'] and t['cycle21'] > 0 and t['pt'] is not None]
    con = lambda t: math.log1p(t['around'] / 1000); pt = lambda t: t['pt'] / 10
    models = dict(base=fit(U, []), conurbation=fit(U, [con]), transport=fit(U, [pt]), both=fit(U, [con, pt]))
    return dict(regions=regions, bands=bands, models=models)


def main():
    P = places()
    pl = [dict(name=n, lat=round(la, 4), lon=round(lo, 4), c=name_class(n, lo)) for _, n, la, lo in P]
    towns = json.load(open(os.path.join(DATA, 'towns.json')))['towns']
    out = []
    for t in towns:
        near = [p['c'] for p in pl if km(t['lat'], t['lon'], p['lat'], p['lon']) <= NEAR_KM]
        k = len(near) or 1
        dan, iri = near.count('danish') / k, near.count('irish') / k
        # a town's own Norse name, or its place among the Five Boroughs, outranks the names around it
        own = name_class(t['name'].split(' (')[0], t['lon'])
        group = ('holland' if t['lad'] in HOLLAND else 'danish' if t['name'] in FIVE_BOROUGHS else own if own != 'english'
                 else 'danish' if dan >= .15 and dan >= iri else 'irish' if iri >= .10 else 'english' if dan + iri < .05 else 'mixed')
        out.append(dict(id=t['id'], name=t['name'], area_name=t['area_name'], region=REGION.get(t['area'], 'East'), tier=t['tier'],
                        lat=t['lat'], lon=t['lon'], travel=t['travel'], cycle21=t['cycle21'], expected=t['expected'], slope=t['slope'],
                        deprived=t['deprived'], nocar=t['nocar'], danish=round(dan, 3), irish=round(iri, 3), places=len(near), group=group,
                        skip=t['tier'] == 'bench' or t['name'] in OUTLIERS))
    # each group's cycling against what gradient alone predicts, weighted by people travelling to work (Hull and York left out)
    groups = []
    for g in ('danish', 'holland', 'mixed', 'english', 'irish'):
        ts = [t for t in out if t['group'] == g and not t['skip']]
        w = sum(t['travel'] for t in ts)
        now = sum(t['cycle21'] * t['travel'] for t in ts) / w; exp = sum(t['expected'] * t['travel'] for t in ts) / w
        groups.append(dict(group=g, towns=len(ts), cycle=round(now, 2), expected=round(exp, 2), ratio=round(now / exp, 3),
                           regions=dict(collections.Counter(t['region'] for t in ts)),
                           examples=[t['name'] for t in sorted(ts, key=lambda t: -t['travel'])[:5]]))
    east = [t for t in out if t['region'] == 'East' and not t['skip'] and t['cycle21'] > 0]
    tests = dict(east=danish_effect(east), east_no_holland=danish_effect([t for t in east if t['group'] != 'holland']),
                 east_flat=danish_effect([t for t in east if t['tier'] != 'hilly' and t['group'] != 'holland']))
    villages = [[p['name'], p['lat'], p['lon'], p['c'][0]] for p in pl if p['c'] != 'english']
    ind = industrial(out)
    json.dump(dict(towns=out, groups=groups, tests=tests, industrial=ind, villages=villages, counts=dict(collections.Counter(p['c'] for p in pl)),
                   near_km=NEAR_KM), open(os.path.join(DATA, 'heritage.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for g in groups: print(g)
    print(tests, dict(collections.Counter(p['c'] for p in pl)))
    print(json.dumps(ind, indent=1)[:3000])


if __name__ == '__main__':
    main()
