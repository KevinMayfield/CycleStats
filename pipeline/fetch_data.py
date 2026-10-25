"""Download the raw data the pipeline needs into ../raw.

    python3 fetch_data.py [area ...] [--keep]

Areas are the ids in areas.json (default: all). --keep reuses files already downloaded instead of
fetching them again, which is handy after a failed or rate-limited run.

Sources:
  - OpenStreetMap via the Overpass API (cycle routes, cycle paths, named roads, rivers, place names)
  - DfT STATS19 road casualty statistics, last 5 years (collisions, vehicles, casualties)
  - DfT road traffic statistics: annual average daily flow (AADF) count points by highway authority
  - Leeds City Council automatic cycle counters (Data Mill North dataset e1dmk)
"""
import csv, io, json, os, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.abspath(os.path.join(HERE, '..', 'raw'))
AREAS = json.load(open(os.path.join(HERE, 'areas.json')))
UA = {'User-Agent': 'CycleStats/1.0 (https://github.com/KevinMayfield/CycleStats)'}
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
            'https://overpass.private.coffee/api/interpreter']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
KEEP = '--keep' in sys.argv


def get(url, data=None, timeout=600, tries=6):
    """Open a URL, backing off on rate limits (429) and server errors."""
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = int(e.headers.get('Retry-After') or 0) or 15 * 2 ** attempt
            print(f'  HTTP {e.code}, retrying in {wait}s')
            time.sleep(wait)


def have(path):
    return KEEP and os.path.exists(path) and os.path.getsize(path) > 0


