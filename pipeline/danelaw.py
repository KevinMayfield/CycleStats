"""The Danelaw Way: a long-distance route from Derby to York along the rivers of the Danelaw, with the Lindsey Ridings
(Torksey to Howden by Lincoln, Grimsby and the Humber), variants from Leicester down the Soar and from Leeds down the Aire, and a coast route from Leicester by
Stamford, the Wash, Skegness and the Lincolnshire coast to the Humber. Writes data/danelaw.json for danelaw.html.

Each stage is routed with BRouter's touring profile ('trekking') through hand-picked villages on one bank of the
river, so it follows the river without crossing back and forth or wandering off along signed routes between
villages. Responses are cached in raw/danelaw/ (delete them to route again).
Every 25 m of the route is then checked against the OpenStreetMap data already downloaded for the areas it crosses:
  path    within 12 m of a cycleway or a path designated for bikes
  quiet   a residential, unclassified or service road
  track   none of these within 12 m: unnamed lanes, farm tracks, towpaths not designated for bikes
  main    a B or C road (secondary or tertiary)
  busy    an A road (primary or trunk)
plus signed cycle routes followed and police-reported cycle collisions (STATS19 2021-25) within 30 m. A-road stretches
of 300 m or more and B or C road stretches of 1 km or more are listed as places a proper path should be built."""
import collections, csv, hashlib, json, math, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
CACHE = os.path.join(RAW, 'danelaw')
UA = {'User-Agent': 'CycleStats/1.0 (https://github.com/KevinMayfield/CycleStats)'}
AREAS = ['rutland', 'leicestershire', 'derbyshire', 'nottinghamshire', 'lincolnshire', 'grimsby-scunthorpe', 'east-riding', 'hull',
         'north-yorkshire', 'york', 'leeds', 'wakefield', 'doncaster-barnsley']

