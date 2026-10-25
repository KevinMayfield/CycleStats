"""Shared settings and geometry for one study area. Every pipeline script takes the area id as its first argument."""
import collections, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AREAS = json.load(open(os.path.join(HERE, 'areas.json')))
AREA = sys.argv[1] if len(sys.argv) > 1 else 'leeds'
CFG = AREAS[AREA]
S = os.path.join(HERE, '..', 'raw') + '/'          # shared downloads (national DfT files, Leeds counters)
A = os.path.join(S, AREA) + '/'                     # this area's downloads and working files
os.makedirs(A + 'work', exist_ok=True)

# local equirectangular projection in metres, centred on the area
LAT0, LON0 = CFG['centre']
K = math.cos(math.radians(LAT0)) * 111320; KY = 110574
def P(lat, lon): return ((lon - LON0) * K, (lat - LAT0) * KY)
def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])
def glen(g): return sum(dist(P(*g[i]), P(*g[i + 1])) for i in range(len(g) - 1))

# --- boundary: an admin area (outer ways of its OSM relation) or a bbox rectangle ---
if 'bbox' in CFG:
    s_, w_, n_, e_ = CFG['bbox']
    ring = [(s_, w_), (s_, e_), (n_, e_), (n_, w_), (s_, w_)]
    edges = [(ring[i][1], ring[i][0], ring[i + 1][1], ring[i + 1][0]) for i in range(4)]
    bnd = [[list(p) for p in ring]]
else:
    # one or more council boundary relations; even-odd ray casting works across all of their edges
    rels = [e for e in json.load(open(A + 'osm/paths.json'))['elements'] if e['type'] == 'relation']
    edges = []; rings = []
    for rel in rels:
        pieces = []
        for m in rel['members']:
            if m['type'] == 'way' and m.get('role') == 'outer':
                g = [(p['lat'], p['lon']) for p in m['geometry']]
                for i in range(len(g) - 1): edges.append((g[i][1], g[i][0], g[i + 1][1], g[i + 1][0]))
                pieces.append(g)
        # chain each council's outer ways end to end into closed rings, so it draws as one shape
        while pieces:
            ring = pieces.pop(0)
            while ring[0] != ring[-1]:
                nxt = next((i for i, p in enumerate(pieces) if ring[-1] in (p[0], p[-1])), None)
                if nxt is None: break
                p = pieces.pop(nxt)
                ring += (p if p[0] == ring[-1] else p[::-1])[1:]
            rings.append(ring)
    bnd = [[[round(la, 5), round(lo, 5)] for la, lo in r[::3] + [r[-1]]] for r in rings]
ecache = {}
def inside(lat, lon):
    """even-odd ray cast against the boundary edges"""
    k = (round(lat, 5), round(lon, 5))
    if k in ecache: return ecache[k]
    c = False
    for x1, y1, x2, y2 in edges:
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1: c = not c
    ecache[k] = c; return c
def clip(g):
    """split a [(lat,lon)] line into pieces inside the area"""
    out = []; cur = []
    for p in g:
        if inside(*p): cur.append(p)
        else:
            if len(cur) > 1: out.append(cur)
            cur = []
    if len(cur) > 1: out.append(cur)
    return out

# --- grid index for segments ---
class Grid:
    def __init__(s, cell=60): s.c = cell; s.d = collections.defaultdict(list)
    def add(s, key, a, b):
        x0, x1 = sorted((a[0], b[0])); y0, y1 = sorted((a[1], b[1]))
        for i in range(int(x0 // s.c), int(x1 // s.c) + 1):
            for j in range(int(y0 // s.c), int(y1 // s.c) + 1): s.d[(i, j)].append((key, a, b))
    def near(s, p, maxd, ok=None):
        best = (maxd, None); i, j = int(p[0] // s.c), int(p[1] // s.c); r = int(maxd // s.c) + 1
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                for key, a, b in s.d.get((i + di, j + dj), ()):
                    if ok and not ok(key): continue
                    dd = segd(p, a, b)
                    if dd < best[0]: best = (dd, key)
        return best
def segd(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]; L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
def simp(g, tol=6):
    """Douglas-Peucker in metres"""
    if len(g) < 3: return g
    pts = [P(*q) for q in g]
    keep = [False] * len(g); keep[0] = keep[-1] = True; st = [(0, len(g) - 1)]
    while st:
        a, b2 = st.pop(); A_, B = pts[a], pts[b2]; dx, dy = B[0] - A_[0], B[1] - A_[1]; L = math.hypot(dx, dy) or 1e-9
        mi, md = None, tol
        for k in range(a + 1, b2):
            dd = abs(dy * (pts[k][0] - A_[0]) - dx * (pts[k][1] - A_[1])) / L
            if dd > md: mi, md = k, dd
        if mi: keep[mi] = True; st += [(a, mi), (mi, b2)]
    return [[round(q[0], 5), round(q[1], 5)] for q, k in zip(g, keep) if k]
def components(lines, tol=40):
    """group lines whose endpoints/vertices touch within tol m"""
    n = len(lines); par = list(range(n))
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    g = Grid(200)
    for i, l in enumerate(lines):
        for q in l[::max(1, len(l) // 20)] + [l[-1]]: g.d[(int(P(*q)[0] // 200), int(P(*q)[1] // 200))].append(i)
    for i, l in enumerate(lines):
        for q in (l[0], l[-1]):
            p = P(*q); ci, cj = int(p[0] // 200), int(p[1] // 200)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for j in g.d.get((ci + di, cj + dj), ()):
                        if f(j) != f(i) and min(dist(p, P(*r)) for r in lines[j]) < tol: par[f(j)] = f(i)
    out = collections.defaultdict(list)
    for i in range(n): out[f(i)].append(i)
    return list(out.values())
def load_roads():
    """named roads with a segment grid for snapping"""
    rg = Grid(60); roadways = {}
    for w in json.load(open(A + 'osm/roads.json'))['elements']:
        g = [(p['lat'], p['lon']) for p in w['geometry']]; t = w['tags']
        roadways[w['id']] = (t.get('name'), t.get('ref'), t.get('highway'), g)
        for i in range(len(g) - 1): rg.add(w['id'], P(*g[i]), P(*g[i + 1]))
    return rg, roadways
def collision_rows():
    """cyclist-involved collisions in this area as dict rows"""
    import csv
    cyc = {r['collision_index'] for r in csv.DictReader(open(S + 'dft/cycle_veh.csv'))}
    lad = set(CFG['stats19_lad'])
    for r in csv.DictReader(open(S + 'dft/collisions.csv')):
        if r['collision_index'] not in cyc: continue
        try: la, lo = float(r['latitude']), float(r['longitude'])
        except ValueError: continue
        if (r['local_authority_ons_district'] in lad) if lad else inside(la, lo):
            yield r, la, lo
def aadf_rows():
    """DfT count point rows (2021-2025) for this area's highway authorities, inside the area"""
    import csv
    for r in csv.DictReader(open(A + 'aadf.csv')):
        if 2021 <= int(r['year']) <= 2025 and ('bbox' not in CFG or inside(float(r['latitude']), float(r['longitude']))):
            yield r
