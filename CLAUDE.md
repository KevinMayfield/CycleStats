# CycleStats notes

Working notes for this repo. The README covers the pipeline, sources and method; this file keeps findings and context
worth coming back to.

## Working here

- Data is rebuilt with `pipeline/run_all.sh` (see README). Downloads land in `raw/` (git-ignored).
- On Kevin's Mac the default `python3` (python.org 3.10) fails HTTPS certificate checks, so downloads fail. Run
  `fetch_data.py` with `/opt/homebrew/bin/python3`. The analysis steps need no network and run on any Python 3.8+.
- `towns.py` writes `data/towns.json` for `towns.html`. Town figures include `nocar` (% households with no car,
  Census 2021, averaged over LSOAs weighted by people travelling to work) and `deprived` (% of LSOAs in England's most
  deprived fifth, IMD 2025).

## Open question: car ownership and cycling (26 Oct 2026, not yet on the page)

Is there a paradox between low car ownership or deprivation and low cycling? Partly. Across the 92 flat and gently
sloping towns, leaving out Hull and York, towns with fewer cars cycle only slightly more, and every group reaches about
a seventh of its Go Dutch level:

| Households with no car | Towns | Cycle to work now | Go Dutch | Share of Go Dutch reached | Neighbourhoods deprived |
|---|---|---|---|---|---|
| Under 20% | 48 | 3.1% | 21.7% | 14% | 5% |
| 20–25% | 21 | 3.6% | 23.4% | 15% | 21% |
| 25–30% | 13 | 4.1% | 26.2% | 16% | 40% |
| 30% or more | 10 | 4.2% | 29.0% | 14% | 51% |

- Correlation with cycling to work among flat towns: no car 0.32 (weak), deprivation 0.06 (none); route gradient −0.36.
- Go Dutch potential is highest where cars are scarcest, but the gap to it is the same everywhere.
- Strongest cases, all flat: Middlesbrough (31% no car, 2.4% cycle), Bentley, Doncaster (35%, 2.9%), Eston (30%, 1.7%).
- Counter-examples: Hull (33% no car, 51% of neighbourhoods deprived, 8.0% cycle), York (28%, 12.5%), Goole (30%, 10.8%),
  Newark-on-Trent (27%, 8.3%).

Possible explanations, not tested: people without a car walk or take the bus, and cycling only takes off where it
feels safe; deprived neighbourhoods often sit beside busy main roads; owning a bike and somewhere secure to keep it is
itself a barrier.

Limits: the Census measures travel to work only, and households without a car are less likely to have someone in work.
These are town averages, so they cannot show whether the people who cycle are the ones without a car.

Next steps if revisited: compare LSOAs within towns (cycling share against no-car share and IMD decile) rather than
town averages; add the band table to `towns.html`.

## How far people travel to work (26 Oct 2026, not in the pipeline)

Census 2021 TS058 (distance to work by LSOA, Nomis NM_2075_1) was downloaded by hand to `raw/imd/ttwdist2021.csv`,
and the Census 2021 home-to-work flow tables by MSOA to `raw/od/` (ODWP01EW all, ODWP09EW by social grade, ODWP14EW
by car or van availability, from nomisweb.co.uk/sources/census_2021_od). Commuters exclude people working mainly from home.

- Across the flat and gently sloping towns, deprived and car-less neighbourhoods have shorter commutes: 58% under
  5 km in IMD deciles 1–2 against 42% in deciles 8–10; 61% where 40%+ of households have no car against 42% under 15%.
- Long Eaton is the exception: about half of commuters in every group travel 5–20 km (deprived 47%, least deprived
  54%), against 29% in Middlesbrough's deprived neighbourhoods and 32% in Hull's. Only 44% of its deprived
  neighbourhoods' commuters work within 5 km.
- Long Eaton (Erewash MSOAs 010, 011, 012, 014, 015) to Castle Donington (North West Leicestershire 001, which takes in
  East Midlands Airport and the logistics parks, about 9–10 km): 8.3% of DE (semi-skilled and unskilled) workers, the
  third biggest destination for that group, against 1.6% of AB workers. 7.7% of workers from households with no car go
  there, against 3.3% with two cars. That backs up the earlier point: lower-paid work for Long Eaton is 5–6 miles away in
  Castle Donington, and the people doing it are the least likely to have a car.

Next steps if revisited: add TS058 to `fetch_data.py` and per-town distance bands to `towns.py`; map the main
destinations of each flat town's lower social grade workers; check whether a protected route exists from Long Eaton
to Castle Donington (Trent crossing at Sawley, A6/A50).