# routes, stages and legs. Points are (name, lat, lon); link legs may add via points after the end point.
ROUTES = [
    dict(id='main', name='The Danelaw Way', sub='Repton to Stamford Bridge', stages=[
        dict(name='Repton to Derby', note='From the Great Army camp at Repton past the Viking cemetery at Heath Wood, over the Trent at Swarkestone Bridge', pts=[
            ('Repton', 52.8390, -1.5500), ('Ingleby', 52.8290, -1.4950), ('Swarkestone', 52.8530, -1.4520), ('Chellaston', 52.8700, -1.4400),
            ('Derby', 52.9255, -1.4740)]),
        dict(name='Derby to Long Eaton', note='Down the Derwent valley to the Trent', pts=[
            ('Derby', 52.9255, -1.4740), ('Borrowash', 52.9050, -1.3830), ('Draycott', 52.8950, -1.3350), ('Long Eaton', 52.8980, -1.2710)]),
        dict(name='Long Eaton to Newark', note='Down the Trent past Nottingham', pts=[
            ('Long Eaton', 52.8980, -1.2710), ('Beeston Lock', 52.9174, -1.2083), ('Trent Bridge, Nottingham', 52.9370, -1.1460),
            ('Gunthorpe', 52.9830, -0.9960), ('Hoveringham', 53.0110, -0.9540), ('Fiskerton', 53.0520, -0.9130), ('Kelham', 53.0900, -0.8460),
            ('Newark-on-Trent', 53.0770, -0.8130)]),
        dict(name='Newark to Gainsborough', note='North along the Lincolnshire bank of the Trent past the Great Army camp at Torksey', pts=[
            ('Newark-on-Trent', 53.0770, -0.8130), ('Winthorpe', 53.0960, -0.7780), ('Collingham', 53.1440, -0.7490), ('Besthorpe', 53.1770, -0.7390),
            ('Girton', 53.1958, -0.7556), ('Newton on Trent', 53.2570, -0.7330), ('Torksey', 53.2985, -0.7430), ('Marton', 53.3260, -0.7440),
            ('Gainsborough', 53.3980, -0.7760)]),
        dict(name='Gainsborough to Goole', note='Down the Trent to Keadby, then across the Isle of Axholme', pts=[
            ('Gainsborough', 53.3980, -0.7760), ('Morton', 53.4120, -0.7740), ('East Ferry', 53.4880, -0.7780), ('Susworth', 53.5170, -0.7700),
            ('Burringham', 53.5760, -0.7350), ('Keadby', 53.5960, -0.7380), ('Crowle', 53.6090, -0.8190), ('Swinefleet', 53.6930, -0.8240),
            ('Goole', 53.7030, -0.8740)]),
        dict(name='Goole to Selby', note='Over the Ouse at Boothferry to Howden, then up the Ouse', pts=[
            ('Goole', 53.7030, -0.8740), ('Howden', 53.7450, -0.8680), ('Barmby on the Marsh', 53.7450, -0.9580),
            ('Hemingbrough', 53.7690, -0.9770), ('Selby', 53.7840, -1.0670)]),
        dict(name='Selby to York', note='Up the Ouse past Riccall and Fulford to Jorvik', pts=[
            ('Selby', 53.7840, -1.0670), ('Riccall', 53.8330, -1.0590), ('Naburn', 53.9135, -1.0875), ('Fulford', 53.9370, -1.0710),
            ('York', 53.9620, -1.0815)]),
        dict(name='York to Stamford Bridge', note='East from Jorvik to the battlefield of 1066', pts=[
            ('York', 53.9620, -1.0815), ('Osbaldwick', 53.9600, -1.0300), ('Dunnington', 53.9650, -0.9850), ('Stamford Bridge', 53.9920, -0.9140)]),
    ]),
    dict(id='lincoln', name='The Lindsey Ridings', sub='Torksey to Howden through Lindsey, by Lincoln, Grimsby and the Humber', joins='Torksey and Howden', stages=[
        dict(name='Torksey to Lincoln', note='Along the Fossdyke, the Roman canal, into Lincoln', pts=[
            ('Torksey', 53.2985, -0.7430), ('Saxilby', 53.2690, -0.6640), ('Lincoln', 53.2307, -0.5406)]),
        dict(name='Lincoln to Grimsby', note='North-east by Market Rasen and Caistor on the edge of the Wolds to the Humber coast', pts=[
            ('Lincoln', 53.2307, -0.5406), ('Langworth', 53.2700, -0.4250), ('Market Rasen', 53.3880, -0.3370), ('Caistor', 53.4970, -0.3180),
            ('Laceby', 53.5400, -0.1650), ('Grimsby', 53.5670, -0.0810)]),
        dict(name='Grimsby to Barton-upon-Humber', note='Along the south bank of the Humber by Immingham and Goxhill', pts=[
            ('Grimsby', 53.5670, -0.0810), ('Stallingborough', 53.5880, -0.1880), ('Immingham', 53.6120, -0.2180), ('East Halton', 53.6550, -0.3100),
            ('Goxhill', 53.6760, -0.3360), ('Barrow upon Humber', 53.6780, -0.3830), ('Barton-upon-Humber', 53.6840, -0.4390)]),
        dict(name='Barton-upon-Humber to Howden', note='Over the Humber Bridge and west along the north bank', pts=[
            ('Barton-upon-Humber', 53.6840, -0.4390), ('Hessle', 53.7230, -0.4380), ('North Ferriby', 53.7210, -0.5040), ('Brough', 53.7290, -0.5720),
            ('Howden', 53.7450, -0.8680)]),
    ]),
    dict(id='soar', name='Soar variant', sub='Leicester to Long Eaton', joins='Long Eaton', stages=[
        dict(name='Leicester to Long Eaton', note='Down the Soar from Leicester, one of the Five Boroughs, to the Trent', pts=[
            ('Leicester', 52.6340, -1.1430), ('Birstall', 52.6760, -1.1200), ('Barrow upon Soar', 52.7530, -1.1500), ('Loughborough', 52.7720, -1.2050),
            ('Normanton on Soar', 52.8050, -1.2400), ('Kegworth', 52.8330, -1.2740), ('Long Eaton', 52.8980, -1.2710)]),
    ]),
    dict(id='coast', name='Coast route', sub='Leicester to Barton-upon-Humber by the Wash and the Lincolnshire coast', joins='Barton-upon-Humber', stages=[
        dict(name='Leicester to Stamford', note='East through Oakham and round Rutland Water to Stamford, the fifth of the Five Boroughs', pts=[
            ('Leicester', 52.6340, -1.1430), ('Houghton on the Hill', 52.6240, -1.0130), ('Oakham', 52.6700, -0.7280), ('Manton', 52.6330, -0.6850),
            ('Edith Weston', 52.6380, -0.6250), ('Empingham', 52.6680, -0.5960), ('Stamford', 52.6530, -0.4800)]),
        dict(name='Stamford to the Wash', note='Down the Welland past Market Deeping, Crowland and Spalding to Fosdyke', pts=[
            ('Stamford', 52.6530, -0.4800), ('Market Deeping', 52.6770, -0.3180), ('Crowland', 52.6760, -0.1680), ('Cowbit', 52.7440, -0.1370),
            ('Spalding', 52.7870, -0.1530), ('Fosdyke', 52.8745, -0.0450)]),
        dict(name='Round the Wash to Wainfleet', note='By Boston and the sea banks at Freiston Shore', pts=[
            ('Fosdyke', 52.8745, -0.0450), ('Kirton', 52.9250, -0.0650), ('Boston', 52.9760, -0.0250), ('Freiston Shore', 52.9620, 0.0850),
            ('Wrangle', 53.0380, 0.1170), ('Wainfleet', 53.1060, 0.2340)]),
        dict(name='Wainfleet to Mablethorpe', note='By Gibraltar Point and Skegness, then north along the coast by Ingoldmells and Sutton on Sea', pts=[
            ('Wainfleet', 53.1060, 0.2340), ('Gibraltar Point', 53.1030, 0.3300), ('Skegness', 53.1440, 0.3390), ('Ingoldmells', 53.1920, 0.3410),
            ('Chapel St Leonards', 53.2240, 0.3360), ('Sutton on Sea', 53.3110, 0.2830), ('Mablethorpe', 53.3410, 0.2610)]),
        dict(name='Mablethorpe to Cleethorpes', note='Along the marsh coast by Saltfleet and Donna Nook to the mouth of the Humber', pts=[
            ('Mablethorpe', 53.3410, 0.2610), ('Theddlethorpe', 53.3650, 0.2290), ('Saltfleet', 53.4210, 0.1780), ('North Somercotes', 53.4510, 0.1380),
            ('Tetney', 53.4910, -0.0170), ('Humberston', 53.5320, -0.0300), ('Cleethorpes', 53.5600, -0.0290)]),
        dict(name='Cleethorpes to Barton-upon-Humber', note='Through Grimsby and along the south bank of the Humber by Immingham and Goxhill', pts=[
            ('Cleethorpes', 53.5600, -0.0290), ('Grimsby', 53.5670, -0.0810), ('Stallingborough', 53.5880, -0.1880), ('Immingham', 53.6120, -0.2180),
            ('East Halton', 53.6550, -0.3100), ('Goxhill', 53.6760, -0.3360), ('Barrow upon Humber', 53.6780, -0.3830), ('Barton-upon-Humber', 53.6840, -0.4390)]),
    ]),
    dict(id='skegness', name='Skegness route', sub='Newark to Skegness by Lincoln, the Witham and Woodhall Spa, keeping to the low ground', joins='Newark, a day from Nottingham along the Trent', stages=[
        dict(name='Newark to Lincoln', note='Across the flat Brant and Witham valleys by Bassingham, avoiding the Lincoln Edge', pts=[
            ('Newark', 53.0770, -0.8130), ('Coddington', 53.0820, -0.7580), ('Stapleford', 53.0950, -0.7020), ('Bassingham', 53.1290, -0.6350),
            ('Aubourn', 53.1750, -0.5960), ('North Hykeham', 53.1840, -0.5800), ('Lincoln', 53.2307, -0.5406)]),
        dict(name='Lincoln to Woodhall Spa', note='Down the Witham by the Water Rail Way, past Bardney Abbey', pts=[
            ('Lincoln', 53.2307, -0.5406), ('Washingborough', 53.2260, -0.4810), ('Bardney', 53.2080, -0.3390), ('Southrey', 53.1890, -0.2880),
            ('Stixwould', 53.1700, -0.2420), ('Woodhall Spa', 53.1530, -0.2180)]),
        dict(name='Woodhall Spa to Skegness', note='Across the East Fen below the southern end of the Wolds, to the sea', pts=[
            ('Woodhall Spa', 53.1530, -0.2180), ('Tattershall', 53.1000, -0.1920), ('Coningsby', 53.1070, -0.1720), ('New Bolingbroke', 53.1080, -0.0450),
            ('Stickney', 53.0980, 0.0060), ('Firsby', 53.1690, 0.1690), ('Burgh le Marsh', 53.1610, 0.2450), ('Skegness', 53.1440, 0.3390)]),
    ]),
    dict(id='aire', name='Aire variant', sub='Leeds to the Ouse', joins='Airmyn, on the Ouse near Howden', stages=[
        dict(name='Leeds to Castleford', note='Down the Aire and the Aire and Calder Navigation', pts=[
            ('Leeds', 53.7945, -1.5410), ('Woodlesford', 53.7570, -1.4430), ('Allerton Bywater', 53.7450, -1.3700), ('Castleford', 53.7255, -1.3560)]),
        dict(name='Castleford to the Ouse', note='Past Knottingley and Snaith to the Ouse at Airmyn', pts=[
            ('Castleford', 53.7255, -1.3560), ('Knottingley', 53.7080, -1.2470), ('Snaith', 53.6920, -1.0280), ('Rawcliffe', 53.6910, -0.9630),
            ('Airmyn', 53.7190, -0.9010)]),
    ]),
]

