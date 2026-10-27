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

Downloads (cached in raw/health/): Fingertips CSVs and Census 2021 TS037, fetched with /usr/bin/python3 on Kevin's Mac.
"""
import collections, csv, io, json, os, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
H = os.path.join(RAW, 'health')
DATA = os.path.join(HERE, '..', 'data')
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

    # PCT health outcomes by 2011 LSOA (most codes unchanged in 2021)
    pct = {}
    for f in os.listdir(os.path.join(RAW, 'pct')):
        if f.endswith('_z.csv'):
            for r in csv.DictReader(open(os.path.join(RAW, 'pct', f))):
                pct[r['geo_code']] = (-float(r['dutch_sideath'] or 0), float(r['dutch_sivaluecomb'] or 0))

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
    json.dump(dict(towns=out, england={k: round(x, 1) for k, x in eng.items()}, periods=periods), open(os.path.join(DATA, 'health.json'), 'w'),
              ensure_ascii=False, separators=(',', ':'))
    print('England', eng, periods)
    league = sorted([x for x in out if x['score'] is not None and x['tier'] in ('flat', 'gentle', 'bench')], key=lambda x: -x['score'])
    for x in league[:25]:
        print(f"{x['name'][:28]:28} {x['tier']:6} need={x['need']:4} cycle={x['cycle']:4} dutch={x['dutch']:4} gap={x['gap']:4} score={x['score']:5} "
              f"deaths={x['deaths']:5} value=£{x['value']:>9,} inactive={x['inactive']} y6={x['child_obese']} dep={x['health_dep']}")


if __name__ == '__main__':
    main()
