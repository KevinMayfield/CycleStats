"""Long Eaton case study: safe routes to work and school. Writes data/longeaton.json for longeaton.html.

Brings together, for Long Eaton (ONS built-up area E63002115):
  travel     Census 2021 method of travel (TS061) and distance to work (TS058) for its LSOAs
  work       Census 2021 home-to-workplace flows by MSOA (raw/od/ODWP01EW, ODWP14EW): where its people work, and the
             Nottingham Road corridor, people travelling each way between Long Eaton and Toton, Stapleford, Beeston
             and Chilwell, and Nottingham
  corridor   the Propensity to Cycle Tool commute route network along the A6005 from Long Eaton to Beeston
  crashes    police-recorded cycle collisions 2021-25 in the town (STATS19), sorted into crash types from what each
             vehicle was doing, with hotspots (three or more within 75 m); the national vehicle file is filtered
             once to raw/dft/cycle_coll_veh.csv
  roads      every injury collision in the town, 2021-25: involving a bicycle, hurting a pedestrian, or between motor
             vehicles only, by the named road it is nearest; the national casualty file is filtered once to
             raw/dft/area_cas.csv
  map        the proposed paths (OpenStreetMap roads in raw/<area>/osm/roads.json), schools and job sites
             (raw/east-midlands/longeaton_places.json, from Overpass)
Toton Sidings and Stanton Ironworks history: Wikipedia (Toton TMD), Grace's Guide and Ilkeston history sources.
Journey times, the deprived areas and the Propensity to Cycle Tool predictions come from the Long Eaton-Castle
Donington cycle link study (October 2026) and are set out below as they were published there.
"""
import collections, csv, io, json, math, os, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
DATA = os.path.join(HERE, '..', 'data')
LE = 'E63002115'
VEH = 'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-vehicle-last-5-years.csv'
CAS = 'https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-casualty-last-5-years.csv'

# door-to-door minutes to the Willow Farm and Trent Lane business parks, from each deprived area's population centre
TRIPS = [dict(area='A · Coniston Road', decile=1, car=15, bus=50, bike=37, path=30, ebike=25),
         dict(area='B · Bank Street', decile=2, car=14, bus=36, bike=33, path=26, ebike=22),
         dict(area='C · Beresford Road, Sawley', decile=2, car=11, bus=23, bike=23, path=19, ebike=16),
         dict(area='D · Hamilton Road', decile=2, car=15, bus=37, bike=33, path=26, ebike=22),
         dict(area='E · Ash Grove', decile=3, car=12, bus=35, bike=27, path=22, ebike=18),
         dict(area='F · Oakley\'s Road', decile=3, car=14, bus=36, bike=30, path=25, ebike=21)]
# Propensity to Cycle Tool, 2011 base: commuters in the six most deprived areas, and the two secondary schools
COMMUTE = dict(workers=3943, rows=[('2011 Census', 287, 2238), ('Government Target', 469, 2140), ('Go Dutch', 1118, 1811),
                                   ('Go Dutch with e-bikes', 1279, 1698)])
SCHOOLS = [dict(name='The Long Eaton School', pupils=1287, cycle2011=179, target=263, dutch=1013, driven=[53, 11], within5=94),
           dict(name='Wilsthorpe School', pupils=824, cycle2011=76, target=126, dutch=637, driven=[80, 15], within5=97)]
SCHOOL_COMPARE = [('All English secondaries', 3.8), ('Flat, compact English secondaries', 7.0), ('Derbyshire and Derby', 2.3),
                  ('The Long Eaton School', 13.9), ('Wilsthorpe School', 9.2), ('Cambridge', 48.7)]
