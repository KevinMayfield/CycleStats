"""Industry and work: does a town's industrial past show in its cycling, and is COVID-19 linked to cycling or to
industry, deprivation and how far people travel to work? Writes data/industry.json for industry.html.

Industrial past, by council area (data/towns.json lad):
  coal   the historic coalfields: South and West Yorkshire, Nottinghamshire, Derbyshire, North West Leicestershire,
         Durham and Northumberland, Lancashire, West Cumbria
  steel  iron, steel and shipbuilding: Teesside, Scunthorpe, Sheffield, Barrow
Cycling to work (Census 2021) is compared with what the town's gradient predicts, and in a model holding hills,
deprivation, car ownership, size, region and how much town surrounds it equal (data/heritage.json).

COVID-19: deaths registered due to COVID-19 in 2020 and 2021 by MSOA (ONS, deathsduetocovid19registeredinengland
andwales2020, 2021 edition, sheet 7), summed to towns and set against residents (Census 2021). The model adds age
(share aged 65+, TS007A), ethnicity (TS021), work from home and commutes of 10 km or more (TS058), the main industries
(TS060) and the coalfield flag. Downloads are cached in raw/industry/; reading the ONS workbook needs openpyxl once.
"""
import collections, csv, io, json, math, os, random, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
D = os.path.join(RAW, 'industry')
DATA = os.path.join(HERE, '..', 'data')
COAL = {'Barnsley', 'Doncaster', 'Rotherham', 'Wakefield', 'Ashfield', 'Mansfield', 'Bassetlaw', 'Newark and Sherwood', 'Gedling',
        'Broxtowe', 'Bolsover', 'Chesterfield', 'North East Derbyshire', 'Amber Valley', 'Erewash', 'South Derbyshire',
        'North West Leicestershire', 'County Durham', 'Northumberland', 'Sunderland', 'South Tyneside', 'Gateshead', 'Wigan',
        'St. Helens', 'Allerdale', 'Copeland'}
STEEL = {'Middlesbrough', 'Redcar and Cleveland', 'Stockton-on-Tees', 'Hartlepool', 'North Lincolnshire', 'Sheffield', 'Barrow-in-Furness'}
COVID = ('https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/birthsdeathsandmarriages/deaths/datasets/'
         'deathsduetocovid19registeredinenglandandwales2020/2021/covid2021reftables1.xlsx')


def get(url, path):
    if not os.path.exists(path):
        os.makedirs(D, exist_ok=True)
        open(path, 'wb').write(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CycleStats'}), timeout=300).read())
    return path


def census(table, level):
    z = get(f'https://www.nomisweb.co.uk/output/census/2021/census2021-{table}.zip', os.path.join(D, f'{table}.zip'))
    return csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(z).open(f'census2021-{table}-{level}.csv'), encoding='utf-8-sig'))


def covid_msoa():
    """deaths due to COVID-19 registered in 2020 and 2021 by MSOA, from the ONS workbook (converted to CSV once)"""
    path = os.path.join(D, 'covid_msoa.csv')
    if not os.path.exists(path):
        import openpyxl
        wb = openpyxl.load_workbook(get(COVID, os.path.join(D, 'covid2021reftables1.xlsx')), read_only=True)
        with open(path, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['msoa', 'deaths_2021', 'deaths_2020'])
            for r in wb['7'].iter_rows(min_row=6, values_only=True):
                if r[0] and str(r[0]).startswith('E02'): w.writerow([r[0], r[3] or 0, r[4] or 0])
    return {r['msoa']: int(r['deaths_2021']) + int(r['deaths_2020']) for r in csv.DictReader(open(path))}


def lstsq(X, y):
    n = len(X[0]); A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]; b = [sum(r[i] * v for r, v in zip(X, y)) for i in range(n)]
    for i in range(n):
        p = A[i][i]; A[i] = [v / p for v in A[i]]; b[i] /= p
        for k in range(n):
            if k != i:
                f = A[k][i]; A[k] = [u - f * w for u, w in zip(A[k], A[i])]; b[k] -= f * b[i]
    return b


