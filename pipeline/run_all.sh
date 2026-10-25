#!/usr/bin/env bash
# Rebuild data/<area>.json for every area in areas.json (or just the areas named).
#   pipeline/run_all.sh [area ...] [--skip-fetch] [--keep]
# --skip-fetch reuses raw/ as it is; --keep only downloads files that are missing.
set -euo pipefail
cd "$(dirname "$0")"
args=(); fetch=1; keep=""
for a in "$@"; do case $a in --skip-fetch) fetch=0;; --keep) keep=--keep;; *) args+=("$a");; esac; done
[[ ${#args[@]} -eq 0 ]] && args=($(python3 -c "import json;print(' '.join(json.load(open('areas.json'))))"))
[[ $fetch -eq 1 ]] && python3 fetch_data.py "${args[@]}" $keep
for a in "${args[@]}"; do
  echo "== $a"
  python3 build_osm.py "$a" > /dev/null        # routes, paths, collisions snapped to roads, map context
  python3 dft_usage.py "$a" > /dev/null        # bikes/day on the dangerous roads, risk per rider
  python3 safe_busy.py "$a" > /dev/null        # safe and well-used roads
  python3 council_counters.py "$a" > /dev/null # bike counts tab
  python3 deprivation.py "$a"                  # neighbourhood layer, collisions by deprivation
  cp "../raw/$a/work/data.json" "../data/$a.json"
  echo "   wrote data/$a.json ($(du -h "../data/$a.json" | cut -f1))"
done
python3 summary.py > /dev/null && echo "   wrote data/summary.json"
# index of areas for the app's area picker
python3 -c "import json,os;a=json.load(open('areas.json'));json.dump([{'id':k,'name':v['name']} for k,v in a.items() if os.path.exists('../data/'+k+'.json')],open('../data/areas.json','w'),indent=1)"
