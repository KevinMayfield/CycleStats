import json,math,csv,collections,sys
import os
HERE=os.path.dirname(os.path.abspath(__file__))
S=os.path.join(HERE,'..','raw')+'/'
K=math.cos(math.radians(53.8))*111320; KY=110574
def P(lat,lon): return ((lon+1.55)*K, (lat-53.8)*KY)
def dist(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def glen(g): return sum(dist(P(*g[i]),P(*g[i+1])) for i in range(len(g)-1))
# --- boundary edges (even-odd ray cast) ---
b=json.load(open(S+'osm/leeds2.json'))
rel=[e for e in b['elements'] if e['type']=='relation'][0]
edges=[]
for m in rel['members']:
    if m['type']=='way' and m.get('role')=='outer':
        g=m['geometry']
        for i in range(len(g)-1): edges.append((g[i]['lon'],g[i]['lat'],g[i+1]['lon'],g[i+1]['lat']))
bnd=[]
for m in rel['members']:
    if m['type']=='way' and m.get('role')=='outer': bnd.append([[round(p['lat'],5),round(p['lon'],5)] for p in m['geometry'][::3]+[m['geometry'][-1]]])
ecache={}
def inside(lat,lon):
    k=(round(lat,5),round(lon,5))
    if k in ecache: return ecache[k]
    c=False
    for x1,y1,x2,y2 in edges:
        if (y1>lat)!=(y2>lat) and lon < (x2-x1)*(lat-y1)/(y2-y1)+x1: c=not c
    ecache[k]=c; return c
def clip(g):
    """split a [(lat,lon)] line into pieces inside Leeds"""
    out=[];cur=[]
    for p in g:
        if inside(*p): cur.append(p)
        else:
            if len(cur)>1: out.append(cur)
            cur=[]
    if len(cur)>1: out.append(cur)
    return out
# --- grid index for segments ---
class Grid:
    def __init__(s,cell=60): s.c=cell; s.d=collections.defaultdict(list)
    def add(s,key,a,b):
        x0,x1=sorted((a[0],b[0]));y0,y1=sorted((a[1],b[1]))
        for i in range(int(x0//s.c),int(x1//s.c)+1):
            for j in range(int(y0//s.c),int(y1//s.c)+1): s.d[(i,j)].append((key,a,b))
    def near(s,p,maxd,ok=None):
        best=(maxd,None);i,j=int(p[0]//s.c),int(p[1]//s.c);r=int(maxd//s.c)+1
        for di in range(-r,r+1):
            for dj in range(-r,r+1):
                for key,a,b in s.d.get((i+di,j+dj),()):
                    if ok and not ok(key): continue
                    dx,dy=b[0]-a[0],b[1]-a[1];L=dx*dx+dy*dy
                    t=0 if L==0 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L))
                    dd=math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
                    if dd<best[0]: best=(dd,key)
        return best
def simp(g,tol=6):
    # Douglas-Peucker in metres
    if len(g)<3: return g
    pts=[P(*q) for q in g]
    keep=[False]*len(g);keep[0]=keep[-1]=True;st=[(0,len(g)-1)]
    while st:
        a,b2=st.pop();A,B=pts[a],pts[b2];dx,dy=B[0]-A[0],B[1]-A[1];L=math.hypot(dx,dy) or 1e-9
        mi,md=None,tol
        for k in range(a+1,b2):
            dd=abs(dy*(pts[k][0]-A[0])-dx*(pts[k][1]-A[1]))/L
            if dd>md: mi,md=k,dd
        if mi: keep[mi]=True; st+=[(a,mi),(mi,b2)]
    return [[round(q[0],5),round(q[1],5)] for q,k in zip(g,keep) if k]
def components(lines,tol=40):
    """group lines whose endpoints/vertices touch within tol m"""
    n=len(lines);par=list(range(n))
    def f(x):
        while par[x]!=x: par[x]=par[par[x]];x=par[x]
        return x
    g=Grid(200);
    for i,l in enumerate(lines):
        for q in l[::max(1,len(l)//20)]+[l[-1]]: g.d[(int(P(*q)[0]//200),int(P(*q)[1]//200))].append(i)
    for i,l in enumerate(lines):
        for q in (l[0],l[-1]):
            p=P(*q);ci,cj=int(p[0]//200),int(p[1]//200)
            for di in (-1,0,1):
                for dj in (-1,0,1):
                    for j in g.d.get((ci+di,cj+dj),()):
                        if f(j)!=f(i) and min(dist(p,P(*r)) for r in lines[j])<tol: par[f(j)]=f(i)
    out=collections.defaultdict(list)
    for i in range(n): out[f(i)].append(i)
    return list(out.values())
# ===== 1. ROUTES =====
r=json.load(open(S+'osm/leeds.json'))
rels=[e for e in r['elements'] if e['type']=='relation' and e.get('bounds',{}).get('minlon',0)<0]
wayroute={}
routes=[]
for e in rels:
    t=e.get('tags',{})
    name=t.get('name') or ('NCN Route '+t['ref'] if t.get('network')=='ncn' and t.get('ref') else t.get('ref'))
    if not name: continue
    pieces=[];seen=set()
    for m in e['members']:
        if m['type']!='way' or not m.get('geometry') or m['ref'] in seen: continue
        seen.add(m['ref']); wayroute.setdefault(m['ref'],name)
        pieces+=clip([(p['lat'],p['lon']) for p in m['geometry']])
    L=sum(glen(p) for p in pieces)
    if L>500: routes.append(dict(name=name,ref=t.get('ref'),network=t.get('network'),km=round(L/1000,1),geom=[simp(p) for p in pieces]))
routes.sort(key=lambda x:-x['km'])
print('ROUTES');[print(x['km'],x['name'],x['ref'],x['network']) for x in routes[:16]]
# ===== road grid =====
rd=json.load(open(S+'osm/roads.json'))
rg=Grid(60);roadways={}
for w in rd['elements']:
    g=[(p['lat'],p['lon']) for p in w['geometry']];t=w['tags']
    roadways[w['id']]=(t.get('name'),t.get('ref'),t.get('highway'),g)
    for i in range(len(g)-1): rg.add(w['id'],P(*g[i]),P(*g[i+1]))
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
cyc=collections.Counter();
for row in csv.DictReader(open(S+'dft/cycle_veh.csv')): cyc[row['collision_index']]+=1
cas=collections.defaultdict(lambda:[0,0,0])
for row in csv.DictReader(open(S+'dft/cycle_cas.csv')):
    s=int(row['casualty_severity']);cas[row['collision_index']][s-1]+=1
pts=[]
for row in csv.DictReader(open(S+'dft/leeds_coll.csv')):
    ci=row['collision_index']
    if ci not in cyc: continue
    try: lat,lon=float(row['latitude']),float(row['longitude'])
    except: continue
    pts.append(dict(id=ci,lat=lat,lon=lon,sev=int(row['collision_severity']),date=row['date'],year=int(row['collision_year']),speed=row['speed_limit'],cas=cas.get(ci,[0,0,0])))
print('cycle collisions in Leeds',len(pts),collections.Counter(p['sev'] for p in pts),collections.Counter(p['year'] for p in pts))
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
json.dump(dict(routes=routes,paths=plist,corr=corr[:40],allpts=[[round(p['lat'],5),round(p['lon'],5),p['sev']] for p in pts],boundary=bnd),open(S+'work/data.json','w'))
# ===== EXPORT =====
REN={'NCN Route 66':'NCN 66 · Leeds–Bradford–Hull','NCN Route 67':'Trans Pennine Trail (NCN 67)','CS3':'Cycle Superhighway 3','West Yorkshire Cycle Route':'West Yorkshire Cycle Route'}
for x in routes: x['name']=REN.get(x['name'],x['name'])
top_routes=routes[:10]
m=collections.OrderedDict()
for x in plist:
    nm=REN.get(x['name'],x['name'])
    if nm not in m: m[nm]=dict(name=nm,km=0,kind=x['kind'],segregated=x['segregated'],geom=[])
    m[nm]['km']+=x['km'];m[nm]['geom']+=x['geom']
top_paths=sorted(m.values(),key=lambda x:-x['km'])[:10]
for x in top_paths: x['km']=round(x['km'],1)
ctx=json.load(open(S+'osm/ctx.json'))
water=[dict(n=e['tags'].get('name',''),w=e['tags']['waterway'],g=simp([(p['lat'],p['lon']) for p in e['geometry']],15)) for e in ctx['elements'] if e['type']=='way']
places=[[e['tags']['name'],round(e['lat'],4),round(e['lon'],4),e['tags']['place']] for e in ctx['elements'] if e['type']=='node']
major=[]
for wid,(nm,ref,hw,g) in roadways.items():
    if hw in ('motorway','trunk','primary'): major.append([hw[0],simp(list(g),20)])
out=dict(routes=top_routes,paths=top_paths,danger=corr[:10],allpts=[[round(p['lat'],5),round(p['lon'],5),p['sev']] for p in pts],
  boundary=bnd,water=water,places=places,major=major,stats=dict(n=len(pts),fatal=sum(p['sev']==1 for p in pts),serious=sum(p['sev']==2 for p in pts)))
json.dump(out,open(S+'work/data.json','w'),separators=(',',':'))
print('ROUTES10',[(x['name'],x['km']) for x in top_routes]);print('PATHS10',[(x['name'],x['km'],x['kind']) for x in top_paths])
json.dump(corr[:80],open(S+'work/corr.json','w'))
