"""How the prediction works: one model of cycling to work across every town, and for each town how much each factor
lifts or holds back its cycling against the typical town. Writes data/predict.json for predict.html.

The model is a straight-line fit of the logarithm of the share who cycle to work (Census 2021) on the town's factors,
so each factor multiplies cycling up or down by a set amount, whatever the town. Factors, all from the other steps:
  hills         average gradient of commute routes (towns.py, PCT)
  conurbation   people working in other towns within 10 km (heritage.py), the industrial revolution
  decline       coalfield, or iron, steel and shipbuilding, by council (industry.py), post-war industrial decline
  short         share of commuters travelling under 5 km (industry.py, Census 2021 TS058)
  nocar, deprived   households with no car (Census 2021) and neighbourhoods in England's most deprived fifth (IMD 2025)
  postwar       share of homes built 1945-1972 (industry.py)
  older         share of residents aged 65+ (industry.py)
  rain          days a year with 1 mm of rain or more, 2011-2020 (Open-Meteo, ERA5 reanalysis), cached in raw/rain/
For what could change, each town also gets: what it would reach with the local effect of the upper quarter of towns of
8,000+ workers (what local action has achieved elsewhere, given the same factors), its Go Dutch share (PCT,
towns.py), its collisions per cyclist index and women's share of cycle commuters (people.py).
  region        North West, and North East and Cumbria, against Yorkshire and the East
  size          people travelling to work (log)
Hull, York and Cambridge are left out of the fit (benchmarks and an outlier) but still get a prediction.
Each town's factor effects are against the typical town (the median of each measure; no industrial past; Yorkshire
and the East); what the factors do not explain is the town's local effect.
"""
import json, math, os, time, urllib.error, urllib.request

from industry import lstsq, model

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
RAIN = os.path.join(HERE, '..', 'raw', 'rain', 'towns_rain.json')
USE_RAIN = os.environ.get('NO_RAIN') is None   # NO_RAIN=1 skips the rain factor (and the download), for testing

# factor: (group shown on the page, the measure, its step for the plain-English effect, step wording)
F = [('hills', 'Hills', lambda t: t['slope'], 1, 'each extra point of route gradient (%)'),
     ('conurbation', 'Towns crowded round it', lambda t: math.log1p(t['around'] / 1000), math.log(2), 'twice as many working in towns within 10 km'),
     ('coal', 'Post-war industrial decline', lambda t: float(t['industry'] == 'coal'), 1, 'a coalfield town'),
     ('steel', 'Post-war industrial decline', lambda t: float(t['industry'] == 'steel'), 1, 'an iron, steel or shipbuilding town'),
     ('short', 'Short commutes', lambda t: t['near'], 10, '10 points more commuters travelling under 5 km'),
     ('nocar', 'Car ownership and deprivation', lambda t: t['nocar'], 10, '10 points more households with no car'),
     ('deprived', 'Car ownership and deprivation', lambda t: t['deprived'], 10, '10 points more deprived neighbourhoods'),
     ('postwar', 'Post-war estates', lambda t: t['postwar'], 10, '10 points more homes built 1945–1972'),
     ('older', 'Older population', lambda t: t['old'], 10, '10 points more residents aged 65+'),
     ('rain', 'Rain', lambda t: t['days'], 10, '10 more days a year with rain'),
     ('west', 'Region', lambda t: float(t['region'] == 'West'), 1, 'being in the North West'),
     ('north', 'Region', lambda t: float(t['region'] == 'North'), 1, 'being in the North East and Cumbria'),
     ('size', 'Town size', lambda t: math.log(t['travel']), math.log(2), 'a town twice the size')]


def rain_days(towns):
    """days a year with 1 mm+ of rain, 2011-2020, for each town, from Open-Meteo (cached). The free service limits
    requests an hour and a day: past the hourly limit this waits and carries on; past the daily limit it stops, and
    towns still missing take the figures of the nearest town that has them (not cached, so a later run fetches them)"""
    done = json.load(open(RAIN)) if os.path.exists(RAIN) else {}
    todo = [t for t in towns if t['id'] not in done]
    for i in range(0, len(todo), 20):
        b = todo[i:i + 20]; d = None
        url = ('https://archive-api.open-meteo.com/v1/archive?latitude=' + ','.join(str(t['lat']) for t in b) + '&longitude=' +
               ','.join(str(t['lon']) for t in b) + '&start_date=2011-01-01&end_date=2020-12-31&daily=precipitation_sum&timezone=Europe/London')
        for _ in range(30):
            try: d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CycleStats'}), timeout=120)); break
            except urllib.error.HTTPError as e:
                if 'Daily' in e.read().decode('utf-8', 'replace'): break
                time.sleep(300)
            except OSError: time.sleep(300)
        if d is None: break
        d = d if isinstance(d, list) else [d]
        for t, x in zip(b, d):
            p = [v for v in x['daily']['precipitation_sum'] if v is not None]
            done[t['id']] = dict(mm=round(sum(p) / len(p) * 365.25), days=round(sum(v >= 1 for v in p) / len(p) * 365.25, 1),
                                 wet=round(sum(v >= 5 for v in p) / len(p) * 365.25, 1))
        os.makedirs(os.path.dirname(RAIN), exist_ok=True); json.dump(done, open(RAIN, 'w'))
    out = dict(done); have = [t for t in towns if t['id'] in done]
    km = lambda a, c: math.hypot((a['lat'] - c['lat']) * 111.2, (a['lon'] - c['lon']) * 111.2 * math.cos(math.radians(a['lat'])))
    for t in towns:
        if t['id'] not in out and have:
            n = min(have, key=lambda h: km(t, h))
            out[t['id']] = dict(done[n['id']], from_town=n['name'].split(' (')[0], from_km=round(km(t, n), 1))
    return out


