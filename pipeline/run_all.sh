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
  python3 priorities.py "$a"                   # harm, protection, PCT potential per stretch for Where to build
  cp "../raw/$a/work/data.json" "../data/$a.json"
  echo "   wrote data/$a.json ($(du -h "../data/$a.json" | cut -f1))"
done
python3 summary.py > /dev/null && echo "   wrote data/summary.json and data/priorities.json"
python3 towns.py > /dev/null && echo "   wrote data/towns.json"
python3 danelaw.py > /dev/null && echo "   wrote data/danelaw.json"   # routes once with BRouter, then uses raw/danelaw/
python3 danelaw_lines.py > /dev/null && echo "   wrote data/danelaw-lines.json"   # compact lines for the area maps
python3 health.py > /dev/null && echo "   wrote data/health.json"     # downloads Fingertips and Census health data to raw/health/
python3 heritage.py > /dev/null && echo "   wrote data/heritage.json"   # downloads ONS built-up area names to raw/heritage/
python3 industry.py > /dev/null && echo "   wrote data/industry.json"   # needs heritage.json; downloads Census tables and ONS COVID-19 deaths to raw/industry/ (first run needs openpyxl)
python3 people.py > /dev/null && echo "   wrote data/people.json"   # needs heritage.json and industry.json; asks the ONS API, cached in raw/people/ (first run needs a Python that can reach it over HTTPS)
python3 predict.py > /dev/null && echo "   wrote data/predict.json"   # needs industry, people and towns json; rain days from Open-Meteo, cached in raw/rain/ (the free service limits requests an hour, so a first run can take a while)
# index of areas for the app's area picker
python3 -c "import json,os;a=json.load(open('areas.json'));json.dump([{'id':k,'name':v['name']} for k,v in a.items() if os.path.exists('../data/'+k+'.json')],open('../data/areas.json','w'),indent=1)"
