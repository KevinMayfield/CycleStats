"""Download the raw data the pipeline needs into ../raw (or the folder given as the first argument).

Sources:
  - OpenStreetMap via the Overpass API (cycle routes, cycle paths, named roads, rivers, place names)
  - DfT STATS19 road casualty statistics, last 5 years (collisions, vehicles, casualties)
  - DfT road traffic statistics: annual average daily flow (AADF) count points for Leeds
  - Leeds City Council automatic cycle counters (Data Mill North dataset e1dmk)
"""
import csv, io, json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'raw'))
UA = {'User-Agent': 'CycleStats/1.0 (https://github.com/KevinMayfield/CycleStats)'}
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
            'https://overpass.private.coffee/api/interpreter']
LEEDS = 'area["ref:gss"="E08000035"]->.a;'
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']


def get(url, data=None, timeout=600):
    req = urllib.request.Request(url, data=data, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def save(path, url, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get(url, data) as r, open(path, 'wb') as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def overpass(name, query):
    path = os.path.join(RAW, 'osm', name)
    body = urllib.parse.urlencode({'data': '[out:json][timeout:380];' + query}).encode()
    for attempt in range(3):
        for url in OVERPASS:
            try:
                save(path, url, body)
                if '"elements"' in open(path, encoding='utf-8', errors='ignore').read(2000):
                    print('  osm', name, os.path.getsize(path) // 1024, 'KB')
                    return
            except Exception as e:
                print('  overpass error', url, e)
            time.sleep(10)
    sys.exit(f'Overpass failed for {name}')


def stream_filter(url, path, column, values):
    """Stream a large CSV and keep only rows where column is one of values."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get(url) as r, open(path, 'w', newline='') as out:
        rd = csv.reader(io.TextIOWrapper(r, encoding='utf-8-sig'))
        head = next(rd); i = head.index(column); w = csv.writer(out); w.writerow(head)
        for row in rd:
            if row[i] in values:
                w.writerow(row)
    print('  dft', os.path.basename(path))


def main():
    print('OpenStreetMap')
    # route relations: Leeds (UK) and Leeds (Maine) share a name, the pipeline clips to the UK boundary
    overpass('leeds.json', 'area["name"="Leeds"]["admin_level"="8"]->.a;(relation["route"="bicycle"](area.a);'
                           'way["highway"="cycleway"](area.a););out geom;')
    overpass('leeds2.json', LEEDS + 'rel["ref:gss"="E08000035"];out geom;(way["highway"="cycleway"](area.a);'
                            'way["highway"~"^(path|bridleway|track|footway)$"]["bicycle"="designated"](area.a););out tags geom;')
    overpass('roads.json', LEEDS + 'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|'
                           'living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"]["name"](area.a);out tags geom;')
    overpass('ctx.json', LEEDS + '(node["place"~"^(town|suburb|city)$"](area.a);way["waterway"="river"]["name"~"Aire|Wharfe"](area.a);'
                         'way["waterway"="canal"](area.a););out tags geom;')

    print('DfT STATS19 (large downloads, filtered as they stream)')
    b = 'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics'
    stream_filter(b + '-collision-last-5-years.csv', os.path.join(RAW, 'dft', 'leeds_coll.csv'), 'local_authority_ons_district', {'E08000035'})
    stream_filter(b + '-vehicle-last-5-years.csv', os.path.join(RAW, 'dft', 'cycle_veh.csv'), 'vehicle_type', {'1'})
    stream_filter(b + '-casualty-last-5-years.csv', os.path.join(RAW, 'dft', 'cycle_cas.csv'), 'casualty_type', {'1'})

    print('DfT traffic counts (Leeds = local authority 63)')
    save(os.path.join(RAW, 'dft', 'aadf_leeds.csv'),
         'https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/local_authority_id/dft_aadf_local_authority_id_63.csv')

    print('Leeds City Council cycle counters')
    pkg = json.load(get('https://datamillnorth.org/api/action/package_show?id=e1dmk'))['result']
    monthly = {}
    for res in pkg['resources']:
        name = urllib.parse.unquote(res['url'].rsplit('/', 1)[-1])
        if 'Sites' in name and 'Leeds' in name:
            save(os.path.join(RAW, 'lcc', 'sites.csv'), res['url'])
        parts = name.replace('.csv', '').split()
        if len(parts) == 4 and parts[:2] == ['Cycle', 'Data'] and parts[2] in MONTHS:
            monthly[(int(parts[3]), MONTHS.index(parts[2]) + 1)] = res['url']
    latest = sorted(monthly)[-12:]
    for n, ym in enumerate(reversed(latest), 1):
        save(os.path.join(RAW, 'lcc', f'm{n}.csv'), monthly[ym])
    # older months for counters that have since stopped reporting (Kirkstall Forge towpath, Meanwood path, Wykebeck Woods)
    for ym in [(2023, 12)] + [(2024, m) for m in range(1, 12)]:
        if ym in monthly:
            save(os.path.join(RAW, 'lcc', 'old', f'{ym[0]}-{ym[1]:02}.csv'), monthly[ym])
    if (2022, 7) in monthly:
        save(os.path.join(RAW, 'lcc', 'y22.csv'), monthly[(2022, 7)])
    print('  counters: latest month', latest[-1])


if __name__ == '__main__':
    main()
