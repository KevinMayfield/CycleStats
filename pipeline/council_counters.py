import csv,glob,collections,json,math
import os
HERE=os.path.dirname(os.path.abspath(__file__))
S=os.path.join(HERE,'..','raw')+'/'
sites={}
for r in list(csv.reader(open(S+'lcc/sites.csv',encoding='utf-8-sig')))[2:]:
    if len(r)>5 and r[0].strip(): sites[int(r[0])]=dict(desc=r[2].strip(),lat=float(r[4]),lon=float(r[5]))
def daily(files):
    vol=collections.defaultdict(collections.Counter);hrs=collections.defaultdict(collections.Counter);months=collections.defaultdict(set)
    for f in files:
        for r in csv.DictReader(open(f,encoding='utf-8-sig')):
            try: v=int(float(r['Volume']));c=int(r['Cosit'])
            except: continue
            if v<0: continue
            d=r['Sdate'][:10];vol[c][d]+=v;hrs[c][(d,r['LaneNumber'])]+=1
    res={}
    for c in vol:
        lanes=collections.defaultdict(dict)
        for (d,l),h in hrs[c].items(): lanes[d][l]=h
        full=[d for d,ls in lanes.items() if all(h>=24 for h in ls.values())]
        if full:
            ms=sorted({d[3:] for d in full},key=lambda m:(m[3:],m[:2]))
            res[c]=dict(days=len(full),avg=round(sum(vol[c][d] for d in full)/len(full)),months=len(ms),first=ms[0],last=ms[-1])
    return res
M=S+'lcc/months/'
have=sorted(f[:-4] for f in os.listdir(M) if f.endswith('.csv'))
recent=daily([M+m+'.csv' for m in have[-12:]])
old=daily([M+m+'.csv' for m in have if '2023-12'<=m<='2024-11'])
o22=daily([M+m+'.csv' for m in have if m=='2022-07'])
out=[]
for c,s in sites.items():
    r=recent.get(c) or old.get(c) or o22.get(c)
    if not r: continue
    s.update(id=c,**r);out.append(s)
for s in sorted(out,key=lambda s:-s['avg']): print(f"{s['avg']:5}/day {s['days']:3}d {s['months']:2}mo {s['first']}–{s['last']}  {s['desc']}")
json.dump(out,open(S+'work/lcc.json','w'))
# merge counters into page data and attach the busiest counter to each path / route
d=json.load(open(S+'work/data.json'))
K=math.cos(math.radians(53.8))*111320;KY=110574
P=lambda la,lo:((lo+1.55)*K,(la-53.8)*KY)
def mind(p,geoms):
    best=1e9
    for g in geoms:
        for i in range(len(g)-1):
            a,b=P(*g[i]),P(*g[i+1]);dx,dy=b[0]-a[0],b[1]-a[1];L=dx*dx+dy*dy
            t=0 if L==0 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L))
            best=min(best,math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy))
    return best
OFF={90810,90120,100217,170127}
NAME={90810:'Leeds–Liverpool Canal towpath, Armley Mills',90120:'Leeds–Liverpool Canal towpath, Kirkstall Forge',100217:'Wyke Beck Way, Wykebeck Woods',170127:'Castleford Greenway'}
mon=lambda m:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(m[:2])-1]+' '+m[3:]
cs=[]
for s in out:
    cs.append(dict(name=NAME.get(s['id'],s['desc']),kind='Off-road path' if s['id'] in OFF else 'Cycle track or lane on a road',avg=s['avg'],src='Leeds City Council automatic counter',
        period=f"{mon(s['first'])} – {mon(s['last'])}",days=s['days'],note='partial data' if s['days']<60 else '',lat=s['lat'],lon=s['lon'],id=s['id']))
# ELOR has no council counter: use the DfT one-day manual counts (2023)
cs.append(dict(name='ELOR cycle track (A6120, A64 to A58)',kind='Cycle track beside a road',avg=127,src='DfT count point 95049 (single manual count, 2023)',period='2023',days=1,note='one-day count',lat=53.84017,lon=-1.44663,id='DfT95049'))
cs.append(dict(name='ELOR cycle track (A6120, M1 J46 to A64)',kind='Cycle track beside a road',avg=151,src='DfT count point 95047 (single manual count, 2023)',period='2023',days=1,note='one-day count',lat=53.80379,lon=-1.41964,id='DfT95047'))
cs.sort(key=lambda c:-c['avg'])
d['counts']=cs
for k in ('paths','routes'):
    for r in d[k]:
        hits=[c for c in cs if mind(P(c['lat'],c['lon']),r['geom'])<60]
        r['counters']=[[c['name'],c['avg'],c['period'],c['src'].startswith('DfT')] for c in hits]
json.dump(d,open(S+'work/data.json','w'),separators=(',',':'))
