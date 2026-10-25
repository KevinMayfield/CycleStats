# CycleStats: Cycling Top 10s

An interactive map of cycling in ten areas, with an area picker and six views for each, plus a [summary page](https://kevinmayfield.github.io/CycleStats/summary.html) that ranks across every area:

| Area | Boundary |
|---|---|
| **Leeds** | City of Leeds district |
| **Nottingham/Derby Corridor** | A rectangle covering Derby, Nottingham and the land between, from Hucknall in the north to Castle Donington in the south (52.82–53.06° N, 1.57–1.06° W) |
| **Sheffield** | City of Sheffield |
| **Hull** | Kingston upon Hull |
| **York** | City of York |
| **Grimsby, Immingham & Scunthorpe** | North East Lincolnshire and North Lincolnshire |
| **Kirklees & Calderdale** | Kirklees (Huddersfield) and Calderdale (Halifax) |
| **Bradford** | City of Bradford district |
| **Wakefield** | Wakefield district |
| **Doncaster & Barnsley** | Doncaster and Barnsley districts |

| Tab | What it ranks | Source |
|---|---|---|
| **Routes** | The 10 longest signed cycle routes, measured inside the area | OpenStreetMap |
| **Paths** | The 10 longest dedicated cycle paths (cycleways and bike-designated paths) | OpenStreetMap |
| **Collisions** | The 10 named roads with the most cycle collisions, weighted fatal ×10, serious ×3, slight ×1 | DfT STATS19, 2021–2025 |
| **Risk/rider** | Collisions per million km cycled, using bikes per day × road length | STATS19 + DfT traffic counts |
| **Safe & busy** | Roads with 150+ bikes a day and the fewest collisions per km cycled | STATS19 + DfT traffic counts |
| **Bike counts** | Leeds: every council automatic counter, including off-road paths. Other areas: the busiest DfT count points | Leeds City Council / DfT |

**Live site:** https://kevinmayfield.github.io/CycleStats/ (link to an area with `?area=` and its id from `pipeline/areas.json`, for example `?area=bradford`)

It is a static web app: `index.html` loads Leaflet from cdnjs, `data/areas.json` for the area list and `data/<area>.json` for the chosen area. It draws its own basemap (boundary, main roads, rivers, place names), so it needs no map tile service.

## Rebuilding the data

Requires Python 3.8+ (standard library only) and about 1 GB of free disk for the downloads.

```bash
pipeline/run_all.sh                 # every area
pipeline/run_all.sh york hull       # just these areas
pipeline/run_all.sh --keep          # only download files that are missing (after a failed run)
pipeline/run_all.sh --skip-fetch    # re-run the analysis on what is already in raw/
```

Downloads go into `raw/` (git-ignored) and each area is written to `data/<area>.json`.

### Adding an area

Add an entry to `pipeline/areas.json`, then run `pipeline/run_all.sh <id>`. An area is either one or more council areas, set with `gss` (an ONS code as tagged `ref:gss` in OpenStreetMap, or a list of them), or a rectangle, set with `bbox` (`[south, west, north, east]`). Also set:

- `stats19_lad`: the ONS district codes used in STATS19 (leave empty for a `bbox` area; collisions are then picked by location)
- `dft_la`: the DfT road traffic local authority ids of the highway authorities that cover the area ([list](https://roadtraffic.dft.gov.uk/api/local-authorities))
- `centre`, `rivers`, `places` and the labels shown on the page

### Pipeline steps

| Step | Script | Does |
|---|---|---|
| 1 | `fetch_data.py` | Overpass queries per area; streams the national STATS19 files once and keeps collisions for every area plus all bicycle vehicles and casualties; downloads DfT AADF per highway authority; downloads Leeds council counter data from Data Mill North |
| 2 | `build_osm.py` | Clips routes and paths to the area, joins path segments by name, snaps each cycle collision to the nearest named road within 40 m and groups roads into connected stretches |
| 3 | `dft_usage.py` | Matches DfT count points to the high-collision roads and works out collisions per million km cycled |
| 4 | `safe_busy.py` | Same calculation for every road that has a DfT count, then ranks the well-used ones by lowest rate |
| 5 | `council_counters.py` | Leeds: averages each council counter over complete days. Other areas: lists the busiest DfT count points. Then attaches the busiest count to each path and route |

`area.py` holds the shared settings and geometry each step uses. After every area is built, `summary.py` writes `data/summary.json` for `summary.html`: the 10 busiest counts, most collisions, highest risk per rider, and safe & busy roads (150+ bikes a day) across all areas, each labelled with its nearest suburb and town.

## Method notes and limits

- **Collisions** are police-reported injury collisions involving a pedal cycle (STATS19). Incidents on off-road paths and unreported incidents are not included, so off-road paths have usage figures (Leeds only) but no safety rating.
- **Risk per rider** = collisions ÷ (bikes per day × stretch length × 365 × 5 years) × 1,000,000. Only roads with 5+ collisions and a DfT cycle count are ranked.
- **DfT bike counts** on most roads come from a single-day manual count, often carried forward from an earlier year. They undercount weekend and leisure riding. Where a road has no count point on it, the nearest count point on the same road number within 3 km is used, and the page says so.
- **Leeds council counters** are averaged over complete days in the latest 12 months. Counters that have stopped reporting use their last full year (Kirkstall Forge towpath and Meanwood path: Dec 2023 – Nov 2024; Wykebeck Woods: July 2022 only). Some counters record one direction of a one-way lane. Leeds is the only area here with open automatic counter data.
- **ELOR** (Leeds) has no council counter. Its figures are two DfT one-day counts from 2023 and are likely to understate use.
- **Nottingham/Derby Corridor** spans five highway authorities (Nottingham, Nottinghamshire, Derby, Derbyshire, Leicestershire), so its DfT count points come from all five.
- **Sheffield** and **Barnsley** changed ONS code in 2023 (E08000019 → E08000039, E08000016 → E08000038); collisions under both codes are included.
- Collision and casualty numbers are small on many roads, so the rankings can shift a lot with one or two incidents.

## Data licences

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open Database Licence (ODbL).
- [DfT road safety data (STATS19)](https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-accidents-safety-data) and [DfT road traffic statistics](https://roadtraffic.dft.gov.uk/), Open Government Licence v3.0.
- [Leeds Annual Cycle Growth](https://datamillnorth.org/dataset/e1dmk), Leeds City Council via Data Mill North, Open Government Licence v3.0.
