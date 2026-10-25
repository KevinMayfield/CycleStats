import csv,sys
col,val=sys.argv[1],sys.argv[2].split(',')
r=csv.reader(sys.stdin);h=next(r);i=h.index(col);w=csv.writer(sys.stdout);w.writerow(h)
for row in r:
    if row[i] in val: w.writerow(row)