# the proposed paths: (number, name, length km, what it is, OpenStreetMap test on tags and the way's middle point)
PATHS = [(1, 'Nottingham Road', 1.2, 'Kerb-separated tracks both sides from the east side into the Market Place',
          lambda t, la, lo: t.get('ref') == 'A6005' and t.get('name') == 'Nottingham Road' and -1.2715 < lo < -1.252),
         (2, 'Derby Road', 2.3, 'Protected tracks from the Breaston edge past Wilsthorpe School to the Market Place',
          lambda t, la, lo: t.get('ref') == 'A6005' and t.get('name') in ('Derby Road', 'Wilsthorpe Road') and -1.31 < lo < -1.2715 and la > 52.895),
         (3, 'Wilsthorpe Road', 1.8, 'Protected tracks north–south through the west of town to Tamworth Road at the station',
          lambda t, la, lo: t.get('ref') == 'B6002' and t.get('name') == 'Wilsthorpe Road'),
         (4, 'Tamworth Road', 3.1, 'A protected track from the Market Place to Sawley: the spine every work trip uses',
          lambda t, la, lo: t.get('ref') == 'B6540' and la >= 52.8745),
         (5, 'Harrington Bridge', 0.4, 'A separate path over the Trent and Sawley Cut, away from the 40 mph carriageway',
          lambda t, la, lo: t.get('ref') == 'B6540' and 52.866 <= la < 52.8745),
         (6, 'B6540 to Castle Donington', 2.1, 'A parallel off-road path, lit for shift times',
          lambda t, la, lo: t.get('ref') == 'B6540' and la < 52.866),
         (7, 'A50 junction and Station Road', 1.7, 'Into the business parks, with Dutch-style roundabouts or signal crossings',
          lambda t, la, lo: t.get('name') in ('Station Road', 'Trent Lane') and 52.845 < la < 52.862 and -1.345 < lo < -1.32)]
EXTEND = [('Nottingham Road corridor to Beeston and Nottingham',
           lambda t, la, lo: t.get('ref') == 'A6005' and -1.252 <= lo < -1.20 and la > 52.898),
          ('Toton Lane to Stapleford', lambda t, la, lo: t.get('ref') == 'B6003' and t.get('name') in ('Toton Lane', 'Stapleford Lane') and la < 52.935)]
# where the jobs went: the works that were close to home, and today's job sites (for the schematic map)
HISTORY = dict(
    old=[dict(name='Toton Sidings', lat=52.906, lon=-1.259, km=1.5,
              what="Europe's largest marshalling yard at the height of the coal traffic, sorting Nottinghamshire coal. In decline by the 1970s: the north yard closed in 1978 and the up side in 1984, and it was cut back to its present shape in the late 1980s."),
         dict(name='Stanton Ironworks', lat=52.944, lon=-1.314, km=5,
              what='Ironworks from 1846 by the Nutbrook Canal, about 7,000 workers at its height under British Steel, later Stanton and Staveley and Saint-Gobain. The last pipe was cast on 24 May 2007. The 470-acre site is now proposed for housing.')],
    new=[dict(name='Castle Donington business parks', lat=52.851, lon=-1.338, key='North of Castle Donington (airport, business parks, logistics)'),
         dict(name='East Midlands Gateway', lat=52.836, lon=-1.300, key=None),
         dict(name='East Midlands Airport', lat=52.826, lon=-1.352, key=None),
         dict(name='Derby', lat=52.922, lon=-1.475, key='Derby'),
         dict(name='Nottingham', lat=52.954, lon=-1.158, key='Nottingham'),
         dict(name='Beeston, Toton, Stapleford', lat=52.925, lon=-1.230, key='Broxtowe (Beeston, Toton, Stapleford)')],
    roads=[dict(name='M1', pts=[[52.80, -1.283], [52.836, -1.296], [52.862, -1.297], [52.893, -1.302], [52.917, -1.302], [52.962, -1.312]]),
           dict(name='A50', pts=[[52.850, -1.318], [52.866, -1.385], [52.887, -1.462]]),
           dict(name='A52', pts=[[52.920, -1.470], [52.914, -1.370], [52.917, -1.302], [52.930, -1.240], [52.952, -1.168]])],
    junctions=[dict(name='J24', lat=52.840, lon=-1.297), dict(name='J24A', lat=52.857, lon=-1.297), dict(name='J25', lat=52.917, lon=-1.302)],
    centre=dict(lat=52.8985, lon=-1.272))
