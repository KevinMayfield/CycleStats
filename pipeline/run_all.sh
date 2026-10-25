#!/usr/bin/env bash
# Rebuild data/leeds-cycling.json from scratch. Pass --skip-fetch to reuse what is already in raw/.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ../raw/work
if [[ "${1:-}" != "--skip-fetch" ]]; then python3 fetch_data.py; fi
python3 build_osm.py        # routes, paths, collisions snapped to roads, map context
python3 dft_usage.py        # bikes/day on the dangerous roads, risk per rider
python3 safe_busy.py        # safe and well-used roads
python3 council_counters.py # Leeds City Council counters, incl. off-road paths
cp ../raw/work/data.json ../data/leeds-cycling.json
echo "Wrote data/leeds-cycling.json ($(du -h ../data/leeds-cycling.json | cut -f1))"