def model(rows, y, cols, seed=7, n=600):
    """multiplier on y for each column, with a 95% bootstrap range, and the share of variation explained"""
    X = [[1.0] + [g(r) for _, g in cols] for r in rows]; Y = [y(r) for r in rows]; c = lstsq(X, Y)
    random.seed(seed); bs = []
    for _ in range(n):
        idx = [random.randrange(len(X)) for _ in X]
        try: bs.append(lstsq([X[i] for i in idx], [Y[i] for i in idx]))
        except ZeroDivisionError: pass
    m = sum(Y) / len(Y); res = [v - sum(a * b for a, b in zip(c, x)) for x, v in zip(X, Y)]
    out = []
    for j, (name, _) in enumerate(cols, 1):
        v = sorted(b[j] for b in bs)
        out.append(dict(name=name, x=round(math.exp(c[j]), 3), lo=round(math.exp(v[int(.025 * len(v))]), 3), hi=round(math.exp(v[int(.975 * len(v))]), 3)))
    return dict(r2=round(1 - sum(e * e for e in res) / sum((v - m) ** 2 for v in Y), 2), terms=out)


def main():
    H = {t['id']: t for t in json.load(open(os.path.join(DATA, 'heritage.json')))['towns']}
    TJ = {t['id']: t for t in json.load(open(os.path.join(DATA, 'towns.json')))['towns']}
    lb = {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv'))) if r['bua'] in H}
    ls_msoa = {}
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if r[0].startswith('E01'): ls_msoa[r[0]] = r[1][:-1]
    mrows = list(census('ts037', 'msoa'))
    msoa_code = {r['geography']: r['geography code'] for r in mrows}
    msoa_pop = {r['geography code']: int(r['General health: Total: All usual residents']) for r in mrows}
    votes = collections.defaultdict(collections.Counter)
    for l, b in lb.items():
        m = msoa_code.get(ls_msoa.get(l))
        if m: votes[m][b] += 1
    m_town = {m: c.most_common(1)[0][0] for m, c in votes.items()}   # each MSOA to the town most of its LSOAs are in
    agg = collections.defaultdict(collections.Counter)
    cov = covid_msoa()
    for m, t in m_town.items():
        if m in cov: agg[t]['deaths'] += cov[m]; agg[t]['pop'] += msoa_pop.get(m, 0)
    old = ('65 to 69 years', '70 to 74 years', '75 to 79 years', '80 to 84 years', '85 years and over')
    for r in census('ts007a', 'lsoa'):
        b = lb.get(r['geography code'])
        if b: agg[b]['res'] += int(r['Age: Total']); agg[b]['old'] += sum(int(r[f'Age: Aged {a}']) for a in old)
    for r in census('ts021', 'lsoa'):
        b = lb.get(r['geography code'])
        if b:
            agg[b]['eth'] += int(r['Ethnic group: Total: All usual residents']); agg[b]['asian'] += int(r['Ethnic group: Asian, Asian British or Asian Welsh'])
            agg[b]['black'] += int(r['Ethnic group: Black, Black British, Black Welsh, Caribbean or African'])
    # distance to work (TS058, raw/imd/ttwdist2021.csv): 0 all, 1 under 2 km, 2 2-5, 3 5-10, 4 10-20, 5 20-30, 6 30-40,
    # 7 40-60, 8 60+, 9 work mainly from home, 10 offshore, no fixed place or abroad
    for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'ttwdist2021.csv'))):
        b = lb.get(r['lsoa'])
        if b: agg[b]['d' + r['band']] += int(r['people'])
    pre = 'Industry (current): '
    for r in census('ts060', 'msoa'):
        t = m_town.get(r['geography code'])
        if not t: continue
        agg[t]['emp'] += int(r[pre + 'Total: All usual residents aged 16 years and over in employment the week before the census'])
        for k, col in (('manuf', 'C: Manufacturing'), ('care', 'Q: Human health and social work activities'), ('mine', 'B: Mining and quarrying')):
            agg[t][k] += int(next(v for kk, v in r.items() if kk.startswith(pre + col)))
    towns = []
    for tid, t in H.items():
        a = agg[tid]; tj = TJ[tid]
        if not (a['pop'] and a['res'] and a['d0'] and a['emp'] and a['eth']): continue
        commute = a['d0'] - a['d9'] - a['d10']
        towns.append(dict(id=tid, name=t['name'], area_name=t['area_name'], region=t['region'], tier=t['tier'], skip=t['skip'],
                          lat=t['lat'], lon=t['lon'], travel=t['travel'], cycle=t['cycle21'], expected=t['expected'], slope=t['slope'],
                          deprived=t['deprived'], nocar=t['nocar'], around=t.get('around'),
                          industry='coal' if tj['lad'] in COAL else 'steel' if tj['lad'] in STEEL else 'other',
                          covid=round(1e5 * a['deaths'] / a['pop'], 1), old=round(100 * a['old'] / a['res'], 1),
                          asian=round(100 * a['asian'] / a['eth'], 1), black=round(100 * a['black'] / a['eth'], 1),
                          wfh=round(100 * a['d9'] / a['d0'], 1), far=round(100 * sum(a[f'd{k}'] for k in (4, 5, 6, 7, 8)) / commute, 1) if commute else 0,
                          manuf=round(100 * a['manuf'] / a['emp'], 1), care=round(100 * a['care'] / a['emp'], 1)))
    U = [t for t in towns if not t['skip'] and t['cycle'] > 0 and t['around'] is not None]
    gm = lambda ts: round(math.exp(sum(math.log(t['cycle'] / t['expected']) for t in ts) / len(ts)), 3)
    groups = []
    for k in ('coal', 'steel', 'other'):
        for tiers, lab in ((('flat', 'gentle'), 'flat'), (('hilly',), 'hilly')):
            ts = [t for t in U if t['industry'] == k and t['tier'] in tiers]
            if ts: groups.append(dict(industry=k, terrain=lab, towns=len(ts), ratio=gm(ts),
                                      examples=[t['name'] for t in sorted(ts, key=lambda t: -t['travel'])[:4]]))
    ctrl = [('hills', lambda t: t['slope']), ('deprived', lambda t: t['deprived'] / 10), ('nocar', lambda t: t['nocar'] / 10),
            ('size', lambda t: math.log(t['travel'])), ('West', lambda t: float(t['region'] == 'West')), ('North', lambda t: float(t['region'] == 'North')),
            ('conurbation', lambda t: math.log1p(t['around'] / 1000))]
    mining = dict(base=model(U, lambda t: math.log(t['cycle']), ctrl),
                  industry=model(U, lambda t: math.log(t['cycle']), ctrl + [('coal', lambda t: float(t['industry'] == 'coal')),
                                                                          ('steel', lambda t: float(t['industry'] == 'steel'))]))
    C = [t for t in U if t['covid'] > 0]
    cv = [('cycling', lambda t: math.log(t['cycle'])), ('aged 65+', lambda t: t['old'] / 10), ('deprived', lambda t: t['deprived'] / 10),
          ('Asian', lambda t: t['asian'] / 10), ('Black', lambda t: t['black'] / 10), ('work from home', lambda t: t['wfh'] / 10),
          ('commute 10 km+', lambda t: t['far'] / 10), ('manufacturing', lambda t: t['manuf'] / 10), ('health and care', lambda t: t['care'] / 10),
          ('coalfield', lambda t: float(t['industry'] == 'coal')), ('size', lambda t: math.log(t['travel'])),
          ('West', lambda t: float(t['region'] == 'West')), ('North', lambda t: float(t['region'] == 'North'))]
    def corr(k):
        xs = [math.log(t['cycle']) if k == 'cycling' else t[k] for t in C]; ys = [t['covid'] for t in C]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        return round(sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)), 2)
    covid = dict(full=model(C, lambda t: math.log(t['covid']), cv), without_cycling=model(C, lambda t: math.log(t['covid']), cv[1:]),
                 corr={k: corr(k) for k in ('cycling', 'old', 'deprived', 'nocar', 'wfh', 'far', 'manuf', 'care', 'asian')},
                 median=round(sorted(t['covid'] for t in C)[len(C) // 2]))
    json.dump(dict(towns=towns, groups=groups, mining=mining, covid=covid), open(os.path.join(DATA, 'industry.json'), 'w'),
              ensure_ascii=False, separators=(',', ':'))
    print(len(towns), 'towns'); print(json.dumps(groups)); print(json.dumps(mining['industry']['terms'][-2:]), mining['base']['terms'][5], mining['industry']['terms'][5])
    print(json.dumps(covid['full']), covid['corr'])


if __name__ == '__main__':
    main()
