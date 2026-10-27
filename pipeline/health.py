"""Health and active travel: which towns have health problems linked to too little exercise, how many people cycle
there now, and where more cycling would do most good. Writes data/health.json for health.html.

Health need for each town (data/towns.json), each measure as a ratio to England (100 = England):
  inactive    adults doing under 30 minutes of activity a week, Active Lives (OHID Fingertips 93015), by council
  overweight  adults overweight or obese (Fingertips 93088), by council
  diabetes    diagnosed diabetes, QOF (Fingertips 241), by council
  child_obese Year 6 children obese, 3 years combined (Fingertips 93107), by MSOA, averaged over the town's MSOAs
  health_dep  share of the town's LSOAs in England's most deprived fifth for health and disability (IMD 2025; the
              domain is built from standardised rates, so it is less driven by age than raw ill health)
  need        the average of the five ratios, each capped at 200 (twice England) so no one measure swamps the rest
Census 2021 general health (TS037, bad or very bad) is kept for reference; it rises with age, so it is not in need.

Benefit of more cycling, from the Propensity to Cycle Tool zones (raw/pct/*_z.csv, commuting only, WHO HEAT method):
  deaths      premature deaths a year avoided if commuting matched the Go Dutch scenario
  value       the value of the health gains a year (deaths and sickness), in pounds
Health gain score: need / 100 x the gap between Go Dutch and today's cycling to work (percentage points). It is high
where people are least healthy and most of the potential for cycling is unused.

Road danger for each ICB: cyclists killed, seriously injured and slightly injured where the collision happened
(police-reported STATS19, 2021-25, raw/dft/cycle_cas.csv with each collision's council from the national collision file,
cached as raw/health/cycle_collision_lad.csv), against people who cycle to work (Census 2021) as a rough measure of
exposure. Scenarios: every board at the lowest killed-or-seriously-injured rate among them; and how far risk per rider
must fall for casualties not to rise if commuting grew to Go Dutch.

Safety projection for the flat and gently sloping towns: safety in numbers measured across towns (log collisions a
year against log people cycling to work, holding town size fixed by log people travelling to work; the same for
killed or seriously injured), then each town's casualties scaled to the cycling of each scenario. With protected
routes applies the gap between protected and unprotected stretches per bike-km measured from the site's own road
stretches (raw/<area>/work/priorities.json with DfT cycle counts).

Downloads (cached in raw/health/): Fingertips CSVs and Census 2021 TS037, fetched with /usr/bin/python3 on Kevin's Mac.
"""
import collections, csv, io, json, os, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
H = os.path.join(RAW, 'health')
DATA = os.path.join(HERE, '..', 'data')
# NHS integrated care boards (2022 boundaries) by council, using the 2011 council names in the PCT zone files.
# North East and North Cumbria is covered except North Cumbria, which sits in the PCT's North West region.
ICB = {
    'NHS West Yorkshire': ['Bradford', 'Calderdale', 'Kirklees', 'Leeds', 'Wakefield'],
    'NHS South Yorkshire': ['Barnsley', 'Doncaster', 'Rotherham', 'Sheffield'],
    'NHS Humber and North Yorkshire': ['Kingston upon Hull, City of', 'East Riding of Yorkshire', 'North East Lincolnshire', 'North Lincolnshire',
                                       'York', 'Craven', 'Hambleton', 'Harrogate', 'Richmondshire', 'Ryedale', 'Scarborough', 'Selby'],
    'NHS Lincolnshire': ['Boston', 'East Lindsey', 'Lincoln', 'North Kesteven', 'South Holland', 'South Kesteven', 'West Lindsey'],
    'NHS Nottingham and Nottinghamshire': ['Nottingham', 'Ashfield', 'Bassetlaw', 'Broxtowe', 'Gedling', 'Mansfield', 'Newark and Sherwood', 'Rushcliffe'],
    'NHS Derby and Derbyshire': ['Derby', 'Amber Valley', 'Bolsover', 'Chesterfield', 'Derbyshire Dales', 'Erewash', 'High Peak',
                                 'North East Derbyshire', 'South Derbyshire'],
    'NHS Leicester, Leicestershire and Rutland': ['Leicester', 'Blaby', 'Charnwood', 'Harborough', 'Hinckley and Bosworth', 'Melton',
                                                  'North West Leicestershire', 'Oadby and Wigston', 'Rutland'],
    'NHS North East and North Cumbria': ['County Durham', 'Darlington', 'Gateshead', 'Hartlepool', 'Middlesbrough', 'Newcastle upon Tyne',
                                         'North Tyneside', 'Redcar and Cleveland', 'South Tyneside', 'Stockton-on-Tees', 'Sunderland'],
}
ICB_NOTE = {'NHS North East and North Cumbria': 'excluding North Cumbria'}
FT = [(93015, 501, 'inactive'), (93088, 501, 'overweight'), (241, 501, 'diabetes'), (93107, 3, 'child_obese')]