def save(path, url, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get(url, data) as r, open(path + '.part', 'wb') as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(path + '.part', path)


def overpass(path, query):
    if have(path): return
    body = urllib.parse.urlencode({'data': '[out:json][timeout:380];' + query}).encode()
    for attempt in range(3):
        for url in OVERPASS:
            try:
                save(path, url, body)
                if '"elements"' in open(path, encoding='utf-8', errors='ignore').read(2000):
                    print('  osm', os.path.relpath(path, RAW), os.path.getsize(path) // 1024, 'KB')
                    return
            except Exception as e:
                print('  overpass error', url, e)
            time.sleep(10)
    sys.exit(f'Overpass failed for {path}')


def bbox_of(paths_json, cfg):
    """(s,w,n,e) of the area: its configured bbox, or the boundary relation's bounds"""
    if 'bbox' in cfg: return cfg['bbox']
    rels = [e for e in json.load(open(paths_json))['elements'] if e['type'] == 'relation']
    if not rels:
        os.remove(paths_json)
        sys.exit(f'No OpenStreetMap boundary has ref:gss={cfg["gss"]}; check the code in areas.json')
    rel = rels[0]
    b = rel['bounds']
    return [b['minlat'], b['minlon'], b['maxlat'], b['maxlon']]


def fetch_osm(aid, cfg):
    d = os.path.join(RAW, aid, 'osm')
    if 'bbox' in cfg:
        sel = '(' + ','.join(map(str, cfg['bbox'])) + ')'; boundary = ''
    else:
        sel = '(area.a)'; boundary = f'rel["ref:gss"="{cfg["gss"]}"];out geom;'
    pre = '' if 'bbox' in cfg else f'area["ref:gss"="{cfg["gss"]}"]->.a;'
    overpass(os.path.join(d, 'paths.json'), pre + boundary + f'(way["highway"="cycleway"]{sel};'
             f'way["highway"~"^(path|bridleway|track|footway)$"]["bicycle"="designated"]{sel};);out tags geom;')
    s, w, n, e = bbox_of(os.path.join(d, 'paths.json'), cfg)
    m = 0.02  # route geometry is clipped to a slightly padded bbox; the pipeline clips to the boundary
    overpass(os.path.join(d, 'routes.json'), pre + f'relation["route"="bicycle"]{sel};out geom({s - m},{w - m},{n + m},{e + m});')
    overpass(os.path.join(d, 'roads.json'), pre + f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|'
             f'living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"]["name"]{sel};out tags geom;')
    overpass(os.path.join(d, 'ctx.json'), pre + f'(node["place"~"^({cfg["places"]})$"]{sel};way["waterway"="river"]["name"~"{cfg["rivers"]}"]{sel};'
             f'way["waterway"="canal"]{sel};);out tags geom;')


def fetch_stats19(areas):
    """Stream the national files once and keep what any area needs."""
    d = os.path.join(RAW, 'dft')
    lads = {l for c in areas.values() for l in c['stats19_lad']}
    boxes = [c['bbox'] for c in areas.values() if 'bbox' in c]

    def keep_collision(row, h):
        if row[h['local_authority_ons_district']] in lads: return True
        try: la, lo = float(row[h['latitude']]), float(row[h['longitude']])
        except ValueError: return False
        return any(s <= la <= n and w <= lo <= e for s, w, n, e in boxes)

    b = 'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics'
    for name, out, test in [('collision', 'collisions.csv', keep_collision),
                            ('vehicle', 'cycle_veh.csv', lambda row, h: row[h['vehicle_type']] == '1'),
                            ('casualty', 'cycle_cas.csv', lambda row, h: row[h['casualty_type']] == '1')]:
        path = os.path.join(d, out)
        if have(path): continue
        os.makedirs(d, exist_ok=True)
        with get(f'{b}-{name}-last-5-years.csv') as r, open(path + '.part', 'w', newline='') as f:
            rd = csv.reader(io.TextIOWrapper(r, encoding='utf-8-sig'))
            head = next(rd); h = {k: i for i, k in enumerate(head)}; wr = csv.writer(f); wr.writerow(head)
            for row in rd:
                if test(row, h): wr.writerow(row)
        os.replace(path + '.part', path)
        print('  dft', out)


def fetch_aadf(aid, cfg):
    rows = []
    for la in cfg['dft_la']:
        path = os.path.join(RAW, 'dft', f'aadf_{la}.csv')
        if not have(path):
            save(path, f'https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/local_authority_id/dft_aadf_local_authority_id_{la}.csv')
        with open(path, encoding='utf-8-sig') as f:
            r = list(csv.reader(f)); head = r[0]; rows += r[1:]
    with open(os.path.join(RAW, aid, 'aadf.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(head); w.writerows(rows)
    print('  aadf', aid, len(rows), 'rows')


def fetch_leeds_counters():
    pkg = json.load(get('https://datamillnorth.org/api/action/package_show?id=e1dmk'))['result']
    monthly = {}
    for res in pkg['resources']:
        name = urllib.parse.unquote(res['url'].rsplit('/', 1)[-1])
        if 'Sites' in name and 'Leeds' in name:
            save(os.path.join(RAW, 'lcc', 'sites.csv'), res['url'])
        parts = name.replace('.csv', '').split()
        if len(parts) == 4 and parts[:2] == ['Cycle', 'Data'] and parts[2] in MONTHS:
            monthly[(int(parts[3]), MONTHS.index(parts[2]) + 1)] = res['url']
    # latest 12 months, plus older months for counters that have since stopped reporting
    # (Kirkstall Forge towpath and Meanwood path: Dec 2023 - Nov 2024; Wykebeck Woods: July 2022)
    latest = sorted(monthly)[-12:]
    wanted = set(latest) | {(2023, 12), (2022, 7)} | {(2024, m) for m in range(1, 12)}
    for ym in sorted(wanted & set(monthly)):
        path = os.path.join(RAW, 'lcc', 'months', f'{ym[0]}-{ym[1]:02}.csv')
        # past months don't change, so only fetch what's missing (and always the newest month)
        if os.path.exists(path) and ym != latest[-1]:
            continue
        save(path, monthly[ym])
        time.sleep(2)  # Data Mill North rate-limits rapid downloads
    print('  counters: latest month', latest[-1])


def main():
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or list(AREAS)
    areas = {a: AREAS[a] for a in ids}
    for aid, cfg in areas.items():
        print('OpenStreetMap:', cfg['name'])
        fetch_osm(aid, cfg)
    print('DfT STATS19 (large downloads, filtered as they stream)')
    # the collisions file holds every area, so a partial run must not overwrite it with fewer areas
    fetch_stats19(AREAS)
    print('DfT traffic counts')
    for aid, cfg in areas.items():
        fetch_aadf(aid, cfg)
    if any(c['counters'] == 'leeds' for c in areas.values()):
        print('Leeds City Council cycle counters')
        fetch_leeds_counters()


if __name__ == '__main__':
    main()