SECONDARY = ('The Long Eaton School', 'Wilsthorpe School', 'Trent College', 'Chilwell School', 'George Spencer Academy',
             'Alderman White School', 'Friesland School', 'Castle Donington College', 'Bramcote College')
JOBS = ('Willow Farm Business Park', 'Trent Lane Industrial Estate', 'SEGRO East Midlands Gateway', 'East Midlands Airport',
        'East Midlands Distribution Centre', 'Beeston Business Park', 'Boots PLC')


def lsoa_town():
    return {r['lsoa']: r['bua'] for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'lsoa_bua.csv')))}


def travel(lb):
    mine = {l for l, b in lb.items() if b == LE}
    z = zipfile.ZipFile(os.path.join(RAW, 'heritage', 'census2021-ts061.zip'))
    rd = csv.reader(io.TextIOWrapper(z.open('census2021-ts061-lsoa.csv'), encoding='utf-8-sig')); h = next(rd); S = collections.Counter()
    for r in rd:
        if r[2] in mine:
            for i in range(3, len(h)): S[h[i].replace('Method of travel to workplace: ', '')] += int(r[i])
    total = next(v for k, v in S.items() if k.startswith('Total')); home = S['Work mainly at or from home']; com = total - home
    groups = [('Driving a car or van', ('Driving a car or van',)), ('On foot', ('On foot',)), ('Bus', ('Bus, minibus or coach',)),
              ('Passenger in a car', ('Passenger in a car or van',)), ('Bicycle', ('Bicycle',)),
              ('Train, tram, motorcycle, taxi, other', ('Train', 'Underground, metro, light rail, tram', 'Motorcycle, scooter or moped', 'Taxi', 'Other method of travel to work'))]
    D = collections.Counter()
    for r in csv.DictReader(open(os.path.join(RAW, 'imd', 'ttwdist2021.csv'))):
        if r['lsoa'] in mine: D[r['band']] += int(r['people'])
    c = D['0'] - D['9'] - D['10']
    return dict(working=total, home=round(100 * home / total, 1), modes=[dict(mode=n, share=round(100 * sum(S[k] for k in ks) / com, 1)) for n, ks in groups],
                distance=[dict(band=b, share=round(100 * v / c)) for b, v in (('Under 2 km', D['1']), ('2–5 km', D['2']), ('5–10 km', D['3']),
                                                                            ('10–20 km', D['4']), ('20 km or more', sum(D[k] for k in '5678')))])