SITES = [
    dict(name='Leicester', lat=52.6340, lon=-1.1430, on='soar', text='One of the Five Boroughs of the Danelaw, and the start of the Soar variant. Æthelflæd of Mercia took it back from the Danes in 918.'),
    dict(name='Heath Wood, Ingleby', lat=52.8270, lon=-1.5070, on='main', text='The only known Viking cremation cemetery in Britain: around 60 barrows in the wood above the Trent, on the first stage of the Way.'),
    dict(name='Repton', lat=52.8390, lon=-1.5500, on='main', text='Where the Way begins, up the Trent from Derby. The Great Heathen Army wintered here in 873–874 and drove out the Mercian king; a Viking camp and burials have been excavated by the church.'),
    dict(name='Derby', lat=52.9255, lon=-1.4740, on='main', text='One of the Five Boroughs. Its name is Old Norse, Djúrabý, "deer farm". Æthelflæd, Lady of the Mercians, took it back from the Danes in 917.'),
    dict(name='Nottingham', lat=52.9370, lon=-1.1460, on='main', text='Another of the Five Boroughs. The Great Heathen Army wintered here in 867–868.'),
    dict(name='Stow Minster', lat=53.3270, lon=-0.6760, on=None, text='Off the route, 5 km from Torksey. A great Anglo-Saxon minster with the earliest known carving of a Viking ship in England scratched into a pillar.'),
    dict(name='Torksey', lat=53.2985, lon=-0.7430, on='main', text='The Great Army\'s winter camp of 872–873, where the Fossdyke meets the Trent. Excavation and metal-detecting have found thousands of finds: hack silver, weights and lead gaming pieces.'),
    dict(name='Fossdyke', lat=53.2690, lon=-0.6640, on='lincoln', text='A canal joining the Trent at Torksey to the Witham at Lincoln, probably Roman and still navigable.'),
    dict(name='Gainsborough', lat=53.3990, lon=-0.7750, on='main', text='On the Trent north of Torksey. Sweyn Forkbeard, king of Denmark, made it his base when he conquered England in 1013 and died there in 1014.'),
    dict(name='Lincoln', lat=53.2290, lon=-0.5450, on='lincoln', text='One of the Five Boroughs, with a busy Viking-age mint. Lincoln was the chief town of Lindsey, the old kingdom that the Danes divided into three ridings, from the Old Norse þriðjungr, a third: the Lindsey Ridings take their name from them. The Lindsey Ridings leaves north-east for Grimsby and the Humber coast.'),
    dict(name='Stamford', lat=52.6530, lon=-0.4800, on='coast', text='The fifth of the Five Boroughs, on the Welland, with a Danish fortified borough north of the river. The coast route turns down the Welland here.'),
    dict(name='Crowland', lat=52.6760, lon=-0.1680, on='coast', text='Crowland Abbey stands in the Fens by the Welland. Later medieval chronicles claimed the Danes burned it in 870, though that account is now thought unreliable.'),
    dict(name='Bardney Abbey', lat=53.2130, lon=-0.3330, on='skegness', text='A royal monastery of Lindsey and Mercia, the shrine of St Oswald. It was destroyed by the Danes around 870 and not refounded until after the Norman Conquest.'),
    dict(name='Skegness', lat=53.1440, lon=0.3390, on='coast', text='Where the coast route and the Skegness route meet the sea. Its name is Old Norse: Skeggi\'s ness, the headland of a man called Skeggi.'),
    dict(name='Lincolnshire Wolds', lat=53.4970, lon=-0.3180, on='lincoln', text='Tealby, Normanby, Grimsby and dozens more: Lincolnshire has more Old Norse -by place names than any other English county, many of them strung along these chalk hills. The Lindsey Ridings cross their western edge at Caistor, close to the Viking Way footpath.'),
    dict(name='Barton-upon-Humber', lat=53.6845, lon=-0.4390, on='lincoln', text='The old ferry town on the south bank of the Humber. St Peter\'s Church has an Anglo-Saxon tower from around the end of the 10th century.'),
    dict(name='Grimsby', lat=53.5670, lon=-0.0810, on='lincoln', text='On the Humber coast: by tradition named after Grim, a Danish fisherman, with the Old Norse -by for farm or village. The Lindsey Ridings reaches the sea here.'),
    dict(name='Humber', lat=53.7090, lon=-0.4500, on='lincoln', text='The estuary the Great Army crossed on its way to York in 866. The Lindsey Ridings crosses it on the Humber Bridge.'),
    dict(name='Leeds', lat=53.7945, lon=-1.5410, on='aire', text='Leeds Minster keeps a 10th-century Anglo-Scandinavian stone cross carved with Weland the Smith, a hero of Norse legend. Start of the Aire variant.'),
    dict(name='Castleford', lat=53.7255, lon=-1.3560, on='aire', text='In 948 the army of Viking York under Eric Bloodaxe caught King Eadred\'s rearguard here and slaughtered it, the Anglo-Saxon Chronicle records.'),
    dict(name='Selby', lat=53.7845, lon=-1.0640, on='main', text='A name of Old Norse origin, probably "willow farm", like many -by places along the Way.'),
    dict(name='Riccall', lat=53.8330, lon=-1.0590, on='main', text='Harald Hardrada\'s fleet came up the Ouse and landed here in September 1066, the last great Viking invasion of England.'),
    dict(name='Fulford', lat=53.9370, lon=-1.0710, on='main', text='Harald Hardrada beat the northern earls here on 20 September 1066, five days before his defeat at Stamford Bridge.'),
    dict(name='Stamford Bridge', lat=53.9920, lon=-0.9140, on='main', text='Where the Way ends, east of York. Harold Godwinson defeated and killed Harald Hardrada here on 25 September 1066, the end of the Viking Age in England.'),
    dict(name='York', lat=53.9580, lon=-1.0850, on='main', text='Jorvik. The Great Heathen Army took it on 1 November 866, and it was the capital of a Viking kingdom until Eric Bloodaxe was driven out in 954.'),
]

