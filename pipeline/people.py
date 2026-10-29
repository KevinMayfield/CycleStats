"""Who cycles: women's share of cycle commuters and cycling by age, for every town. Writes data/people.json for
people.html.

Census 2021 method of travel to work by sex and by age (6 bands) for each MSOA, from the ONS API
(api.beta.ons.gov.uk, population type UR, transport_to_workplace_12a). Each MSOA goes to the town most of its LSOAs
are in, as in industry.py. ONS withholds the sex breakdown for about a third of MSOAs (disclosure control), so a town
gets a women's share only where at least half its commuters are covered. Rates are cyclists over people travelling to
work (not working from home). Downloads are cached in raw/people/.

Cyclist casualties (STATS19 2021-25, raw/dft/cycle_cas.csv, with each collision's council from
raw/health/cycle_collision_lad.csv) give the women's and children's share of casualties by council, against Census
cycling to work, for every council in England.

An ageing cycling culture: for flat and gently sloping towns, cycling to work in 2011 (PCT, Census 2011) against 2021,
set against how much more 50-64s cycle than 16-34s, with a model holding the 2011 level and region equal, and set against
cycle collisions per weekly cyclist (an index, below).

Women and deprivation: each MSOA's women's share of cycle commuters against its IMD 2025 score (the mean of its LSOAs),
in fifths and within towns, and towns in thirds by their share of deprived neighbourhoods. Each town also gets cycle collisions a year per
10,000 residents (Census 2021 TS007A), a measure of danger that does not depend on how many people already cycle.
"""
import collections, csv, io, json, math, os, time, urllib.error, urllib.request, zipfile

from industry import lstsq, model

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
D = os.path.join(RAW, 'people')
DATA = os.path.join(HERE, '..', 'data')
API = 'https://api.beta.ons.gov.uk/v1/population-types/UR/census-observations?area-type=msoa,{}&dimensions={},transport_to_workplace_12a'
NOT = ('Not in employment or aged 15 years and under', 'Work mainly at or from home')
AGES = [('Aged 16 to 24 years', '16–24'), ('Aged 25 to 34 years', '25–34'), ('Aged 35 to 49 years', '35–49'),
        ('Aged 50 to 64 years', '50–64'), ('Aged 65 years and over', '65+')]


def fetch(dim, msoas):
    """MSOA x dim x travel mode counts, cached; MSOAs the API withholds are skipped"""
    path = os.path.join(D, f'msoa_{dim}_transport_to_workplace_12a.csv')
    held = path[:-4] + '_withheld.txt'   # MSOAs the API refuses, so later runs do not ask again
    done = {r['msoa'] for r in csv.DictReader(open(path))} if os.path.exists(path) else set()
    if os.path.exists(held): done |= set(open(held).read().split())
    todo = [m for m in msoas if m not in done]
    if todo:
        os.makedirs(D, exist_ok=True)
        f = open(path, 'a', newline=''); w = csv.writer(f)
        if not os.path.getsize(path): w.writerow(['msoa', 'cat', 'cat_id', 'mode', 'n'])
        hf = open(held, 'a')

        def get(batch):
            for _ in range(4):
                try:
                    req = urllib.request.Request(API.format(','.join(batch), dim), headers={'User-Agent': 'CycleStats'})
                    return json.load(urllib.request.urlopen(req, timeout=120))['observations']
                except urllib.error.HTTPError as e:
                    if e.code != 400: time.sleep(3); continue
                    if len(batch) == 1: hf.write(batch[0] + '\n'); return []
                    h = len(batch) // 2; return get(batch[:h]) + get(batch[h:])
                except OSError: time.sleep(3)
            return []
        for i in range(0, len(todo), 40):
            for o in get(todo[i:i + 40]):
                d = o['dimensions']; w.writerow([d[0]['option_id'], d[1]['option'], d[1]['option_id'], d[2]['option'], o['observation']])
            f.flush(); hf.flush()
        f.close(); hf.close()
    out = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in csv.DictReader(open(path)): out[r['msoa']][r['cat']][r['mode']] += int(r['n'])
    return out