def main():
    I = json.load(open(os.path.join(DATA, 'industry.json')))['towns']
    P = {t['id']: t for t in json.load(open(os.path.join(DATA, 'people.json')))['towns']}
    TJ = {t['id']: t for t in json.load(open(os.path.join(DATA, 'towns.json')))['towns']}
    T = [dict(t) for t in I if t['cycle'] > 0 and t.get('postwar') is not None and t['around'] is not None]
    rain = rain_days(T) if USE_RAIN else {}
    if not USE_RAIN:
        for t in T: t.update(days=0, mm=0)
    for t in T: t.update(rain.get(t['id'], {}))
    T = [t for t in T if 'days' in t]
    feats = [f for f in F if USE_RAIN or f[0] != 'rain']
    fit = [t for t in T if not t['skip']]
    cols = [(k, g) for k, _, g, _, _ in feats]
    m = model(fit, lambda t: math.log(t['cycle']), cols)
    X = [[1.0] + [g(t) for _, g in cols] for t in fit]; b = lstsq(X, [math.log(t['cycle']) for t in fit])
    # the typical town: the median of each measure, no industrial past, in Yorkshire and the East
    ref = []
    for k, _, g, _, _ in feats:
        v = sorted(g(t) for t in fit)
        ref.append(0.0 if k in ('coal', 'steel', 'west', 'north') else v[len(v) // 2])
    typical = math.exp(b[0] + sum(c * r for c, r in zip(b[1:], ref)))
    terms = []
    for (k, grp, g, step, words), c, mt in zip(feats, b[1:], m['terms']):
        lo, hi = math.log(mt['lo']), math.log(mt['hi'])
        terms.append(dict(key=k, group=grp, words=words, effect=round(100 * (math.exp(c * step) - 1), 1),
                          lo=round(100 * (math.exp(lo * step) - 1), 1), hi=round(100 * (math.exp(hi * step) - 1), 1)))
    towns = []
    for t in T:
        x = [g(t) for _, _, g, _, _ in feats]
        pred = math.exp(b[0] + sum(c * v for c, v in zip(b[1:], x)))
        groups = {}
        for (k, grp, *_), c, v, r in zip(feats, b[1:], x, ref): groups[grp] = groups.get(grp, 0) + c * (v - r)
        towns.append(dict(id=t['id'], name=t['name'], area=t['area_name'], region=t['region'], tier=t['tier'], skip=t['skip'],
                          lat=t['lat'], lon=t['lon'], travel=t['travel'], cycle=t['cycle'], pred=round(pred, 2),
                          local=round(100 * (t['cycle'] / pred - 1), 1),
                          factors={grp: round(100 * (math.exp(v) - 1), 1) for grp, v in groups.items()},
                          dutch=TJ.get(t['id'], {}).get('dutch'), risk=P.get(t['id'], {}).get('rider_index'), women=P.get(t['id'], {}).get('women'),
                          values=dict(slope=t['slope'], around=t['around'], industry=t['industry'], near=t['near'], nocar=t['nocar'],
                                      deprived=t['deprived'], postwar=t['postwar'], old=t['old'], days=t['days'], mm=t['mm'],
                                      rain_from=t.get('from_town'), rain_km=t.get('from_km'))))
    keys = ('slope', 'around', 'near', 'nocar', 'deprived', 'postwar', 'old', 'days', 'mm')
    typ = {k: sorted(t['values'][k] for t in towns if not t['skip'])[len(fit) // 2] for k in keys}
    # what local action achieves: the local effect of the town at the upper quarter, among towns of 8,000+ workers
    loc = sorted(t['local'] for t in towns if not t['skip'] and t['travel'] >= 8000)
    best_local = loc[3 * len(loc) // 4]
    for t in towns: t['reach'] = round(max(t['cycle'], t['pred'] * (1 + best_local / 100)), 2)
    risk = sorted(t['risk'] for t in towns if t['risk'] is not None and t['travel'] >= 8000)
    out = dict(rain_filled=sum(1 for t in T if t.get('from_town')), best_local=best_local, risk_q3=risk[3 * len(risk) // 4], women_median=sorted(t['women'] for t in towns if t['women'] is not None)[len([t for t in towns if t['women'] is not None]) // 2],
               r2=m['r2'], towns_fitted=len(fit), typical=round(typical, 2), typical_values=typ, terms=terms, towns=towns)
    json.dump(out, open(os.path.join(DATA, 'predict.json'), 'w'), separators=(',', ':'))
    print(json.dumps({k: v for k, v in out.items() if k != 'towns'}, indent=1))


if __name__ == '__main__':
    main()