K = math.cos(math.radians(53.3)) * 111320; KY = 110574
P = lambda la, lo: ((lo + 1.0) * K, (la - 53.3) * KY)
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])


def fetch(url, data=None, tries=4):
    for attempt in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=300).read()
        except Exception as e: print('  retry', e); time.sleep(15 * (attempt + 1))
    sys.exit('download failed: ' + url[:80])


def brouter(pts):
    key = hashlib.md5(json.dumps(pts).encode()).hexdigest()[:12]; path = os.path.join(CACHE, f'link_{key}.geojson')
    if not os.path.exists(path):
        lonlats = '|'.join(f'{lo},{la}' for _, la, lo in pts)
        json.dump(json.loads(fetch(f'https://brouter.de/brouter?lonlats={urllib.parse.quote(lonlats, safe=",|")}&profile=trekking&alternativeidx=0&format=geojson')), open(path, 'w'))
        time.sleep(2)
    return json.load(open(path))


class Grid:
    def __init__(s, cell=60): s.c = cell; s.d = collections.defaultdict(list)
    def add(s, key, a, b):
        for i in range(int(min(a[0], b[0]) // s.c), int(max(a[0], b[0]) // s.c) + 1):
            for j in range(int(min(a[1], b[1]) // s.c), int(max(a[1], b[1]) // s.c) + 1): s.d[(i, j)].append((key, a, b))
    def within(s, p, maxd):
        """keys of segments within maxd of p, with their distance"""
        out = {}; i, j = int(p[0] // s.c), int(p[1] // s.c); r = int(maxd // s.c) + 1
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                for key, a, b in s.d.get((i + di, j + dj), ()):
                    dx, dy = b[0] - a[0], b[1] - a[1]; L = dx * dx + dy * dy
                    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
                    d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
                    if d <= maxd and d < out.get(key, 1e9): out[key] = d
        return out


def main():
    os.makedirs(CACHE, exist_ok=True)

    # 1. each stage's waypoints are hand-picked villages on one bank, so the router follows the river without
    #    crossing back and forth or wandering off along signed routes between villages
    for r in ROUTES:
        for st in r['stages']: st['via'] = [q[0] for q in st['pts']]

    # 2. route each stage with BRouter (cached)
    for r in ROUTES:
        for st in r['stages']:
            st['geo'] = brouter(st['pts'])

    # 3. OpenStreetMap and collision data for the areas the routes cross
    paths, roads, ncn = Grid(50), Grid(50), Grid(50); rinfo, ninfo, places = {}, {}, []
    for a in AREAS:
        d = os.path.join(RAW, a, 'osm')
        if not os.path.exists(d): continue
        for w in json.load(open(os.path.join(d, 'paths.json')))['elements']:
            if w['type'] != 'way': continue
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): paths.add(w['id'], g[i], g[i + 1])
        for w in json.load(open(os.path.join(d, 'roads.json')))['elements']:
            t = w['tags']; rinfo[w['id']] = (t.get('name'), t.get('ref'), t.get('highway', ''), t.get('maxspeed'))
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): roads.add(w['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'routes.json')))['elements']:
            if e['type'] != 'relation': continue
            t = e.get('tags', {}); nm = t.get('name') or (('NCN ' + t['ref']) if t.get('ref') else None)
            if not nm or t.get('network') not in ('ncn', 'rcn', 'lcn'): continue
            ninfo[e['id']] = nm
            for m in e['members']:
                g = [P(p['lat'], p['lon']) for p in (m.get('geometry') or []) if p]
                for i in range(len(g) - 1): ncn.add(e['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'ctx.json')))['elements']:
            if e['type'] == 'node' and e['tags'].get('name') and e['tags'].get('place') in ('city', 'town', 'village', 'suburb'):
                places.append((e['tags']['name'], P(e['lat'], e['lon'])))
    cyc = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
    cg = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv'))):
        if r['collision_index'] not in cyc: continue
        try: la, lo = float(r['latitude']), float(r['longitude'])
        except ValueError: continue
        if 52.5 < la < 54.1 and -1.7 < lo < 0.5:
            p = P(la, lo); cg[(int(p[0] // 100), int(p[1] // 100))].append((r['collision_index'], p, la, lo, int(r['collision_severity'])))

    def near(grid, p, maxd):
        hits = grid.within(p, maxd)
        return min(hits.items(), key=lambda kv: kv[1])[0] if hits else None

    def classify(p):
        if near(paths, p, 12): return 'path', None
        k = near(roads, p, 12)
        if not k: return 'track', None
        hw = rinfo[k][2].replace('_link', '')
        return ('busy' if hw in ('motorway', 'trunk', 'primary') else 'main' if hw in ('secondary', 'tertiary') else 'quiet'), k

    # 4. measure every 25 m
    out_routes, segs, coll_all = [], [], {}
    for r in ROUTES:
        rstages = []
        for sn, st in enumerate(r['stages'], 1):
            coords = st['geo']['features'][0]['geometry']['coordinates']; props = st['geo']['features'][0]['properties']
            samples = []
            for a, b in zip(coords, coords[1:]):
                L = dist(P(a[1], a[0]), P(b[1], b[0])); k = max(1, int(L // 25))
                for i in range(k): samples.append((a[1] + (b[1] - a[1]) * i / k, a[0] + (b[0] - a[0]) * i / k, L / k))
            mix = collections.Counter(); onroute = collections.Counter(); seen = set(); ksi = 0; runs = []; cur = None
            for s in samples:
                p = P(s[0], s[1]); w = s[2]; cls, k = classify(p)
                mix[cls] += w
                rid = near(ncn, p, 15)
                if rid: onroute[ninfo[rid]] += w
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        for ci, q, la, lo, sev in cg.get((int(p[0] // 100) + di, int(p[1] // 100) + dj), ()):
                            if ci not in seen and dist(p, q) < 30:
                                seen.add(ci); coll_all[ci] = [round(la, 5), round(lo, 5), sev]; ksi += sev <= 2
                if cur is None or cur['cls'] != cls:
                    if cur: cur['pts'].append([round(s[0], 5), round(s[1], 5)])
                    cur = dict(cls=cls, route=r['id'], stage=sn, pts=[], km=0, keys=collections.Counter())
                    runs.append(cur); segs.append(cur)
                cur['pts'].append([round(s[0], 5), round(s[1], 5)]); cur['km'] += w / 1000
                if k: cur['keys'][k] += 1
            # where a proper path is needed: A-road stretches of 300 m or more, B and C road stretches of 1 km or more
            todo = []
            for run in runs:
                if (run['cls'] == 'busy' and run['km'] >= 0.3) or (run['cls'] == 'main' and run['km'] >= 1.0):
                    mid = run['pts'][len(run['pts']) // 2]; pm = P(*mid)
                    k = run['keys'].most_common(1)[0][0] if run['keys'] else None
                    nm, ref, hw, ms = rinfo[k] if k else (None, None, '', None)
                    nc = sum(1 for c in coll_all.values() if any(dist(P(c[0], c[1]), P(*q)) < 30 for q in run['pts'][::8]))
                    todo.append(dict(cls=run['cls'], km=round(run['km'], 1), road=nm or ref or ('A road' if run['cls'] == 'busy' else 'B or C road'),
                                     ref=ref, speed=ms, near=min(places, key=lambda x: dist(x[1], pm))[0] if places else '',
                                     collisions=nc, lat=mid[0], lon=mid[1]))
            km = int(props['track-length']) / 1000
            # height profile: metres above sea level every 500 m along the stage
            prof, acc, nxt = [], 0.0, 0.0
            for a, b in zip(coords, coords[1:]):
                if acc >= nxt and len(a) > 2: prof.append(round(a[2])); nxt += 500
                acc += dist(P(a[1], a[0]), P(b[1], b[0]))
            if len(coords[-1]) > 2: prof.append(round(coords[-1][2]))
            rstages.append(dict(n=sn, name=st['name'], note=st['note'], km=round(km, 1), ascent=int(props.get('filtered ascend', 0)), profile=prof,
                                mix={c: round(v / 1000, 1) for c, v in mix.items()}, via=st['via'],
                                routes=[dict(name=k, km=round(v / 1000, 1)) for k, v in onroute.most_common(4) if v >= 1000],
                                signed=round(sum(onroute.values()) / max(1, sum(mix.values())) * 100), collisions=len(seen), ksi=ksi,
                                todo=sorted(todo, key=lambda t: -t['km'])))
        tot = collections.Counter()
        for s in rstages:
            for c, v in s['mix'].items(): tot[c] += v
        kmr = sum(s['km'] for s in rstages)
        out_routes.append(dict(id=r['id'], name=r['name'], sub=r['sub'], joins=r.get('joins'), km=round(kmr, 1),
                               ascent=sum(s['ascent'] for s in rstages), mix={c: round(v, 1) for c, v in tot.items()},
                               signed=round(sum(s['signed'] * s['km'] for s in rstages) / max(kmr, 1)), stages=rstages))
    for s in segs:
        s.pop('keys', None); s['km'] = round(s['km'], 2)
        s['pts'] = s['pts'][::3] + ([s['pts'][-1]] if len(s['pts']) % 3 != 1 else [])
    out = dict(routes=out_routes, segments=segs, collisions=list(coll_all.values()), sites=SITES)
    json.dump(out, open(os.path.join(HERE, '..', 'data', 'danelaw.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for r in out_routes:
        print(f"{r['name']}: {r['km']} km, {r['ascent']} m up, signed {r['signed']}%, {r['mix']}")
        for s in r['stages']:
            print(f"   {s['n']}. {s['name']}: {s['km']} km {s['mix']} to do: {[(t['road'], t['km']) for t in s['todo'][:4]]}")


if __name__ == '__main__':
    main()
