"""Routes, paths, collisions snapped to named roads, and map context for one area."""
import json,collections,csv
from area import *
b=json.load(open(A+'osm/paths.json'))
# ===== 1. ROUTES =====
r=json.load(open(A+'osm/routes.json'))
rels=[e for e in r['elements'] if e['type']=='relation']
wayroute={}
routes=[]
for e in rels:
    t=e.get('tags',{})
    name=t.get('name') or ('NCN Route '+t['ref'] if t.get('network')=='ncn' and t.get('ref') else t.get('ref'))
    # skip unnamed bits (a bare number) and umbrella relations for a whole network
    if not name or name.isdigit() or name.lower().endswith('network'): continue
    pieces=[];seen=set()
    for m in e['members']:
        if m['type']!='way' or not m.get('geometry') or m['ref'] in seen: continue
        seen.add(m['ref']); wayroute.setdefault(m['ref'],name)
        pieces+=clip([(p['lat'],p['lon']) for p in m['geometry'] if p])
    L=sum(glen(p) for p in pieces)
    if L>500: routes.append(dict(name=name,ref=t.get('ref'),network=t.get('network'),km=round(L/1000,1),geom=[simp(p) for p in pieces]))
# relations split into sections share a name: merge them
merged={}
for x in routes:
    if x['name'] in merged: m_=merged[x['name']];m_['km']=round(m_['km']+x['km'],1);m_['geom']+=x['geom']
    else: merged[x['name']]=x
routes=sorted(merged.values(),key=lambda x:-x['km'])
print('ROUTES');[print(x['km'],x['name'],x['ref'],x['network']) for x in routes[:16]]
# ===== road grid =====
rg,roadways=load_roads()
# ===== 2. PATHS =====
MAJOR={'motorway','trunk','primary','secondary','tertiary'}
paths=collections.defaultdict(list)
for w in [e for e in b['elements'] if e['type']=='way']:
    t=w['tags'];g=[(p['lat'],p['lon']) for p in w['geometry']]
    nm=t.get('name')
    if nm and nm.lower().startswith(('definitive','non-definitive')): nm=None
    kind='Off-road path'
    if not nm:
        mid=P(*g[len(g)//2]);dd,key=rg.near(mid,25,lambda k:roadways[k][2].split('_')[0] in MAJOR)
        if not key: dd,key=rg.near(mid,22)
        if key and t.get('highway')=='cycleway': nm=roadways[key][0];kind='Cycle track beside road'
        elif w['id'] in wayroute: nm=wayroute[w['id']]
    if not nm: continue
    for piece in clip(g): paths[nm].append((piece,kind,t.get('segregated'),t.get('surface')))
plist=[]
for nm,ls in paths.items():
    lines=[x[0] for x in ls]
    for comp in components(lines,40):
        L=sum(glen(lines[i]) for i in comp)
        kinds=collections.Counter(ls[i][1] for i in comp)
        seg=collections.Counter(ls[i][2] for i in comp if ls[i][2])
        plist.append(dict(name=nm,km=round(L/1000,2),kind=kinds.most_common(1)[0][0],segregated=seg.most_common(1)[0][0] if seg else None,geom=[simp(lines[i]) for i in comp]))
plist.sort(key=lambda x:-x['km'])
print('PATHS');[print(x['km'],x['name'],x['kind'],x['segregated']) for x in plist[:20]]
# ===== 3. COLLISIONS =====
pts=[]
for row,lat,lon in collision_rows():
    ci=row['collision_index']
    pts.append(dict(id=ci,lat=lat,lon=lon,sev=int(row['collision_severity']),date=row['date'],year=int(row['collision_year']),speed=row['speed_limit']))
print('cycle collisions in',CFG['name'],len(pts),collections.Counter(p['sev'] for p in pts),collections.Counter(p['year'] for p in pts))
byway=collections.defaultdict(list);miss=0
for p in pts:
    dd,key=rg.near(P(p['lat'],p['lon']),40)
    if key: byway[key].append(p)
    else: miss+=1
print('unsnapped',miss)
# group road ways by name -> connected corridors
byname=collections.defaultdict(list)
for wid,(nm,ref,hw,g) in roadways.items(): byname[nm].append(wid)
corr=[]
for nm,wids in byname.items():
    if not any(w in byway for w in wids): continue
    lines=[roadways[w][3] for w in wids]
    for comp in components(lines,25):
        ws=[wids[i] for i in comp];cp=[p for w in ws for p in byway.get(w,[])]
        if not cp: continue
        L=sum(glen(lines[i]) for i in comp)
        refs=collections.Counter(roadways[w][1] for w in ws if roadways[w][1])
        corr.append(dict(name=nm,ref=refs.most_common(1)[0][0] if refs else None,km=round(L/1000,2),n=len(cp),fatal=sum(p['sev']==1 for p in cp),serious=sum(p['sev']==2 for p in cp),
            ksi=sum(p['sev']<=2 for p in cp),geom=[simp(lines[i]) for i in comp],pts=[[round(p['lat'],5),round(p['lon'],5),p['sev'],p['date'],p['speed']] for p in cp]))
# danger score: collisions weighted (fatal 10, serious 3, slight 1)
for c in corr: c['score']=c['fatal']*10+c['serious']*3+(c['n']-c['fatal']-c['serious'])
corr.sort(key=lambda c:(-c['score'],-c['n']))
print('DANGER');[print(c['score'],c['n'],c['ksi'],c['fatal'],c['km'],c['name'],c['ref']) for c in corr[:20]]
# ===== EXPORT =====
REN=CFG['rename']
for x in routes: x['name']=REN.get(x['name'],x['name'])
top_routes=routes[:10]
m=collections.OrderedDict()
for x in plist:
    nm=REN.get(x['name'],x['name'])
    if nm not in m: m[nm]=dict(name=nm,km=0,kind=x['kind'],segregated=x['segregated'],geom=[])
    m[nm]['km']+=x['km'];m[nm]['geom']+=x['geom']
top_paths=sorted(m.values(),key=lambda x:-x['km'])[:10]
for x in top_paths: x['km']=round(x['km'],1)
ctx=json.load(open(A+'osm/ctx.json'))
water=[dict(n=e['tags'].get('name',''),w=e['tags']['waterway'],g=simp([(p['lat'],p['lon']) for p in e['geometry']],15)) for e in ctx['elements'] if e['type']=='way']
places=[[e['tags']['name'],round(e['lat'],4),round(e['lon'],4),e['tags']['place']] for e in ctx['elements'] if e['type']=='node']
major=[]
for wid,(nm,ref,hw,g) in roadways.items():
    if hw in ('motorway','trunk','primary'): major.append([hw[0],simp(list(g),20)])
out=dict(routes=top_routes,paths=top_paths,danger=corr[:10],allpts=[[round(p['lat'],5),round(p['lon'],5),p['sev']] for p in pts],
  boundary=bnd,water=water,places=places,major=major,stats=dict(n=len(pts),fatal=sum(p['sev']==1 for p in pts),serious=sum(p['sev']==2 for p in pts)))
out['meta']={k:CFG[k] for k in ('name','eyebrow','in','boundary_label','water_label')}
out['meta']['id']=AREA
json.dump(out,open(A+'work/data.json','w'),separators=(',',':'))
print('ROUTES10',[(x['name'],x['km']) for x in top_routes]);print('PATHS10',[(x['name'],x['km'],x['kind']) for x in top_paths])
json.dump(corr[:80],open(A+'work/corr.json','w'))
