# CycleStats: Cycling Top 10s

**[What the data says](FINDINGS.md)**: a summary of the findings and the Danelaw Cycle Network.

An interactive map of cycling across all of Yorkshire (West, South, East and North, plus Middlesbrough and Redcar), Lincolnshire, Nottinghamshire, Derbyshire and Leicestershire: fifteen areas, with an area picker, several views for each and a neighbourhood layer for deprivation, housing condition and car ownership, plus a [summary page](https://kevinmayfield.github.io/CycleStats/summary.html) that ranks across every area:

| Area | Boundary |
|---|---|
| **Leeds** | City of Leeds district |
| **Sheffield** | City of Sheffield |
| **Kirklees & Calderdale** | Kirklees (Huddersfield) and Calderdale (Halifax) |
| **Bradford** | City of Bradford district |
| **Wakefield** | Wakefield district |
| **Doncaster & Barnsley** | Doncaster and Barnsley districts |
| **Rotherham** | Rotherham district |
| **Hull & East Riding** | Kingston upon Hull and the East Riding of Yorkshire (Hull, Beverley, Bridlington, Goole) |
| **Lincolnshire** | Lincolnshire county, North Lincolnshire and North East Lincolnshire (Lincoln, Boston, Grantham, Skegness, Grimsby, Immingham, Scunthorpe) |
| **Nottingham & Nottinghamshire** | Nottingham city and Nottinghamshire county (Mansfield, Worksop, Newark, Hucknall, Beeston, West Bridgford) |
| **Derby & Derbyshire** | Derby city and Derbyshire county (Chesterfield, Buxton, Matlock, Ilkeston, Long Eaton) |
| **Leicester & Leicestershire** | Leicester city and Leicestershire county (Loughborough, Hinckley, Coalville, Melton Mowbray, Market Harborough) |
| **Rutland** | Rutland county (Oakham, Uppingham, Rutland Water) |
| **York & North Yorkshire** | City of York and the North Yorkshire council area (York, Harrogate, Scarborough, Selby, Skipton, Northallerton, Richmond, Whitby) |
| **Middlesbrough & Redcar** | Middlesbrough and Redcar & Cleveland |

| Tab | What it ranks | Source |
|---|---|---|
| **Routes & paths** | The 10 longest signed cycle routes and the 10 longest dedicated cycle paths (cycleways and bike-designated paths), measured inside the area, plus the suggested Danelaw Cycle Network routes that cross it (dashed; `danelaw_lines.py` writes their outlines to `data/danelaw-lines.json`) | OpenStreetMap, Danelaw Cycle Network |
| **Safety** | Where cyclists are hurt and safer alternatives, on one map: the most dangerous roads (the 10 with the most cycle collisions, weighted fatal ×10, serious ×3, slight ×1, merged with the 10 with the most collisions per million km cycled), the roads with 150+ bikes a day and the fewest collisions per km cycled, cycle paths, and every collision | DfT STATS19 2021–2025 + DfT traffic counts + OpenStreetMap |
| **Bike counts** | Leeds: every council automatic counter, including off-road paths. Other areas: the busiest DfT count points | Leeds City Council / DfT |
| **Towns & health** | The area's flat and gently sloping towns, sortable by how many more people would cycle at Hull and York levels or by health gain (health need × room for cycling to grow), with Hull and York as the benchmark; each town links to its roads to improve on `towns.html` | `data/towns.json`, `data/health.json` |

The **Neighbourhoods** layer shades each LSOA (about 1,500 residents) by its English Indices of Deprivation 2025 decile, its Indoors sub-domain decile (housing in poor condition) or the share of households with no car (Census 2021). The Safety tab says what share of cycle collisions happened in the most deprived fifth of neighbourhoods, and each listed road shows the deprivation decile where it runs.

**Live site:** https://kevinmayfield.github.io/CycleStats/ opens on an overview map (`index.html`): every area, its towns shaded by hilliness and the Danelaw Cycle Network routes. Click an area for its map, a flat or gently sloping town for where to build there (`towns.html#<town code>`), or a route for the Danelaw page. The area maps are `area.html`; link to an area with `?area=` and its id from `pipeline/areas.json`, for example `area.html?area=bradford`. Old `index.html?area=` links forward to `area.html`.

It is a static web app: `area.html` loads Leaflet from cdnjs, `data/areas.json` for the area list and `data/<area>.json` for the chosen area. It draws its own basemap (boundary, main roads, rivers, place names), so it needs no map tile service.

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

- `stats19_lad`: the ONS codes used in STATS19, either district codes or a county's highway authority code (leave empty for a `bbox` area; collisions are then picked by location)
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
| 6 | `deprivation.py` | Writes `data/<area>-imd.json` (LSOA outlines with IMD, housing condition and no-car figures), counts cycle collisions by deprivation decile using the LSOA in each STATS19 record, and tags each listed road with the decile at its midpoint |
| 7 | `priorities.py` | For every stretch with collisions or a DfT count: harm, share protected (a dedicated cycle track beside the road, `foot=no`, or lanes physically separated by bollards, kerbs or wands) or partial (painted lane, or a pavement shared with walkers or split by a painted line, credited as a quarter of a track), speed limit, PCT commuters and pupils now and Go Dutch, and the share of cyclist casualties who were women or children |

`area.py` holds the shared settings and geometry each step uses. After every area is built, `summary.py` writes `data/priorities.json` for `priorities.html` (Where to build: top 10 corridors for safety, for more cycling, and for both, scored as described on the page) and `data/summary.json` for `summary.html`. `towns.py` writes `data/towns.json` for `towns.html` (Where Dutch infrastructure should work?: every ONS built-up area compared on PCT route gradient and Census 2021 cycling to work, against Hull and York and against a fitted curve (share cycling = a·e^(b·gradient), weighted by commuters, which halves roughly every 1.5 points of gradient), with up to eight roads to improve per town (each town opens to a table of its roads and an OpenStreetMap street map with them numbered): road stretches from `priorities.py` placed in the town most of their length runs through, skipping those 80%+ protected, ranked half on unprotected harm and half on Go Dutch potential; an overview map of every town's ONS built-up area outline shaded by hilliness; and networks: flat and gently sloping towns whose built-up edges come within 250 m of each other, such as Beeston, Stapleford, Sandiacre and Long Eaton across the Nottinghamshire–Derbyshire line; and for each town and network, the share of households with no car, the share of neighbourhoods in England's most deprived fifth, and cycle collisions a year per 100 cycle commuters against the same figure for England and Wales (a comparison between places, not a cyclist's risk: it counts all cycling against commuters only), with the shares killed or seriously injured and on 40 mph+ roads). summary.json holds: the 10 busiest counts, most collisions, highest risk per rider, and safe & busy roads (150+ bikes a day) across all areas, each labelled with its nearest suburb and town.

`health.py` writes `data/health.json` for `health.html`, **Health and active travel**: for every town, a health need index (physically inactive adults, adults overweight or obese and diagnosed diabetes by council from OHID Fingertips; Year 6 child obesity by MSOA; the share of LSOAs in England's most health-deprived fifth from IMD 2025; each as a ratio to England, capped at 200, then averaged), set against cycling to work and the Go Dutch potential. The league ranks flat and gently sloping towns by need ÷ 100 × (Go Dutch − today), with the Propensity to Cycle Tool's own estimates of deaths avoided and health value (WHO HEAT, commuting only). It also sums the Propensity to Cycle Tool's health estimates (today's value, and the extra under Go Dutch and e-bikes: deaths and sick days avoided and their value) over each NHS integrated care board, matching councils to boards on 2011 names; these are WHO HEAT values to society, not NHS treatment-cost savings. For road danger it counts cyclist casualties by severity where the collision happened (STATS19 2021–25, with each collision's council from the national collision file, cached as `raw/health/cycle_collision_lad.csv`) against Census 2021 cycle commuters, and works out the casualties avoided at the lowest board's rate and the cut in risk per rider needed for casualties not to rise at Go Dutch. Downloads are cached in `raw/health/`.

`danelaw.py` writes `data/danelaw.json` for `danelaw.html`, the **Danelaw Cycle Network**. Its spine, the Danelaw Way, is a direct long-distance route from Repton to Stamford Bridge along the Trent (via Derby, Long Eaton, Newark, Torksey and Gainsborough), across to Howden and up the Ouse to York and Stamford Bridge, with the Lindsey Ridings loop (Fossdyke, Lincoln, Market Rasen, Caistor, Grimsby, the Humber bank, Alkborough, Scunthorpe, back to the Trent at Gainsborough), a Soar variant from Leicester, an Aire variant from Leeds on to Hull by Howden and the Humber bank, a Don variant from Sheffield by Rotherham and Doncaster to Goole, a Humber Bridge link from Barton to Hessle (with the Aire variant, Barton to Hull), a Tadcaster route from Leeds direct to York, a Beverley route from Hull direct to York (Hudson Way, Pocklington), a Great North Road route from Stamford to Middlesbrough (the A1 by Grantham, Newark, Retford and Doncaster, the A19 to Selby, then from York by Thirsk and Northallerton; shortest profile), Roman sites alongside the Danelaw ones, Wolds (Pocklington to Driffield) and Bridlington (Beverley, Driffield, Bridlington) routes that make up York–Bridlington and Hull–Bridlington rides, the Boroughs of Leicester and Stamford plus Holland (Leicester by Rutland Water, Stamford, the Welland and the Wash to Wainfleet), Lindsey South and North Riding Coastal (Wainfleet by Skegness, Mablethorpe, Saltfleet and Cleethorpes to Barton-upon-Humber), and a Skegness route from Newark by Lincoln, the Witham (Water Rail Way) and Woodhall Spa. The line follows each river centreline (shortest path along the mapped waterway) or the line of Ermine Street, with short links routed by BRouter's safety profile, so it does not wander between villages. Every 25 m is then checked against OpenStreetMap within reach of the line: a traffic-free path you can cycle, a quiet road, only a footpath or a path beside a busy road (upgrade), or nothing usable (build). Downloads are cached in `raw/danelaw/`. Predicted cycling comes from the Propensity to Cycle Tool route networks already downloaded for each area (`raw/pct/`): every 25 m sample takes the commuting and school flows (Census 2011 and Go Dutch) of the nearest PCT road running the same way within 150 m, so a path beside a road or a towpath gets that road's flow; values are smoothed over 500 m stretches. The "Build these first" ranking orders stages by the people who commute between the towns they link (Census 2021 home-to-work flows by MSOA, `raw/od/ODWP01EW_MSOA.csv`, downloaded by hand from Nomis; MSOAs are matched to towns through their LSOAs; pairs within 15 km, credited to every stage the route runs along between them), flat routes (under 3 m of climbing a km) first, with the Go Dutch prediction alongside. The town-pair counts are cached in `raw/danelaw/od_pairs.json`. PCT has no leisure trips, so destination rides are undervalued.

## Method notes and limits

- **Collisions** are police-reported injury collisions involving a pedal cycle (STATS19). Incidents on off-road paths and unreported incidents are not included, so off-road paths have usage figures (Leeds only) but no safety rating.
- **Risk per rider** = collisions ÷ (bikes per day × stretch length × 365 × 5 years) × 1,000,000. Only roads with 5+ collisions and a DfT cycle count are ranked.
- **DfT bike counts** on most roads come from a single-day manual count, often carried forward from an earlier year. They undercount weekend and leisure riding. Where a road has no count point on it, the nearest count point on the same road number within 3 km is used, and the page says so.
- **Leeds council counters** are averaged over complete days in the latest 12 months. Counters that have stopped reporting use their last full year (Kirkstall Forge towpath and Meanwood path: Dec 2023 – Nov 2024; Wykebeck Woods: July 2022 only). Some counters record one direction of a one-way lane. Leeds is the only area here with open automatic counter data.
- **ELOR** (Leeds) has no council counter. Its figures are two DfT one-day counts from 2023 and are likely to understate use.
- **Nottingham & Nottinghamshire**, **Derby & Derbyshire** and **Leicester & Leicestershire** each combine a city (unitary) council with its county, so their DfT count points come from both highway authorities.
- **North Yorkshire** became one council in 2023; collisions recorded under the former county and district codes are included.
- **Sheffield** and **Barnsley** changed ONS code in 2023 (E08000019 → E08000039, E08000016 → E08000038); collisions under both codes are included.
- **Deprivation** deciles are national: decile 1 is the most deprived 10% of neighbourhoods in England. A collision's neighbourhood says where it happened, not where the cyclist lives.
- Collision and casualty numbers are small on many roads, so the rankings can shift a lot with one or two incidents.

## Data licences

- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open Database Licence (ODbL).
- [DfT road safety data (STATS19)](https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-accidents-safety-data) and [DfT road traffic statistics](https://roadtraffic.dft.gov.uk/), Open Government Licence v3.0.
- [English Indices of Deprivation 2025](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025), MHCLG; [Census 2021 TS045 car or van availability](https://www.nomisweb.co.uk/); [LSOA 2021 boundaries](https://geoportal.statistics.gov.uk/), ONS. All Open Government Licence v3.0; boundaries contain OS data © Crown copyright and database right.
- [Propensity to Cycle Tool](https://www.pct.bike/) route networks (commute and school, Go Dutch and gender-equality scenarios), npct/pct-outputs-regional-notR, Open Government Licence / CC BY 4.0.
- [Census 2021 TS061 method of travel to work](https://www.nomisweb.co.uk/), [LSOA (2021) to built-up area (2022) lookup](https://geoportal.statistics.gov.uk/) and [built-up area (2022) boundaries](https://geoportal.statistics.gov.uk/), ONS, Open Government Licence v3.0.
- [Leeds Annual Cycle Growth](https://datamillnorth.org/dataset/e1dmk), Leeds City Council via Data Mill North, Open Government Licence v3.0.