def fetch(url, path):
    if not os.path.exists(path):
        print('download', url)
        open(path, 'wb').write(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CycleStats'}), timeout=300).read())
    return path


def fingertips(ind, area_type):
    """latest value for every area (Persons, no category breakdown), and England's"""
    p = fetch(f'https://fingertips.phe.org.uk/api/all_data/csv/by_indicator_id?indicator_ids={ind}&child_area_type_id={area_type}',
              os.path.join(H, f'fingertips_{ind}_{area_type}.csv'))
    rows = [r for r in csv.DictReader(open(p, encoding='utf-8-sig')) if r['Sex'] == 'Persons' and not r['Category Type'] and r['Value']]
    latest = max(r['Time period Sortable'] for r in rows)
    rows = [r for r in rows if r['Time period Sortable'] == latest]
    age = collections.Counter(r['Age'] for r in rows if r['Area Type'] != 'England').most_common(1)[0][0]   # England also has age bands
    rows = [r for r in rows if r['Age'] == age]
    eng = next(float(r['Value']) for r in rows if r['Area Type'] == 'England')
    return {r['Area Code']: float(r['Value']) for r in rows if r['Area Type'] != 'England'}, eng, rows[0]['Time period']


def lstsq(X, y):
    """least squares by the normal equations (small, well-conditioned problems only)"""
    n = len(X[0]); A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]; b = [sum(r[i] * v for r, v in zip(X, y)) for i in range(n)]
    for i in range(n):
        p = A[i][i]; A[i] = [v / p for v in A[i]]; b[i] /= p
        for k in range(n):
            if k != i:
                f = A[k][i]; A[k] = [u - f * w for u, w in zip(A[k], A[i])]; b[k] -= f * b[i]
    return b


def safety_projection(towns, years, bench_share):
    """casualties a year in the flat and gentle towns today, at the Hull and York level and at Go Dutch, with and without
    protected routes"""
    import math
    def exponent(key, minn):
        F = [t for t in towns if t['tier'] in ('flat', 'gentle', 'bench') and t[key] >= minn and t['cyclists'] >= 50]
        return lstsq([(1, math.log(t['cyclists']), math.log(t['travel'])) for t in F], [math.log(t[key] / years) for t in F])[1], len(F)
    b, nb = exponent('coll', 5); bk, nk = exponent('coll_ksi', 3)
    # protected against unprotected stretches, collisions per million bike-km (stretches with DfT cycle counts)
    grp = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for a in os.listdir(RAW):
        p = os.path.join(RAW, a, 'work', 'priorities.json')
        if not os.path.exists(p): continue
        for c in json.load(open(p)):
            if not c.get('aadf'): continue
            g = 'protected' if c['protected'] >= 0.5 else 'lane' if c['lane'] >= 0.5 else 'none'
            grp[g][0] += c['n']; grp[g][1] += c['aadf'] * c['km'] * 365 * 5 / 1e6; grp[g][2] += 1
    rate = {g: v[0] / v[1] for g, v in grp.items() if v[1]}
    protect = rate['protected'] / rate['none']
    G = [t for t in towns if t['tier'] in ('flat', 'gentle')]
    now = sum(t['cyclists'] for t in G)
    out = []
    for key, label, share in (('today', 'Today', lambda t: t['cycle21']), ('bench', 'Hull and York levels', lambda t: max(t['cycle21'], bench_share)),
                              ('dutch', 'Go Dutch', lambda t: max(t['cycle21'], t['dutch']))):
        grow = lambda t: max(1.0, t['travel'] * share(t) / 100 / t['cyclists']) if t['cyclists'] else 1.0
        cyc = sum(t['cyclists'] * grow(t) for t in G)
        coll = sum(t['coll'] / years * grow(t) ** b for t in G); ksi = sum(t['coll_ksi'] / years * grow(t) ** bk for t in G)
        out.append(dict(key=key, label=label, cyclists=round(cyc), coll=round(coll), ksi=round(ksi), coll_p=round(coll * protect), ksi_p=round(ksi * protect)))
    return dict(towns=len(G), travel=sum(t['travel'] for t in G), b=round(b, 2), b_towns=nb, bk=round(bk, 2), bk_towns=nk,
                protect=round(protect, 2), protected_stretches=grp['protected'][2], rates={g: round(v, 1) for g, v in rate.items()}, scenarios=out)


