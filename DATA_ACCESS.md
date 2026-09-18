# Data Access

This document tells a researcher exactly what data this repository
does and does not provide, and how to obtain what's missing to
reproduce the full analysis. See also `THIRD_PARTY_DATA_LICENSES.md`
for licensing terms and `docs/DATA_SOURCES.md` for a narrative account
of every source, including validation notes.

**This repository does not redistribute DHS/PDHS microdata under any
circumstance.** If you want the real, survey-derived mortality
estimates rather than the deprivation-index proxy, you must obtain
your own authorized copy directly from The DHS Program.

## DHS / PDHS 2017-18 — required for real mortality estimates

| | |
|---|---|
| Source | The DHS Program (https://dhsprogram.com) |
| Survey | Pakistan Demographic and Health Survey 2017-18 |
| Access route | Register a DHS account and a research project at https://dhsprogram.com/data/dataset_admin/index.cfm, request the Pakistan PDHS 2017-18 datasets below |
| Authorization requirement | Your registered project's stated purpose must cover this kind of analysis (subnational mortality small-area estimation). If it doesn't, register a new project first — using data outside your approved purpose is a terms-of-use violation regardless of what this repository's code does. |
| Committed to GitHub? | **No** — `data/raw/dhs/` is `.gitignore`d |

| Expected file | DHS dataset name | Local path | Required for |
|---|---|---|---|
| Births Recode (BR) | PKBR71DT | `data/raw/dhs/2017-18_DHS_GPS/PKBR71DT/PKBR71FL.DTA` | Direct U5MR estimation, hierarchical hazard model |
| Household Recode (HR) | PKHR71DT | `data/raw/dhs/2017-18_DHS_GPS/PKHR71DT/PKHR71FL.DTA` | Wealth index, water/sanitation indicators |
| Individual/Women's Recode (IR) | PKIR71DT | `data/raw/dhs/2017-18_DHS_GPS/PKIR71DT/PKIR71FL.DTA` | Maternal education, ANC coverage |
| Children's Recode (KR) | PKKR71FL | `data/raw/dhs/2017-18_DHS_GPS/PKKR71FL/PKKR71FL.DTA` | Vaccination coverage validation axis |
| GPS/Geographic Data (GE) | PKGE71FL | `data/raw/dhs/2017-18_DHS_GPS/PKGE71FL/PKGE71FL.shp` (+ .shx/.dbf/.prj) | Cluster → district spatial join (all of the above depend on this) |

**After downloading:** place each file at its documented path, then
run `bash scripts/run_pipeline.sh` (without `--no-dhs`). See
`REPRODUCIBILITY.md` for the full step-by-step.

**Terms:** https://dhsprogram.com/Data/terms-of-use.cfm — binding on
you directly, independent of anything in this repository. In
particular, per DHS's own terms: no attempt to identify individual
respondents or their exact location, no redistribution of microdata,
and (per DHS's request) a copy of any resulting publication should be
sent to references@dhsprogram.com.

## Pakistan Bureau of Statistics — 2017 Census

| | |
|---|---|
| Source | https://www.pbs.gov.pk/content/district-wise-results-tables-census-2017, via `cerp-analytics/pbs2017` |
| Access route | Automatically fetched by `scripts/run_pipeline.sh` (`git clone https://github.com/cerp-analytics/pbs2017`) |
| Authorization requirement | None — public statistics |
| Committed to GitHub? | No (fetched at pipeline run time to `data/raw/pbs2017-main/`), but the code that fetches it is committed |
| Required for | District demographics, geography, WASH/literacy proxies |

## District boundary shapefile

Bundled in the same `pbs2017-main` fetch above
(`data/raw/pbs2017-main/data/00_shapefiles/District_Boundary.shp`).
Original source: OCHA Pakistan admin boundaries via HDX — see
`THIRD_PARTY_DATA_LICENSES.md` for the licensing caveat on this
specific bundle.

## IHME Global Burden of Disease 2023

| | |
|---|---|
| Source | https://vizhub.healthdata.org/gbd-results/ (requires a free IHME account) |
| Access route | Manual download via the GBD Results Tool — not fetchable automatically by this pipeline |
| Committed to GitHub? | **Yes** — `data/external/gbd/*.csv` (aggregate, province-level, non-identifying) |
| Required for | External validation/benchmarking of the hierarchical model (not required to run the core pipeline) |

## Health facility locations (OpenStreetMap via HOTOSM)

| | |
|---|---|
| Source | https://data.humdata.org/dataset/hotosm_pak_health_facilities |
| Access route | Public download, no authorization needed |
| Committed to GitHub? | Yes — `data/raw/health_facilities/hotosm_pak_health_facilities_points_geojson.geojson` (already aggregated/filtered; individual facility points, but this is inherently public map data, not survey microdata) |
| Required for | Facility-distance covariate |

## Quick reference: what's in this repo vs. what you must supply

| | In this repo | You supply |
|---|---|---|
| DHS/PDHS microdata (BR/HR/IR/KR/GE) | No | **Yes — required for real mortality estimates** |
| PBS census tables + boundary shapefile | Auto-fetched by pipeline | No |
| IHME GBD 2023 comparison data | Yes | No |
| OSM/HOTOSM facility locations | Yes | No |
| Pipeline code | Yes | No |
