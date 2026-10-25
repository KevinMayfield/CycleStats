"""Well-used roads (150+ bikes/day on DfT counts) with the fewest cycle collisions per km cycled."""
import json,collections
from area import *
rg,roadways=load_roads()
# collisions
byway=collections.defaultdict(list)
for r,la,lo in collision_rows():
    d,k=rg.near(P(la,lo),40)
    if k: byway[k].append([round(la,5),round(lo,5),int(r['collision_severity']),r['date'],r['speed_limit']])
# count points -> snap to road way (prefer same ref)
cps=collections.defaultdict(list)
for r in aadf_rows(): cps[r['count_point_id']].append(r)
cpway={}
for cid,rs in cps.items():
    r0=rs[0];p=P(float(r0['latitude']),float(r0['longitude']));ref=r0['road_name']
    d,k=rg.near(p,80,(lambda kk:roadways[kk][1]==ref) if ref not in('U','C') else None)
    if not k and ref in ('U','C'): continue
    if not k: d,k=rg.near(p,40)
    if k: cpway[cid]=k
# corridors for every road name that has a count point
names={roadways[k][0] for k in cpway.values()}
byname=collections.defaultdict(list)
for wid,v in roadways.items():
    if v[0] in names: byname[v[0]].append(wid)
corr=[]
for nm,wids in byname.items():
    lines=[roadways[w][3] for w in wids]
    for comp in components(lines,25):
        ws=set(wids[i] for i in comp)
        cp=[cid for cid,k in cpway.items() if k in ws]
        if not cp: continue
        vals=[int(r['pedal_cycles']) for c in cp for r in cps[c]]
        aadf=sum(vals)/len(vals);L=sum(glen(lines[i]) for i in comp)/1000
        pts=[p for w in ws for p in byway.get(w,[])]
        n=len(pts);fat=sum(p[2]==1 for p in pts);ser=sum(p[2]==2 for p in pts)
        refs=collections.Counter(roadways[w][1] for w in ws if roadways[w][1])
        corr.append(dict(name=nm,ref=refs.most_common(1)[0][0] if refs else None,km=round(L,2),n=n,fatal=fat,serious=ser,ksi=fat+ser,score=fat*10+ser*3+(n-fat-ser),
          aadf=round(aadf),rate=round(n/(max(aadf,1)*L*365*5)*1e6,1),counted=sum(r['estimation_method']=='Counted' for c in cp for r in cps[c]),obs=len(vals),match='on road',
          geom=[simp(lines[i]) for i in comp],pts=pts,
          cp_pts=[[float(cps[c][0]['latitude']),float(cps[c][0]['longitude']),round(sum(int(r['pedal_cycles']) for r in cps[c])/len(cps[c])),c] for c in cp]))
# "well used" means 150+ bikes/day; where cycling is lighter and fewer than 10 roads reach that,
# drop the bar to the 20th busiest road's figure (never below 50) so the list still compares the busier roads
long_=[c for c in corr if c['km']>=0.5]
MIN=150
if sum(c['aadf']>=150 for c in long_)<10:
    MIN=max(50,sorted((c['aadf'] for c in long_),reverse=True)[min(19,len(long_)-1)] if long_ else 50)
busy=[c for c in long_ if c['aadf']>=MIN]
print(len(corr),'corridors with counts;',len(busy),'busy')
safe=sorted(busy,key=lambda c:(c['rate'],-c['aadf']))
for c in safe[:20]: print(f"{c['name'][:26]:26} {str(c['ref']):6} aadf={c['aadf']:4} km={c['km']:5} n={c['n']:2} ksi={c['ksi']} rate={c['rate']}")
d=json.load(open(A+'work/data.json'));d['safe']=safe[:10];d['meta']['safe_min']=MIN
json.dump(d,open(A+'work/data.json','w'),separators=(',',':'))