def main():
    os.makedirs(H, exist_ok=True)
    towns = json.load(open(os.path.join(DATA, 'towns.json')))['towns']
    tid = {t['id']: t for t in towns}

    # small areas: LSOA -> town, LSOA -> council, LSOA -> MSOA (an LSOA's name is its MSOA's name plus a letter)
    lsoa_town = {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv'))) if r['bua'] in tid}
    lsoa_lad, lsoa_msoa, health_dec = {}, {}, {}
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if not r[0].startswith('E01'): continue
        lsoa_lad[r[0]] = r[2]; lsoa_msoa[r[0]] = r[1][:-1]; health_dec[r[0]] = int(r[21])

    # Census 2021 general health, and MSOA names to codes
    z = fetch('https://www.nomisweb.co.uk/output/census/2021/census2021-ts037.zip', os.path.join(H, 'census2021-ts037.zip'))
    zf = zipfile.ZipFile(z)
    bad, people = collections.Counter(), collections.Counter()
    for r in csv.DictReader(io.TextIOWrapper(zf.open('census2021-ts037-lsoa.csv'), encoding='utf-8-sig')):
        bad[r['geography code']] = int(r['General health: Bad health']) + int(r['General health: Very bad health'])
        people[r['geography code']] = int(r['General health: Total: All usual residents'])
    eng_ts = next(r for r in csv.DictReader(io.TextIOWrapper(zf.open('census2021-ts037-ctry.csv'), encoding='utf-8-sig')) if r['geography'] == 'England')
    eng_bad = 100 * (int(eng_ts['General health: Bad health']) + int(eng_ts['General health: Very bad health'])) / int(eng_ts['General health: Total: All usual residents'])
    msoa_code = {r['geography']: r['geography code'] for r in csv.DictReader(io.TextIOWrapper(zf.open('census2021-ts037-msoa.csv'), encoding='utf-8-sig'))}

    ft = {name: fingertips(ind, at) for ind, at, name in FT}

    # PCT health outcomes by 2011 LSOA (most codes unchanged in 2021), and the same summed for each NHS ICB
    pct = {}
    lad_icb = {lad: icb for icb, lads in ICB.items() for lad in lads}
    keys = dict(commuters='all', cyclists='bicycle', dutch_cyclists='dutch_slc', now_value='base_slvaluecomb', now_deaths='base_sldeath',
                value='dutch_sivaluecomb', value_lives='dutch_sivalueyll', value_sick='dutch_sivaluesick', deaths='dutch_sideath',
                sickdays='dutch_sisickdays', hours='dutch_sicyclehours', ebike_value='ebike_sivaluecomb', ebike_deaths='ebike_sideath')
    icb = collections.defaultdict(collections.Counter)
    for f in os.listdir(os.path.join(RAW, 'pct')):
        if f.endswith('_z.csv'):
            for r in csv.DictReader(open(os.path.join(RAW, 'pct', f))):
                pct[r['geo_code']] = (-float(r['dutch_sideath'] or 0), float(r['dutch_sivaluecomb'] or 0))
                if r['lad_name'] in lad_icb:
                    c = icb[lad_icb[r['lad_name']]]; c['zones'] += 1
                    for k, col in keys.items(): c[k] += float(r[col] or 0)
    # deaths and sick days come out of the PCT as changes (negative = fewer); report them as avoided
    icbs = [dict(name=n, note=ICB_NOTE.get(n), councils=len(ICB[n]), commuters=round(c['commuters']), cyclists=round(c['cyclists']),
                 now_value=round(c['now_value']), now_deaths=round(-c['now_deaths'], 1), value=round(c['value']), value_lives=round(c['value_lives']),
                 value_sick=round(c['value_sick']), deaths=round(-c['deaths'], 1), sickdays=round(-c['sickdays']), hours=round(c['hours']),
                 ebike_value=round(c['ebike_value']), ebike_deaths=round(-c['ebike_deaths'], 1), dutch_cyclists=round(c['dutch_cyclists']))
            for n, c in icb.items()]
    # road danger: cyclist casualties where the collision happened, by board, against Census 2021 cycle commuters
    ny = ['Craven', 'Hambleton', 'Harrogate', 'Richmondshire', 'Ryedale', 'Scarborough', 'Selby']   # one council since 2023
    lad_name = {}
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if r[0].startswith('E01'): lad_name[r[2]] = r[3]
    name_icb = {('North Yorkshire' if l in ny else l): n for n, ls in ICB.items() for l in ls}
    code_icb = {c: name_icb[n] for c, n in lad_name.items() if n in name_icb}
    cl = os.path.join(H, 'cycle_collision_lad.csv')
    if not os.path.exists(cl):
        ids = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_cas.csv'))) if r['casualty_type'] == '1'}
        rd = csv.reader(io.TextIOWrapper(urllib.request.urlopen(urllib.request.Request(
            'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-last-5-years.csv',
            headers={'User-Agent': 'CycleStats'}), timeout=600), encoding='utf-8-sig'))
        head = next(rd); h = {k: i for i, k in enumerate(head)}
        with open(cl + '.part', 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['collision_index', 'local_authority_ons_district'])
            for row in rd:
                if row[h['collision_index']] in ids: w.writerow([row[h['collision_index']], row[h['local_authority_ons_district']]])
        os.replace(cl + '.part', cl)
    where = {r['collision_index']: r['local_authority_ons_district'] for r in csv.DictReader(open(cl))}
    cas, years = collections.defaultdict(collections.Counter), set()
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_cas.csv'))):
        i = code_icb.get(where.get(r['collision_index']))
        if r['casualty_type'] == '1' and i:
            cas[i][r['casualty_severity']] += 1; years.add(r['collision_year'])
    riders = collections.Counter()
    for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'ttw2021.csv'))):
        i = code_icb.get(lsoa_lad.get(r['lsoa']))
        if i and r['method'] == '9': riders[i] += int(r['people'])
    ny_ = len(years)
    for x in icbs:
        c = cas[x['name']]
        x.update(killed=round(c['1'] / ny_, 1), serious=round(c['2'] / ny_), slight=round(c['3'] / ny_), riders21=riders[x['name']],
                 ksi_rate=round(1000 * (c['1'] + c['2']) / ny_ / riders[x['name']], 1) if riders[x['name']] else None,
                 growth=round(x['dutch_cyclists'] / x['cyclists'], 1) if x['cyclists'] else None)
    best = min(x['ksi_rate'] for x in icbs if x['ksi_rate'])
    for x in icbs:
        x['ksi_at_best'] = round((x['killed'] + x['serious']) - best * x['riders21'] / 1000)
        x['cut_needed'] = round(100 * (1 - 1 / x['growth'])) if x['growth'] else None
    icbs.sort(key=lambda x: -x['value'])

    by_town = collections.defaultdict(list)
    for l, t in lsoa_town.items(): by_town[t].append(l)
    out = []
    for t in towns:
        ls = by_town.get(t['id'], [])
        if not ls: continue
        lads = collections.Counter(lsoa_lad[l] for l in ls if l in lsoa_lad)
        lad = lads.most_common(1)[0][0] if lads else None
        msoas = [msoa_code.get(lsoa_msoa.get(l)) for l in ls]
        co = [ft['child_obese'][0][m] for m in msoas if m in ft['child_obese'][0]]
        pop = sum(people[l] for l in ls)
        v = dict(
            inactive=ft['inactive'][0].get(lad), overweight=ft['overweight'][0].get(lad), diabetes=ft['diabetes'][0].get(lad),
            child_obese=sum(co) / len(co) if co else None,
            health_dep=100 * sum(health_dec.get(l, 10) <= 2 for l in ls) / len(ls),
            bad_health=100 * sum(bad[l] for l in ls) / pop if pop else None)
        eng = dict(inactive=ft['inactive'][1], overweight=ft['overweight'][1], diabetes=ft['diabetes'][1], child_obese=ft['child_obese'][1], health_dep=20.0)
        ratios = {k: min(200, 100 * v[k] / eng[k]) for k in eng if v[k] is not None}
        need = sum(ratios.values()) / len(ratios) if len(ratios) == len(eng) else None
        deaths = sum(pct[l][0] for l in ls if l in pct); value = sum(pct[l][1] for l in ls if l in pct)
        gap = max(0.0, t['dutch'] - t['cycle21'])
        out.append(dict(
            id=t['id'], name=t['name'], area=t['area'], area_name=t['area_name'], lad=t['lad'], tier=t['tier'], slope=t['slope'],
            lat=t['lat'], lon=t['lon'], residents=pop, travel=t['travel'], cycle=t['cycle21'], dutch=t['dutch'], gap=round(gap, 1),
            nocar=t['nocar'], deprived=t['deprived'],
            **{k: round(x, 1) if x is not None else None for k, x in v.items()},
            ratios={k: round(x) for k, x in ratios.items()}, need=round(need) if need else None,
            score=round(need / 100 * gap, 1) if need else None,
            deaths=round(deaths, 2), value=round(value), value_pp=round(value / pop, 1) if pop else None))
    eng = dict(inactive=ft['inactive'][1], overweight=ft['overweight'][1], diabetes=ft['diabetes'][1], child_obese=ft['child_obese'][1],
               health_dep=20.0, bad_health=round(eng_bad, 1))
    periods = {name: ft[name][2] for name in ft}
    tj = json.load(open(os.path.join(DATA, 'towns.json')))
    safety = safety_projection(tj['towns'], len(tj['coll_years']), tj['bench']['share'])
    print('safety', json.dumps(safety))
    json.dump(dict(towns=out, icbs=icbs, safety=safety, cas_years=sorted(years), england={k: round(x, 1) for k, x in eng.items()}, periods=periods), open(os.path.join(DATA, 'health.json'), 'w'),
              ensure_ascii=False, separators=(',', ':'))
    print('England', eng, periods)
    for x in icbs: print(f"{x['name']:42} killed {x['killed']}/yr serious {x['serious']} slight {x['slight']} riders {x['riders21']} KSI per 1000 riders {x['ksi_rate']} at best -{x['ksi_at_best']}  growth x{x['growth']} cut {x['cut_needed']}%  today's cycling avoids {x['now_deaths']} deaths")
    for x in icbs: print(f"{x['name']:42} now £{x['now_value']/1e6:5.1f}m  Go Dutch +£{x['value']/1e6:5.1f}m (lives {x['value_lives']/1e6:.1f}, sick {x['value_sick']/1e6:.1f})  deaths {x['deaths']}  sick days {x['sickdays']:,}  e-bike +£{x['ebike_value']/1e6:.1f}m")
    league = sorted([x for x in out if x['score'] is not None and x['tier'] in ('flat', 'gentle', 'bench')], key=lambda x: -x['score'])
    for x in league[:25]:
        print(f"{x['name'][:28]:28} {x['tier']:6} need={x['need']:4} cycle={x['cycle']:4} dutch={x['dutch']:4} gap={x['gap']:4} score={x['score']:5} "
              f"deaths={x['deaths']:5} value=£{x['value']:>9,} inactive={x['inactive']} y6={x['child_obese']} dep={x['health_dep']}")


if __name__ == '__main__':
    main()