def rate(c):
    return c['Bicycle'], sum(v for k, v in c.items() if k not in NOT)


def corr(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x)); sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy), 2)


def median(v):
    v = sorted(v); n = len(v)
    return round((v[n // 2] + v[(n - 1) // 2]) / 2, 1) if n else None


# Active Lives (Sport England, DfT CW0302, downloaded by hand to raw/activelives/cw0302.ods): adults who cycle at least
# once a week for any purpose, by council. Councils merged in 2023 are only given as the new council.
NEW_COUNCIL = {'E07000026': 'E06000063', 'E07000028': 'E06000063', 'E07000029': 'E06000063',
               'E07000027': 'E06000064', 'E07000030': 'E06000064', 'E07000031': 'E06000064',
               **{f'E070001{n}': 'E06000065' for n in range(63, 70)}}


def ods_rows(path, sheet):
    import xml.etree.ElementTree as ET
    T = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'; O = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
    X = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
    for t in ET.parse(zipfile.ZipFile(path).open('content.xml')).getroot().iter(T + 'table'):
        if t.get(T + 'name') != sheet: continue
        for r in t.iter(T + 'table-row'):
            row = []
            for c in r:
                v = c.get(O + 'value')
                if v is None: v = ' '.join(''.join(p.itertext()) for p in c.iter(X + 'p'))
                row += [v] * min(int(c.get(T + 'number-columns-repeated', '1')), 20)
            yield row


def weekly_ratio():
    """for each 2021 council, adults who cycle weekly (Active Lives, mean of 2019, 2022 and 2023, leaving out the
    pandemic years) for each person who cycles to work (Census 2021), pooled over councils merged since"""
    al = {}
    for r in ods_rows(os.path.join(RAW, 'activelives', 'cw0302.ods'), 'CW0302'):
        if len(r) < 14 or r[4] != 'Any' or r[5] != 'At least once per week': continue
        v = [float(x) for x in (r[9], r[12], r[13]) if x.replace('.', '', 1).isdigit()]
        if v: al[r[0]] = sum(v) / len(v)
    adults, bikes = collections.Counter(), collections.Counter()
    z = zipfile.ZipFile(os.path.join(RAW, 'industry', 'ts007a.zip'))
    for r in csv.DictReader(io.TextIOWrapper(z.open('census2021-ts007a-ltla.csv'), encoding='utf-8-sig')):
        kids = sum(int(r[f'Age: Aged {a}']) for a in ('4 years and under', '5 to 9 years', '10 to 14 years')) + int(r['Age: Aged 15 to 19 years']) / 5
        adults[NEW_COUNCIL.get(r['geography code'], r['geography code'])] += int(r['Age: Total']) - kids
    names = {}
    for r in csv.reader(io.TextIOWrapper(zipfile.ZipFile(os.path.join(RAW, 'heritage', 'census2021-ts061.zip')).open('census2021-ts061-ltla.csv'))):
        if r[0] == 'date': continue
        names[r[1]] = r[2]; bikes[NEW_COUNCIL.get(r[2], r[2])] += int(r[12])
    ratio = {k: al[k] / 100 * adults[k] / bikes[k] for k in al if adults[k] and bikes[k]}
    return {n: ratio.get(NEW_COUNCIL.get(c, c)) for n, c in names.items()}


def casualties():
    cen = {}
    for r in csv.reader(io.TextIOWrapper(zipfile.ZipFile(os.path.join(RAW, 'heritage', 'census2021-ts061.zip')).open('census2021-ts061-ltla.csv'))):
        if r[0] != 'date': cen[r[2]] = 100 * int(r[12]) / (int(r[3]) - int(r[4]))
    lad = {r['collision_index']: r['local_authority_ons_district'] for r in csv.DictReader(open(os.path.join(RAW, 'health', 'cycle_collision_lad.csv')))}
    C = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_cas.csv'))):
        l = lad.get(r['collision_index'])
        if r['casualty_type'] != '1' or l not in cen: continue
        c = C[l]
        if r['sex_of_casualty'] in ('1', '2'): c['sexn'] += 1; c['f'] += r['sex_of_casualty'] == '2'
        if int(r['age_of_casualty']) >= 0: c['agen'] += 1; c['u16'] += int(r['age_of_casualty']) < 16
    bands = [('Under 2%', 0, 2), ('2–4%', 2, 4), ('4–8%', 4, 8), ('8% or more', 8, 100)]
    out = []
    for lab, lo, hi in bands:
        cs = [C[l] for l in C if l.startswith('E') and lo <= cen[l] < hi and C[l]['sexn'] >= 30]
        out.append(dict(band=lab, councils=len(cs), casualties=sum(c['sexn'] for c in cs),
                        women=round(100 * sum(c['f'] for c in cs) / sum(c['sexn'] for c in cs), 1),
                        children=round(100 * sum(c['u16'] for c in cs) / sum(c['agen'] for c in cs), 1)))
    return out


def main():
    H = {t['id']: t for t in json.load(open(os.path.join(DATA, 'heritage.json')))['towns']}
    I = {t['id']: t for t in json.load(open(os.path.join(DATA, 'industry.json')))['towns']}
    TJD = json.load(open(os.path.join(DATA, 'towns.json'))); TJ = {t['id']: t for t in TJD['towns']}; YEARS = len(TJD['coll_years'])
    lb = {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv'))) if r['bua'] in H}
    ls_msoa, imd = {}, {}   # LSOA to MSOA name, and LSOA IMD 2025 score
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if r[0].startswith('E01'): ls_msoa[r[0]] = r[1][:-1]; imd[r[0]] = float(r[4])
    mrows = csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(os.path.join(RAW, 'industry', 'ts037.zip')).open('census2021-ts037-msoa.csv'), encoding='utf-8-sig'))
    code = {r['geography']: r['geography code'] for r in mrows}
    votes = collections.defaultdict(collections.Counter)
    for l, b in lb.items():
        m = code.get(ls_msoa.get(l))
        if m: votes[m][b] += 1
    m_town = {m: c.most_common(1)[0][0] for m, c in votes.items()}
    S = fetch('sex', sorted(m_town)); A = fetch('resident_age_6a', sorted(m_town))
    cov = collections.Counter()
    for m in A:
        b = sum(rate(c)[0] for c in A[m].values()); n = sum(rate(c)[1] for c in A[m].values())
        k = 'with' if m in S else 'without'; cov[k + '_b'] += b; cov[k + '_n'] += n; cov[k] += 1
    wr = weekly_ratio()
    pop = collections.Counter()   # usual residents (Census 2021 TS007A), for collisions per head
    for r in csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(os.path.join(RAW, 'industry', 'ts007a.zip')).open('census2021-ts007a-lsoa.csv'), encoding='utf-8-sig')):
        if r['geography code'] in lb: pop[lb[r['geography code']]] += int(r['Age: Total'])
    T = collections.defaultdict(collections.Counter)
    for m, t in m_town.items():
        for a, c in A.get(m, {}).items():
            b, n = rate(c); T[t]['b' + a] += b; T[t]['n' + a] += n; T[t]['n'] += n; T[t]['b'] += b
        for s, c in S.get(m, {}).items():
            b, n = rate(c); T[t]['b' + s] += b; T[t]['n' + s] += n; T[t]['sexn'] += n
    towns = []
    for tid, c in T.items():
        h = H[tid]; i = I.get(tid)
        if not i or c['n'] < 2000: continue
        around = h.get('around') or 0
        t = dict(id=tid, name=h['name'], region=h['region'], tier=h['tier'], skip=h['skip'], industry=i['industry'],
                 setting='own' if around < 20000 else 'few' if around < 60000 else 'edge' if around < 150000 else 'inside',
                 lat=h['lat'], lon=h['lon'], travel=h['travel'], cycle=round(100 * c['b'] / c['n'], 2),
                 ages={lab: round(100 * c['b' + a] / c['n' + a], 2) if c['n' + a] else None for a, lab in AGES})
        if c['sexn'] >= .5 * c['n'] and c['bFemale'] + c['bMale'] >= 50:
            t.update(women=round(100 * c['bFemale'] / (c['bFemale'] + c['bMale']), 1),
                     f=round(100 * c['bFemale'] / c['nFemale'], 2), m=round(100 * c['bMale'] / c['nMale'], 2))
        tj = TJ.get(tid, {}); a = t['ages']
        if pop[tid] and 'coll' in tj:   # cycle collisions a year per 10,000 residents, and how many were serious
            t.update(pop=pop[tid], coll_pop=round(1e4 * tj['coll'] / YEARS / pop[tid], 2), ksi_pop=round(1e4 * tj['coll_ksi'] / YEARS / pop[tid], 2))
        if tj.get('coll_rate') is not None: t['coll_rider'] = tj['coll_rate']   # cycle collisions a year per 100 cycle commuters
        k = next((v for n, v in wr.items() if n == tj.get('lad') or n.startswith(f"{tj.get('lad')},")), None)
        if k and tj.get('cyclists') and 'coll' in tj:   # weekly cyclists: the town's cycle commuters times its council's ratio
            t['weekly'] = round(tj['cyclists'] * k); t['coll_weekly'] = tj['coll'] / YEARS / t['weekly']
        young = (a['16–24'] + a['25–34']) / 2 if a['16–24'] and a['25–34'] else 0
        if tj.get('cycle11') and young:
            t.update(c11=tj['cycle11'], c21=tj['cycle21'], change=round(tj['cycle21'] / tj['cycle11'], 3), skew=round(a['50–64'] / young, 2), ksi=tj.get('ksi_pct'))
        towns.append(t)
    U = [t for t in towns if not t['skip'] or t['name'].split(' (')[0] in ('York', 'Cambridge')]
    W = [t for t in U if 'women' in t]
    LAB = dict(cycling={'1': 'Under 2%', '2': '2–4%', '3': '4–8%', '4': '8% or more'},
               tier={'flat': 'Flat', 'gentle': 'Gently sloping', 'hilly': 'Hilly'},
               setting={'own': 'On its own', 'few': 'A few towns nearby', 'edge': 'Edge of a conurbation', 'inside': 'Inside a conurbation'},
               industry={'other': 'Other towns', 'steel': 'Iron, steel and shipbuilding', 'coal': 'Coalfield towns'},
               region={'East': 'Yorkshire and the East', 'West': 'North West', 'North': 'North East and Cumbria'})
    key = dict(cycling=lambda t: '1' if t['cycle'] < 2 else '2' if t['cycle'] < 4 else '3' if t['cycle'] < 8 else '4',
               tier=lambda t: t['tier'], setting=lambda t: t['setting'], industry=lambda t: t['industry'], region=lambda t: t['region'])
    groups = {}
    for by, labs in LAB.items():
        groups[by] = []
        for k, lab in labs.items():
            g = [t for t in W if key[by](t) == k]
            if len(g) >= 3:
                groups[by].append(dict(key=k, label=lab, towns=len(g), women=median([t['women'] for t in g]),
                                       f=median([t['f'] for t in g]), m=median([t['m'] for t in g]),
                                       examples=[t['name'].split(' (')[0] for t in sorted(g, key=lambda t: -t['travel'])[:4]]))
    # cycling by age, pooled over flat towns on their own and over hilly or conurbation towns
    pools = [('Flat towns on their own', lambda t: t['tier'] == 'flat' and t['setting'] == 'own'),
             ('All towns', lambda t: True), ('Hilly towns and conurbations', lambda t: t['tier'] == 'hilly' or t['setting'] == 'inside')]
    age = []
    for lab, f in pools:
        g = [t['id'] for t in U if f(t) and not t['name'].startswith('Cambridge')]   # Cambridge's students would swamp the pools
        age.append(dict(label=lab, towns=len(g), rates={al: round(100 * sum(T[i]['b' + a] for i in g) / sum(T[i]['n' + a] for i in g), 2) for a, al in AGES}))
    # collisions per weekly cyclist as an index, the typical town of 8,000+ commuters = 100: it compares towns and is not
    # a rider's chance of a crash (collisions count every rider of every age and trip, weekly cyclists only adults)
    mid = sorted(t['coll_weekly'] for t in towns if t['travel'] >= 8000 and 'coll_weekly' in t); mid = mid[len(mid) // 2]
    for t in towns:
        if 'coll_weekly' in t: t['rider_index'] = round(100 * t.pop('coll_weekly') / mid)
    # an ageing cycling culture: flat and gently sloping towns where at least 1.5% cycle; skew in steps of 0.25
    F = [t for t in towns if t['tier'] in ('flat', 'gentle') and not t['skip'] and 'change' in t and t['c21'] >= 1.5]
    bands = []
    for lab, lo, hi in (('Rose', 1, 99), ('Fell by up to a quarter', .75, 1), ('Fell by a quarter or more', 0, .75)):
        g = [t for t in F if lo <= t['change'] < hi]
        bands.append(dict(label=lab, towns=len(g), c11=median([t['c11'] for t in g]), c21=median([t['c21'] for t in g]),
                          women=median([t['women'] for t in g if 'women' in t]), skew=median([t['skew'] for t in g]),
                          old=median([t['ages']['65+'] / ((t['ages']['16–24'] + t['ages']['25–34']) / 2) for t in g]),
                          examples=[t['name'].split(' (')[0] for t in sorted(g, key=lambda t: -t['travel'])[:5]]))
    m = model(F, lambda t: math.log(t['change']), [('skew', lambda t: t['skew'] * 4), ('2011 level', lambda t: math.log(t['c11'])),
                                                    ('North', lambda t: t['region'] == 'North'), ('West', lambda t: t['region'] == 'West')])
    # collisions per weekly cyclist (the index): against the change, the older-rider skew and women's share
    for t in F: t['risk'] = t.get('rider_index')
    K = sorted([t for t in F if t['risk'] is not None], key=lambda t: t['risk']); n = len(K)
    risk = [dict(label=lab, towns=len(g), risk=median([t['risk'] for t in g]), women=median([t['women'] for t in g if 'women' in t]),
                 change=median([100 * (t['change'] - 1) for t in g]), skew=median([t['skew'] for t in g]))
            for lab, g in (('Lowest third', K[:n // 3]), ('Middle third', K[n // 3:2 * n // 3]), ('Highest third', K[2 * n // 3:]))]
    KW = [t for t in K if 'women' in t]
    # the clearest cases: cycling fell 15% or more and rests most on older riders, towns with 8,000+ people travelling to work
    strong = [dict(name=t['name'].split(' (')[0], change=round(100 * (t['change'] - 1)), skew=t['skew'], women=t.get('women'), risk=t.get('rider_index'))
              for t in sorted(F, key=lambda t: -t['skew']) if t['skew'] >= 1.25 and t['change'] < .85 and t['travel'] >= 8000]
    ageing = dict(towns=len(F), corr=corr([t['skew'] for t in F], [t['change'] for t in F]), bands=bands, model=m, risk=risk, strong=strong,
                  risk_median=median([t['risk'] for t in K]), risk_corr=dict(change=corr([t['risk'] for t in K], [t['change'] for t in K]),
                  skew=corr([t['risk'] for t in K], [t['skew'] for t in K]), women=corr([t['risk'] for t in KW], [t['women'] for t in KW])))
    # women and deprivation: neighbourhoods (MSOAs with 20+ cycle commuters) by IMD 2025 score (mean of their LSOAs),
    # in fifths and within towns (each neighbourhood against its own town's average), and towns in thirds
    mimd = collections.defaultdict(list)
    for l, m in ls_msoa.items():
        if m in code: mimd[code[m]].append(imd[l])
    M = []
    for m, sx in S.items():
        f, ma = sx['Female']['Bicycle'], sx['Male']['Bicycle']
        if m in mimd and f + ma >= 20:
            M.append(dict(town=m_town.get(m), imd=sum(mimd[m]) / len(mimd[m]), women=100 * f / (f + ma),
                          cyc=100 * (f + ma) / (rate(sx['Female'])[1] + rate(sx['Male'])[1])))
    M.sort(key=lambda x: x['imd']); n = len(M)
    fifths = [dict(label=lab, msoas=len(g), imd=median([x['imd'] for x in g]), cycle=median([x['cyc'] for x in g]), women=median([x['women'] for x in g]))
              for lab, g in zip(('Least deprived fifth', 'Second', 'Middle', 'Fourth', 'Most deprived fifth'), [M[k * n // 5:(k + 1) * n // 5] for k in range(5)])]
    byt = collections.defaultdict(list)
    for x in M:
        if x['town']: byt[x['town']].append(x)
    dx, dy, dc = [], [], []
    for g in byt.values():
        if len(g) < 3: continue
        mi, mw, mc = (sum(f(x) for x in g) / len(g) for f in (lambda x: x['imd'], lambda x: x['women'], lambda x: math.log(x['cyc'])))
        for x in g: dx.append((x['imd'] - mi) / 10); dy.append(x['women'] - mw); dc.append(math.log(x['cyc']) - mc)
    within = round(lstsq([[1.0, a, c] for a, c in zip(dx, dc)], dy)[1], 2)
    D3 = sorted([t for t in W if t['id'] in I], key=lambda t: I[t['id']]['deprived']); n3 = len(D3)
    thirds = [dict(label=lab, towns=len(g), deprived=median([I[t['id']]['deprived'] for t in g]), cycle=median([t['cycle'] for t in g]),
                   women=median([t['women'] for t in g]), f=median([t['f'] for t in g]), m=median([t['m'] for t in g]))
              for lab, g in (('Least deprived third', D3[:n3 // 3]), ('Middle third', D3[n3 // 3:2 * n3 // 3]), ('Most deprived third', D3[2 * n3 // 3:]))]
    hull = next((t for t in towns if t['name'] == 'Kingston upon Hull'), None)
    hull_deprived = [x for x in byt.get(hull['id'], []) if x['imd'] >= 40] if hull else []
    deprivation = dict(msoas=n, fifths=fifths, within=within, within_n=len(dx), thirds=thirds,
                       hull=dict(cycle=[round(min(x['cyc'] for x in hull_deprived), 1), round(max(x['cyc'] for x in hull_deprived), 1)],
                                 women=[round(min(x['women'] for x in hull_deprived)), round(max(x['women'] for x in hull_deprived))]) if hull_deprived else None)
    out = dict(towns=towns, groups=groups, age=age, casualties=casualties(), ageing=ageing, deprivation=deprivation,
               coll_pop_median=median([t['coll_pop'] for t in towns if t['travel'] >= 8000 and 'coll_pop' in t]),
               coll_rider_median=median([t['coll_rider'] for t in towns if t['travel'] >= 8000 and 'coll_rider' in t]),
               corr=corr([math.log(t['cycle']) for t in W if t['cycle'] > 0], [t['women'] for t in W if t['cycle'] > 0]),
               coverage=dict(msoas=cov['with'] + cov['without'], with_sex=cov['with'],
                             cycle_with=round(100 * cov['with_b'] / cov['with_n'], 2), cycle_without=round(100 * cov['without_b'] / cov['without_n'], 2)))
    json.dump(out, open(os.path.join(DATA, 'people.json'), 'w'), separators=(',', ':'))
    print(json.dumps({k: v for k, v in out.items() if k != 'towns'}, indent=1))


if __name__ == '__main__':
    main()
