"""Cycle collision rates on road stretches by cycle provision, using DfT bikes/day as exposure.

    python3 pipeline/infra_rates.py [--split]

Reads raw/<area>/work/priorities.json (run priorities.py first). Only stretches with a DfT cycle count of 20+ bikes/day
are used: counted roads are in the data whether or not anyone crashed there. Rate = collisions / (bikes/day x km x 365
x 5 years) per million cycle-km, pooled across stretches, with 95% bootstrap intervals. --split separates painted lanes
from shared pavements. Results are in CLAUDE.md."""
import json, glob, os, random, sys, collections
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'raw')
S = [{**c, 'area': f.split(os.sep)[-3]} for f in glob.glob(os.path.join(RAW, '*', 'work', 'priorities.json')) for c in json.load(open(f))]
YEARS = 5
def cls(c, split=False):
    p, l = c['protected'], c['lane']
    if split:
        pa, sh = c.get('paint', 0), c.get('shared', 0)
        if p >= .5: return '1 mostly protected'
        if pa >= .5: return '2 mostly painted lane'
        if sh >= .5: return '3 mostly shared pavement'
        if p < .1 and l < .1: return '4 nothing'
        return '5 mixed'
    if p >= .5: return '1 mostly protected'
    if l >= .5: return '2 mostly painted or shared'
    if p < .1 and l < .1: return '3 nothing'
    return '4 mixed'
def rate(g, key='n'):
    exp = sum(c['aadf'] * c['km'] * 365 * YEARS for c in g) / 1e6   # million cycle-km
    return sum(c[key] for c in g) / exp if exp else float('nan')
def ci(g, key='n', B=2000):
    random.seed(1); r = sorted(rate([random.choice(g) for _ in g], key) for _ in range(B))
    return r[int(.025 * B)], r[int(.975 * B)]
def table(title, rows, split=False):
    print('\n' + title)
    groups = collections.defaultdict(list)
    for c in rows: groups[cls(c, split)].append(c)
    for k in sorted(groups):
        g = groups[k]; lo, hi = ci(g); kl, kh = ci(g, 'ksi')
        print(f"  {k:28} stretches={len(g):4} km={sum(c['km'] for c in g):6.0f} collisions={sum(c['n'] for c in g):5} "
              f"median bikes/day={sorted(c['aadf'] for c in g)[len(g)//2]:4}  per million cycle-km={rate(g):5.2f} ({lo:.2f}–{hi:.2f})  "
              f"KSI={rate(g,'ksi'):5.2f} ({kl:.2f}–{kh:.2f})")
split = '--split' in sys.argv
base = [c for c in S if c.get('aadf') and c['aadf'] >= 20]     # very low counts make rates unstable
table(f'All counted stretches with 20+ bikes/day ({len(base)})', base, split)
for name, f in [('30 mph or less', lambda c: c['speed'] and c['speed'] <= 30), ('40 mph or more', lambda c: c['speed'] and c['speed'] >= 40),
                ('busy: 100+ bikes/day', lambda c: c['aadf'] >= 100)]:
    table(name, [c for c in base if f(c)], split)
