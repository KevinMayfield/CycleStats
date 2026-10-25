"""Neighbourhood layer and deprivation stats for one area.

Writes data/<area>-imd.json (LSOA outlines with their IMD 2025 decile, Indoors (poor housing) decile and
% of households with no car), and adds to the area's data: how cycle collisions split across the most and
least deprived neighbourhoods, and the IMD decile at each listed road."""
import csv, json
from area import *

HERE_DATA = os.path.join(HERE, '..', 'data')

# IoD 2025: decile 1 = most deprived 10% of LSOAs in England
iod = {}
with open(S + 'imd/imd2025.csv', encoding='utf-8-sig') as f:
    rd = csv.reader(f); head = next(rd)
    col = lambda start: next(i for i, h in enumerate(head) if h.replace('\n', ' ').startswith(start))
    c_code, c_name, c_imd = col('LSOA code'), col('LSOA name'), col('Index of Multiple Deprivation (IMD) Decile')
    c_ind, c_pop = col('Indoors Sub-domain Decile'), col('Total population')
    for r in rd:
        iod[r[c_code]] = (r[c_name], int(r[c_imd]), int(r[c_ind]), int(float(r[c_pop])))
nocar = {r['lsoa']: float(r['pct_no_car']) for r in csv.DictReader(open(S + 'imd/nocar.csv'))}

# LSOAs whose centre lies in the area
lsoas = []
for ft in json.load(open(A + 'lsoa.geojson'))['features']:
    code = ft['properties']['LSOA21CD']
    if code not in iod: continue
    g = ft['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    rings = [[(la, lo) for lo, la in ring] for poly in polys for ring in poly[:1]]  # outer rings only
    big = max(rings, key=len)
    c = (sum(p[0] for p in big) / len(big), sum(p[1] for p in big) / len(big))
    if not inside(*c): continue
    lsoas.append((code, rings))


def contains(rings, la, lo):
    for ring in rings:
        c = False
        for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
            if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / (y2 - y1) + x1: c = not c
        if c: return True
    return False


boxes = [(code, rings, min(p[0] for r in rings for p in r), max(p[0] for r in rings for p in r),
          min(p[1] for r in rings for p in r), max(p[1] for r in rings for p in r)) for code, rings in lsoas]


def lsoa_at(la, lo):
    for code, rings, s, n, w, e in boxes:
        if s <= la <= n and w <= lo <= e and contains(rings, la, lo): return code
    return None


# --- layer file ---
layer = []
for code, rings in lsoas:
    name, imd, ind, pop = iod[code]
    # a closed ring starts and ends on the same point, which Douglas-Peucker can't simplify: drop the closing point first
    layer.append([code, name, imd, ind, nocar.get(code), [simp(r[:-1], 12) + [list(map(lambda v: round(v, 5), r[0]))] for r in rings]])
json.dump({'f': layer}, open(os.path.join(HERE_DATA, AREA + '-imd.json'), 'w'), separators=(',', ':'))

# --- collisions by deprivation: STATS19 records the LSOA each collision happened in ---
codes = {c for c, _ in lsoas}
by_dec = [0] * 10; total = 0
for r, la, lo in collision_rows():
    code = r['lsoa_of_accident_location']
    if code not in iod: code = lsoa_at(la, lo)  # older records can carry 2011 codes
    if code in iod:
        by_dec[iod[code][1] - 1] += 1; total += 1
pop_dec = [0] * 10
for c in codes: pop_dec[iod[c][1] - 1] += iod[c][3]
pop = sum(pop_dec) or 1
d = json.load(open(A + 'work/data.json'))
d['meta']['dep'] = dict(coll_by_decile=by_dec, pop_by_decile=pop_dec, coll_matched=total,
                        coll_share_most=round(100 * sum(by_dec[:2]) / max(total, 1)), pop_share_most=round(100 * sum(pop_dec[:2]) / pop),
                        lsoas=len(lsoas))
print(f"{CFG['name']}: {len(lsoas)} LSOAs; {d['meta']['dep']['coll_share_most']}% of {total} cycle collisions in the most deprived 20% "
      f"(home to {d['meta']['dep']['pop_share_most']}% of residents)")

# --- deprivation at each listed road: the decile of the neighbourhood at the middle of the stretch ---
for k in ('danger', 'risk', 'safe'):
    for it in d.get(k, []):
        pts = [p for g in it['geom'] for p in g]; la, lo = pts[len(pts) // 2]
        code = lsoa_at(la, lo)
        it['imd'] = iod[code][1] if code else None
        it['nocar'] = nocar.get(code)
json.dump(d, open(A + 'work/data.json', 'w'), separators=(',', ':'))
