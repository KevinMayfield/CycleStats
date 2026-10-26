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
