"""Compact Danelaw Cycle Network lines for the area maps: each route's outline from data/danelaw.json, its stretches
joined into continuous lines and simplified to ~10 m, so an area map can draw and measure the routes that cross it
without loading the full network file. Writes data/danelaw-lines.json. Run after danelaw.py."""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')


def simp(g, tol=10):
    """Douglas-Peucker on [lat, lon] points, tolerance in metres"""
    if len(g) < 3: return g
    k = math.cos(math.radians(g[0][0])) * 111320
    P = [(lo * k, la * 110574) for la, lo in g]; keep = [False] * len(g); keep[0] = keep[-1] = True; st = [(0, len(g) - 1)]
    while st:
        a, b = st.pop(); (x1, y1), (x2, y2) = P[a], P[b]; L = math.hypot(x2 - x1, y2 - y1) or 1e-9; mi, md = None, tol
        for i in range(a + 1, b):
            d = abs((y2 - y1) * (P[i][0] - x1) - (x2 - x1) * (P[i][1] - y1)) / L
            if d > md: mi, md = i, d
        if mi: keep[mi] = True; st += [(a, mi), (mi, b)]
    return [p for p, k_ in zip(g, keep) if k_]


D = json.load(open(os.path.join(DATA, 'danelaw.json')))
routes = []
for r in D['routes']:
    lines = []
    for seg in (x for x in D['segments'] if x['route'] == r['id']):
        if lines and lines[-1][-1] == seg['pts'][0]: lines[-1] += seg['pts'][1:]   # carries on from the last stretch
        else: lines.append(list(seg['pts']))
    routes.append(dict(id=r['id'], name=r['name'], sub=r['sub'], km=r['km'], lines=[simp(g) for g in lines]))
json.dump(dict(routes=routes), open(os.path.join(DATA, 'danelaw-lines.json'), 'w'), separators=(',', ':'))
print(f"{len(routes)} routes, {sum(len(r['lines']) for r in routes)} lines")
