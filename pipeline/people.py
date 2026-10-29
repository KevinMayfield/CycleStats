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
cycle collisions a year per 100 cycle commuters (data/towns.json).
"""
import collections, csv, io, json, math, os, time, urllib.error, urllib.request, zipfile

from industry import model

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
    TJ = {t['id']: t for t in json.load(open(os.path.join(DATA, 'towns.json')))['towns']}
    lb = {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv'))) if r['bua'] in H}
    ls_msoa = {}
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if r[0].startswith('E01'): ls_msoa[r[0]] = r[1][:-1]
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
        tj = TJ.get(tid, {}); a = t['ages']; young = (a['16–24'] + a['25–34']) / 2 if a['16–24'] and a['25–34'] else 0
        if tj.get('cycle11') and young:
            t.update(c11=tj['cycle11'], c21=tj['cycle21'], change=round(tj['cycle21'] / tj['cycle11'], 3), skew=round(a['50–64'] / young, 2),
                     risk=tj.get('coll_rate'), ksi=tj.get('ksi_pct'))
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
    # collisions a year per 100 cycle commuters (towns.py): against the change, the older-rider skew and women's share
    K = sorted([t for t in F if t.get('risk') is not None], key=lambda t: t['risk']); n = len(K)
    risk = [dict(label=lab, towns=len(g), risk=median([t['risk'] for t in g]), women=median([t['women'] for t in g if 'women' in t]),
                 change=median([100 * (t['change'] - 1) for t in g]), skew=median([t['skew'] for t in g]))
            for lab, g in (('Lowest third', K[:n // 3]), ('Middle third', K[n // 3:2 * n // 3]), ('Highest third', K[2 * n // 3:]))]
    KW = [t for t in K if 'women' in t]
    # the clearest cases: cycling fell 15% or more and rests most on older riders, towns with 8,000+ people travelling to work
    strong = [dict(name=t['name'].split(' (')[0], change=round(100 * (t['change'] - 1)), skew=t['skew'], women=t.get('women'), risk=t['risk'])
              for t in sorted(F, key=lambda t: -t['skew']) if t['skew'] >= 1.25 and t['change'] < .85 and t['travel'] >= 8000]
    ageing = dict(towns=len(F), corr=corr([t['skew'] for t in F], [t['change'] for t in F]), bands=bands, model=m, risk=risk, strong=strong,
                  risk_median=median([t['risk'] for t in K]), risk_corr=dict(change=corr([t['risk'] for t in K], [t['change'] for t in K]),
                  skew=corr([t['risk'] for t in K], [t['skew'] for t in K]), women=corr([t['risk'] for t in KW], [t['women'] for t in KW])))
    out = dict(towns=towns, groups=groups, age=age, casualties=casualties(), ageing=ageing,
               corr=corr([math.log(t['cycle']) for t in W if t['cycle'] > 0], [t['women'] for t in W if t['cycle'] > 0]),
               coverage=dict(msoas=cov['with'] + cov['without'], with_sex=cov['with'],
                             cycle_with=round(100 * cov['with_b'] / cov['with_n'], 2), cycle_without=round(100 * cov['without_b'] / cov['without_n'], 2)))
    json.dump(out, open(os.path.join(DATA, 'people.json'), 'w'), separators=(',', ':'))
    print(json.dumps({k: v for k, v in out.items() if k != 'towns'}, indent=1))


if __name__ == '__main__':
    main()
