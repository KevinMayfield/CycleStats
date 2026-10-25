import json,csv,math,collections
import os
HERE=os.path.dirname(os.path.abspath(__file__))
S=os.path.join(HERE,'..','raw')+'/'
src=open(os.path.join(HERE,'build_osm.py')).read().split('# ===== 1. ROUTES')[0]
exec(src.split('# --- boundary edges')[0]); exec(src.split('# --- grid index')[1].split('\n',1)[1])
def segd(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];L=dx*dx+dy*dy;t=0 if L==0 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
rd=json.load(open(S+'osm/roads.json'))
rg=Grid(60);roadways={}
for w in rd['elements']:
    g=[(p['lat'],p['lon']) for p in w['geometry']];t=w['tags']
    roadways[w['id']]=(t.get('name'),t.get('ref'),t.get('highway'),g)
    for i in range(len(g)-1): rg.add(w['id'],P(*g[i]),P(*g[i+1]))
# collisions
cyc={r['collision_index'] for r in csv.DictReader(open(S+'dft/cycle_veh.csv'))}
byway=collections.defaultdict(list)
for r in csv.DictReader(open(S+'dft/leeds_coll.csv')):
    if r['collision_index'] not in cyc: continue
    try: la,lo=float(r['latitude']),float(r['longitude'])
    except: continue
    d,k=rg.near(P(la,lo),40)
    if k: byway[k].append([round(la,5),round(lo,5),int(r['collision_severity']),r['date'],r['speed_limit']])
# count points -> snap to road way (prefer same ref)
cps=collections.defaultdict(list)
for r in csv.DictReader(open(S+'dft/aadf_leeds.csv')):
    if 2021<=int(r['year'])<=2025: cps[r['count_point_id']].append(r)
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
busy=[c for c in corr if c['aadf']>=150 and c['km']>=0.5]
print(len(corr),'corridors with counts;',len(busy),'busy')
safe=sorted(busy,key=lambda c:(c['rate'],-c['aadf']))
for c in safe[:20]: print(f"{c['name'][:26]:26} {str(c['ref']):6} aadf={c['aadf']:4} km={c['km']:5} n={c['n']:2} ksi={c['ksi']} rate={c['rate']}")
d=json.load(open(S+'work/data.json'));d['safe']=safe[:10]
json.dump(d,open(S+'work/data.json','w'),separators=(',',':'))
