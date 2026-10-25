# CycleStats: Leeds Cycling Top 10s

An interactive map of cycling in the City of Leeds district, with six views:

| Tab | What it ranks | Source |
|---|---|---|
| **Routes** | The 10 longest signed cycle routes, measured inside the Leeds boundary | OpenStreetMap |
| **Paths** | The 10 longest dedicated cycle paths (cycleways and bike-designated paths) | OpenStreetMap |
| **Collisions** | The 10 named roads with the most cycle collisions, weighted fatal ×10, serious ×3, slight ×1 | DfT STATS19, 2021–2025 |
| **Risk/rider** | Collisions per million km cycled, using bikes per day × road length | STATS19 + DfT traffic counts |
| **Safe & busy** | Roads with 150+ bikes a day and the fewest collisions per km cycled | STATS19 + DfT traffic counts |
| **Bike counts** | Average bikes per day at every council counter, including off-road paths | Leeds City Council + DfT |

**Live site:** https://kevinmayfield.github.io/CycleStats/

It is a static web app: `index.html` loads Leaflet from cdnjs and the prepared data from `data/leeds-cycling.json`. It draws its own basemap (boundary, main roads, rivers, place names), so it needs no map tile service.

## Rebuilding the data

Requires Python 3.8+ (standard library only) and about 1 GB of free disk for the downloads.

```bash
pipeline/run_all.sh
```

This downloads everything into `raw/` (git-ignored), runs the pipeline and writes `data/leeds-cycling.json`. Use `pipeline/run_all.sh --skip-fetch` to re-run the analysis on data you already have.

| Step | Script | Does |
|---|---|---|
| 1 | `fetch_data.py` | Overpass queries for Leeds (E08000035); streams the national STATS19 files and keeps only Leeds collisions and bicycle vehicles/casualties; downloads DfT AADF for local authority 63; downloads the latest 12 months of council counter data from Data Mill North |
| 2 | `build_osm.py` | Clips routes and paths to the Leeds boundary, joins path segments by name, snaps each cycle collision to the nearest named road within 40 m and groups roads into connected stretches |
| 3 | `dft_usage.py` | Matches DfT count points to the dangerous roads and works out collisions per million km cycled |
| 4 | `safe_busy.py` | Same calculation for every road that has a DfT count, then ranks the well-used ones by lowest rate |
| 5 | `council_counters.py` | Averages each council counter over complete days and attaches the busiest counter to each path and route |

## Method notes and limits

- **Collisions** are police-reported injury collisions involving a pedal cycle (STATS19). Incidents on off-road paths and unreported incidents are not included, so off-road paths have usage figures but no safety rating.
- **Risk per rider** = collisions ÷ (bikes per day × stretch length × 365 × 5 years) × 1,000,000. Only roads with 5+ collisions and a DfT cycle count are ranked.
- **DfT bike counts** on most roads come from a single-day manual count, often carried forward from an earlier year. They undercount weekend and leisure riding. Where a road has no count point on it, the nearest count point on the same road number within 3 km is used, and the page says so.
- **Council counters** are averaged over complete days in the latest 12 months. Counters that have stopped reporting use their last full year (Kirkstall Forge towpath and Meanwood path: Dec 2023 – Nov 2024; Wykebeck Woods: July 2022 only). Some counters record one direction of a one-way lane.
- **ELOR** has no council counter. Its figures are two DfT one-day counts from 2023 and are likely to understate use.
- Collision and casualty numbers are small on many roads, so the rankings can shift a lot with one or two incidents.

## Data licences

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open Database Licence (ODbL).
- [DfT road safety data (STATS19)](https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-accidents-safety-data) and [DfT road traffic statistics](https://roadtraffic.dft.gov.uk/), Open Government Licence v3.0.
- [Leeds Annual Cycle Growth](https://datamillnorth.org/dataset/e1dmk), Leeds City Council via Data Mill North, Open Government Licence v3.0.