def msoa_towns(lb):
    ls_msoa = {}
    for r in csv.reader(open(os.path.join(RAW, 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
        if r[0].startswith('E01'): ls_msoa[r[0]] = r[1][:-1]
    code = {r['geography']: r['geography code'] for r in csv.DictReader(io.TextIOWrapper(
        zipfile.ZipFile(os.path.join(RAW, 'industry', 'ts037.zip')).open('census2021-ts037-msoa.csv'), encoding='utf-8-sig'))}
    votes = collections.defaultdict(collections.Counter)
    for l, b in lb.items():
        m = code.get(ls_msoa.get(l))
        if m: votes[m][b] += 1
    return {m: c.most_common(1)[0][0] for m, c in votes.items()}


def work(mt):
    # Toton and Chilwell West: the two Broxtowe MSOAs nearest Toton (E02005862, E02005864)
    group = {LE: 'Long Eaton', 'E63002057': 'Beeston and Chilwell', 'E63002042': 'Stapleford', 'E63001992': 'Nottingham'}
    toton = {'E02005862', 'E02005864'}
    g = lambda m: 'Toton and Chilwell West' if m in toton else group.get(mt.get(m))
    dest, out, inn = collections.Counter(), collections.Counter(), collections.Counter()
    for r in csv.DictReader(open(os.path.join(RAW, 'od', 'ODWP01EW_MSOA.csv'))):
        if r['Place of work indicator (4 categories) code'] != '3': continue
        h, w, n = r['Middle layer Super Output Areas code'], r['MSOA of workplace code'], int(r['Count'])
        if g(h) == 'Long Eaton':
            lab = r['MSOA of workplace label']
            dest['Within Long Eaton' if g(w) == 'Long Eaton' else 'North of Castle Donington (airport, business parks, logistics)'
                 if lab in ('North West Leicestershire 001', 'North West Leicestershire 002') else 'Nottingham' if lab.startswith('Nottingham ')
                 else 'Derby' if lab.startswith('Derby ') else 'Broxtowe (Beeston, Toton, Stapleford)' if lab.startswith('Broxtowe ')
                 else 'Erewash outside Long Eaton' if lab.startswith('Erewash ') else 'Elsewhere'] += n
        if g(h) == 'Long Eaton' and g(w) not in (None, 'Long Eaton'): out[g(w)] += n
        if g(w) == 'Long Eaton' and g(h) not in (None, 'Long Eaton'): inn[g(h)] += n
    nocar = collections.Counter()
    for r in csv.DictReader(open(os.path.join(RAW, 'od', 'ODWP14EW_MSOA.csv'))):
        if g(r['Middle layer Super Output Areas code']) == 'Long Eaton' and r['Place of work indicator (4 categories) code'] == '3':
            k = r['Car or van availability (5 categories) label']; nocar[k] += int(r['Count'])
            if r['MSOA of workplace label'] == 'North West Leicestershire 001': nocar[k + '|cd'] += int(r['Count'])
    total = sum(dest.values())
    order = ['Within Long Eaton', 'Nottingham', 'Broxtowe (Beeston, Toton, Stapleford)', 'Derby', 'Erewash outside Long Eaton',
             'North of Castle Donington (airport, business parks, logistics)', 'Elsewhere']
    places = ['Toton and Chilwell West', 'Stapleford', 'Beeston and Chilwell', 'Nottingham']
    return dict(total=total, dest=[dict(place=k, workers=dest[k], share=round(100 * dest[k] / total, 1)) for k in order],
                corridor=[dict(place=p, out=out[p], inn=inn[p]) for p in places],
                cd_nocar=round(100 * nocar['No cars or vans in household|cd'] / nocar['No cars or vans in household'], 1),
                cd_twocar=round(100 * nocar['2 cars or vans in household|cd'] / nocar['2 cars or vans in household'], 1))


def corridor():
    """PCT commuters per day along the A6005 from Long Eaton to Beeston, every 400 m or so"""
    roads = [e for e in json.load(open(os.path.join(RAW, 'east-midlands', 'osm', 'roads.json')))['elements']
             if e.get('type') == 'way' and e.get('geometry') and e.get('tags', {}).get('ref') == 'A6005']
    lines = []
    for f in ('derbyshire', 'nottinghamshire'):
        for ft in json.load(open(os.path.join(RAW, 'pct', f'{f}_commute.geojson')))['features']:
            g = ft['geometry']; lines.append((ft['properties'], g['coordinates'] if g['type'] == 'LineString' else [c for l in g['coordinates'] for c in l]))
    pts = sorted((g['lon'], g['lat'], e['tags'].get('name')) for e in roads for g in e['geometry'][::3] if -1.272 < g['lon'] < -1.20 and 52.895 < g['lat'] < 52.935)
    out, last = [], None
    for lo, la, n in pts:
        if last is not None and lo - last < .006: continue
        last = lo; k = 111200 * math.cos(math.radians(la)); best = None
        for p, cs in lines:
            if abs(cs[0][1] - la) > .02 or abs(cs[0][0] - lo) > .03: continue
            P = [((x - lo) * k, (y - la) * 111200) for x, y in cs]
            for (ax, ay), (bx, by) in zip(P, P[1:]):
                dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy; u = 0 if L == 0 else max(0, min(1, (-ax * dx - ay * dy) / L))
                if math.hypot(ax + u * dx, ay + u * dy) <= 40 and (best is None or p['dutch_slc'] > best['dutch_slc']): best = p
        if best: out.append(dict(lat=round(la, 4), lon=round(lo, 4), road=n, now=best['bicycle'], target=best['govtarget_slc'], dutch=best['dutch_slc'], ebike=best['ebike_slc']))
    return out


def vehicles(keep):
    path = os.path.join(RAW, 'dft', 'cycle_coll_veh.csv')
    if not os.path.exists(path):
        r = urllib.request.urlopen(urllib.request.Request(VEH, headers={'User-Agent': 'CycleStats'}), timeout=600)
        rd = csv.reader(io.TextIOWrapper(r, encoding='utf-8-sig')); h = next(rd); i = h.index('collision_index')
        with open(path, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(h)
            for row in rd:
                if row[i] in keep: w.writerow(row)
    V = collections.defaultdict(list)
    for r in csv.DictReader(open(path)): V[r['collision_index']].append(r)
    return V


def jtype(c, vs):
    if c['junction_detail_historic'] in ('1', '2') or any(v['junction_location'] in ('3', '4') for v in vs): return 'Roundabout'
    j = c['junction_detail'] if c['junction_detail'] not in ('-1', '99', '') else {'0': '0', '3': '13', '6': '16', '7': '17', '8': '18', '9': '19', '5': '19'}.get(c['junction_detail_historic'], '-1')
    return {'0': 'Not at a junction', '13': 'T-junction', '16': 'Crossroads', '17': 'Big junction', '18': 'Drive or entrance', '19': 'Other junction'}.get(j, 'Unknown')


def crash_type(c, vs):
    """what happened, from each vehicle's manoeuvre, junction location and point of impact (STATS19 codes)"""
    bikes = [v for v in vs if v['vehicle_type'] == '1']; others = [v for v in vs if v['vehicle_type'] != '1']
    if not others: return 'Cyclist alone, or with a pedestrian or another cyclist'
    o = others[0]; m, jl = o['vehicle_manoeuvre'], o['junction_location']; b = bikes[0] if bikes else {}
    if jtype(c, vs) == 'Roundabout': return 'At a roundabout'
    if c['junction_detail'] == '18' or c['junction_detail_historic'] == '8': return 'Driver in or out of a drive'
    if m in ('2', '20', '1'): return 'Parked, parking or reversing vehicle, including doors'
    if m in ('9', '10'): return 'Driver turning right across the cyclist'
    if m in ('7', '8'): return 'Driver turning left across the cyclist'
    if jl == '6' or (m in ('3', '5') and jl in ('1', '2', '6', '8')): return 'Driver pulling out of a side road'
    if m in ('11', '12', '13', '14', '15'): return 'Driver overtaking or changing lane'
    if b.get('vehicle_manoeuvre') in ('9', '10', '7', '8'): return 'Cyclist turning'
    if o['first_point_of_impact'] == '1' and b.get('first_point_of_impact') == '2': return 'Cyclist hit from behind'
    if jl in ('1', '2', '5', '8'): return 'Both going ahead, paths crossing at a junction'
    return 'Other, away from a junction'


def crashes(lb):
    C = {r['collision_index']: r for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv')))}
    cyc = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
    V = vehicles(cyc & set(C))
    mine = [ci for ci in cyc & set(C) if lb.get(C[ci]['lsoa_of_accident_location']) == LE and ci in V]
    ages = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_cas.csv'))):
        if r['collision_index'] in mine and r['age_of_casualty'].lstrip('-').isdigit(): ages[r['collision_index']].append(int(r['age_of_casualty']))
    pts = []
    for ci in mine:
        c = C[ci]
        pts.append(dict(id=ci, lat=float(c['latitude']), lon=float(c['longitude']), e=float(c['location_easting_osgr']), n=float(c['location_northing_osgr']),
                        year=c['collision_year'], serious=c['collision_severity'] in ('1', '2'), type=crash_type(c, V[ci]), junction=jtype(c, V[ci]),
                        child=any(0 <= a < 16 for a in ages[ci]), school_run=c['time'][:2] in ('08', '15', '16')))
    # hotspots: three or more within 75 m, taken greedily from the densest point
    used, spots = set(), []
    near = lambda p: [q for q in pts if math.hypot(q['e'] - p['e'], q['n'] - p['n']) <= 75]
    for p in sorted(pts, key=lambda p: -len(near(p))):
        if p['id'] in used: continue
        m = [q for q in near(p) if q['id'] not in used]
        if len(m) < 3: continue
        used |= {q['id'] for q in m}
        spots.append(dict(lat=sum(q['lat'] for q in m) / len(m), lon=sum(q['lon'] for q in m) / len(m), n=len(m), serious=sum(q['serious'] for q in m),
                          types=collections.Counter(q['type'] for q in m).most_common(3)))
    for p in pts: del p['e'], p['n'], p['id']
    n = len(pts); T = collections.Counter(p['type'] for p in pts); J = collections.Counter(p['junction'] for p in pts)
    kids = sum(0 <= a < 16 for v in ages.values() for a in v)
    return dict(points=pts, hotspots=spots, total=n, serious=sum(p['serious'] for p in pts), casualties=sum(len(v) for v in ages.values()), children=kids,
                children_school_run=sum(1 for p in pts if p['child'] and p['school_run']),
                types=[dict(type=k, n=v, share=round(100 * v / n)) for k, v in T.most_common()],
                junctions=[dict(type=k, share=round(100 * v / n)) for k, v in J.most_common()])


def filtered(url, path, keep):
    """rows of a national STATS19 file for the collisions in keep, streamed once and cached"""
    if not os.path.exists(path):
        r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CycleStats'}), timeout=600)
        rd = csv.reader(io.TextIOWrapper(r, encoding='utf-8-sig')); h = next(rd); i = h.index('collision_index')
        with open(path, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(h)
            for row in rd:
                if row[i] in keep: w.writerow(row)
    return csv.DictReader(open(path))


def road_namer():
    ways = [(e['bounds'], e['tags']['name'], e['tags'].get('ref', ''), [(g['lat'], g['lon']) for g in e['geometry']])
            for e in json.load(open(os.path.join(RAW, 'east-midlands', 'osm', 'roads.json')))['elements']
            if e.get('type') == 'way' and e.get('geometry') and e.get('tags', {}).get('name')]
    def name(la, lo):
        k = 111200 * math.cos(math.radians(la)); best = (41, None)
        for bd, n, r, g in ways:
            if bd['minlat'] - .0005 > la or bd['maxlat'] + .0005 < la or bd['minlon'] - .0008 > lo or bd['maxlon'] + .0008 < lo: continue
            P = [((b - lo) * k, (a - la) * 111200) for a, b in g]
            for (ax, ay), (bx, by) in zip(P, P[1:]):
                dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy; u = 0 if L == 0 else max(0, min(1, (-ax * dx - ay * dy) / L))
                d = math.hypot(ax + u * dx, ay + u * dy)
                if d < best[0]: best = (d, f'{n} ({r})' if r else n)
        return best[1] or 'Unnamed or off-road'
    return name


def roads(lb):
    """every injury collision in Long Eaton: bicycle, pedestrian hurt, or motor vehicles only, by nearest named road"""
    C = {r['collision_index']: r for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv')))}
    cyc = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
    ped = {r['collision_index'] for r in filtered(CAS, os.path.join(RAW, 'dft', 'area_cas.csv'), set(C)) if r['casualty_class'] == '3'}
    name = road_namer(); pts = []; by = collections.defaultdict(collections.Counter)
    for ci, c in C.items():
        if lb.get(c['lsoa_of_accident_location']) != LE: continue
        try: la, lo = float(c['latitude']), float(c['longitude'])
        except ValueError: continue
        kind = 'cycle' if ci in cyc else 'pedestrian' if ci in ped else 'motor'; serious = c['collision_severity'] in ('1', '2'); rd = name(la, lo)
        pts.append(dict(lat=round(la, 5), lon=round(lo, 5), kind=kind, serious=serious, road=rd, year=c['collision_year']))
        b = by[rd]; b[kind] += 1; b['all'] += 1; b['serious'] += serious
    tot = collections.Counter(p['kind'] for p in pts)
    rows = [dict(road=r, cycle=b['cycle'], pedestrian=b['pedestrian'], motor=b['motor'], all=b['all'], serious=b['serious'])
            for r, b in sorted(by.items(), key=lambda x: -x[1]['all']) if r != 'Unnamed or off-road'][:14]
    return dict(points=pts, totals=dict(tot), serious=sum(p['serious'] for p in pts), rows=rows)


def geometry():
    ways = []
    for a in ('east-midlands', 'leicestershire'):
        for e in json.load(open(os.path.join(RAW, a, 'osm', 'roads.json')))['elements']:
            if e.get('type') == 'way' and e.get('geometry'): ways.append(e)
    seen = set(); line = lambda e: [[round(g['lat'], 5), round(g['lon'], 5)] for g in e['geometry']]
    def pick(test):
        out = []
        for e in ways:
            g = e['geometry'][len(e['geometry']) // 2]
            if e['id'] not in seen and test(e.get('tags', {}), g['lat'], g['lon']): seen.add(e['id']); out.append(line(e))
        return out
    paths = [dict(n=n, name=nm, km=km, what=w, lines=pick(t)) for n, nm, km, w, t in PATHS]
    extend = [dict(name=nm, lines=pick(t)) for nm, t in EXTEND]
    P = json.load(open(os.path.join(RAW, 'east-midlands', 'longeaton_places.json')))['elements']
    place = lambda e: e.get('center') or e
    schools, jobs = [], []
    for e in P:
        t = e.get('tags', {}); nm = t.get('name', ''); c = place(e)
        if nm in SECONDARY and nm not in [s['name'] for s in schools]: schools.append(dict(name=nm, lat=c['lat'], lon=c['lon'], kind='secondary'))
        elif t.get('amenity') == 'school' and 'primary' in t.get('school', '') + t.get('isced:level', '') and 52.875 < c['lat'] < 52.912 and -1.31 < c['lon'] < -1.25:
            schools.append(dict(name=nm, lat=c['lat'], lon=c['lon'], kind='primary'))
        if nm in JOBS and nm not in [j['name'] for j in jobs]: jobs.append(dict(name=nm, lat=c['lat'], lon=c['lon']))
    return paths, extend, schools, jobs


def main():
    lb = lsoa_town()
    T = next(t for t in json.load(open(os.path.join(DATA, 'towns.json')))['towns'] if t['id'] == LE)
    PR = json.load(open(os.path.join(DATA, 'predict.json'))); P = next(t for t in PR['towns'] if t['id'] == LE)
    PE = next(t for t in json.load(open(os.path.join(DATA, 'people.json')))['towns'] if t['id'] == LE)
    paths, extend, schools, jobs = geometry()
    out = dict(town=dict(cycle11=T['cycle11'], cycle21=T['cycle21'], dutch=T['dutch'], slope=T['slope'], travel=T['travel'], pred=P['pred'], local=P['local'],
                         women=PE.get('women'), f=PE.get('f'), f_pred=P.get('f_pred'), skew=PE.get('skew'), risk=PE.get('rider_index'), pit_km=6.8),
               travel=travel(lb), work=work(msoa_towns(lb)), corridor=corridor(), crashes=crashes(lb), roads=roads(lb), trips=TRIPS, commute=COMMUTE,
               schools=SCHOOLS, school_compare=SCHOOL_COMPARE, history=HISTORY, paths=paths, extend=extend, places=dict(schools=schools, jobs=jobs))
    json.dump(out, open(os.path.join(DATA, 'longeaton.json'), 'w'), separators=(',', ':'))
    print(json.dumps({k: v for k, v in out.items() if k not in ('paths', 'extend', 'places', 'crashes', 'corridor')}, indent=1)[:2500])
    print('roads', out['roads']['totals'], out['roads']['serious']); [print('  ', r) for r in out['roads']['rows']]
    print('crashes', out['crashes']['total'], out['crashes']['serious'], 'hotspots', len(out['crashes']['hotspots']), 'children', out['crashes']['children'])
    print('paths', [(p['n'], len(p['lines'])) for p in paths], 'extend', [(e['name'], len(e['lines'])) for e in extend])
    print('schools', len(schools), 'jobs', [j['name'] for j in jobs], 'corridor points', len(out['corridor']))


if __name__ == '__main__':
    main()
