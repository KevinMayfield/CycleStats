import json,csv,math,collections
import os
HERE=os.path.dirname(os.path.abspath(__file__))
S=os.path.join(HERE,'..','raw')+'/'
K=math.cos(math.radians(53.8))*111320; KY=110574
P=lambda la,lo:((lo+1.55)*K,(la-53.8)*KY)
def segd(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];L=dx*dx+dy*dy;t=0 if L==0 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
corr=json.load(open(S+'work/corr.json'))
rows=[r for r in csv.DictReader(open(S+'dft/aadf_leeds.csv')) if 2021<=int(r['year'])<=2025]
cps=collections.defaultdict(list)
for r in rows: cps[r['count_point_id']].append(r)
out=[]
for c in corr:
    segs=[(P(*g[i]),P(*g[i+1])) for g in c['geom'] for i in range(len(g)-1)]
    hits=[];near=[]
    for cid,rs in cps.items():
        r0=rs[0];p=P(float(r0['latitude']),float(r0['longitude']))
        d=min(segd(p,a,b) for a,b in segs)
        if c['ref'] and r0['road_name']==c['ref']:
            if d<60: hits.append((cid,rs))
            elif d<3000: near.append((d,cid,rs))
        elif r0['road_type']=='Minor' and (r0['road_name'] in ('U','C') or r0['road_name']==c['ref']) and d<25: hits.append((cid,rs))
    c['match']='on road'
    if not hits and near:
        d,cid,rs=min(near,key=lambda x:x[0]);hits=[(cid,rs)];c['match']=f'same road, {d/1000:.1f} km away'
    if not hits: c['aadf']=None;out.append(c);continue
    vals=[int(r['pedal_cycles']) for cid,rs in hits for r in rs]
    cnt=sum(r['estimation_method']=='Counted' for cid,rs in hits for r in rs)
    c['aadf']=round(sum(vals)/len(vals));c['cps']=len(hits);c['counted']=cnt;c['obs']=len(vals)
    c['cp_pts']=[[float(rs[0]['latitude']),float(rs[0]['longitude']),round(sum(int(r['pedal_cycles']) for r in rs)/len(rs)),cid] for cid,rs in hits]
    c['rate']=c['n']/(max(c['aadf'],1)*c['km']*365*5)*1e6   # collisions per million cycle-km
    c['srate']=c['score']/(max(c['aadf'],1)*c['km']*365*5)*1e6
    out.append(c)
for c in sorted([c for c in out if c.get('aadf') and c['n']>=5],key=lambda c:-c['rate']):
    print(f"{c.get('match','-')[:24]:24} {c['name'][:22]:22} {str(c['ref']):6} n={c['n']:3} ksi={c['ksi']:2} km={c['km']:5} aadf={c.get('aadf')} cps={c.get('cps')} counted={c.get('counted')}/{c.get('obs')} rate={c.get('rate',0):.1f}")
json.dump(out,open(S+'work/corr_risk.json','w'))
# merge into page data: top 10 by harm (with usage) and top 10 by risk per rider
d=json.load(open(S+'work/data.json'))
keep=('name','ref','km','n','fatal','serious','ksi','score','geom','pts','aadf','match','rate','counted','obs','cp_pts')
d['danger']=[{k:c.get(k) for k in keep} for c in out[:10]]
risk=sorted([c for c in out if c.get('aadf') and c['aadf']>=20 and c['n']>=5],key=lambda c:-c['rate'])[:10]
d['risk']=[{k:c.get(k) for k in keep} for c in risk]
for c in d['danger']+d['risk']:
    if c.get('rate'): c['rate']=round(c['rate'],1)
json.dump(d,open(S+'work/data.json','w'),separators=(',',':'))
