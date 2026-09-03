# Data Sources Log

Every dataset used in this project, with direct links, access date, and
license/terms. Use this as your own download record — anything marked
`[FETCHED]` is already pulled into `data/raw/` or `data/external/`;
anything marked `[NEEDED FROM YOU]` requires your DHS-authenticated login.

---

## 1. Demographic and Health Surveys (DHS) — Pakistan PDHS 2017-18 & 2019 MMS

**Status:** `[RECEIVED]` — uploaded 2026-08-04, processed under DHS terms of use.

| File | Used from | Purpose |
|---|---|---|
| Births Recode (BR), PKBR71DT | 2017-18 PDHS | Birth histories → district-level U5MR (synthetic cohort method) |
| Household Recode (HR), PKHR71DT | 2017-18 PDHS | Wealth index, water/sanitation — **integrated** (`scripts/cleaning/04_clean_dhs_hr_ir.py`) |
| Individual/Women's Recode (IR), PKIR71DT | 2017-18 PDHS | Maternal education, ANC — **integrated** (`scripts/cleaning/04_clean_dhs_hr_ir.py`) |
| GPS/Geographic (GE), PKGE71FL | 2017-18 PDHS | 561 cluster lat/long (displaced) → spatial join to districts |
| DHS Covariates Extract, PKGC72FL | 2017-18 PDHS | Pre-built geospatial covariates (not yet integrated) |
| 2019 Maternal Mortality Survey (HH/IQ/BQ/SQ) | 2019 MMS | No GPS component; potential supplementary source, not yet integrated |

**Validation:** national U5MR reimplemented from BR microdata via synthetic-cohort actuarial method = 74.7/1,000, matching the published PDHS 2017-18 figure of 74.9/1,000 to within 0.2 points.

**Terms of use:** https://dhsprogram.com/Data/terms-of-use.cfm — full terms including non-redistribution, confidentiality, and no re-identification apply and are enforced structurally (see compliance notes below, unchanged from original request).

**Compliance notes (binding for this project):**
- Raw microdata is stored only in `data/raw/dhs/` which is `.gitignore`d and never committed to any repository or redistributed in the dashboard.
- Only district-aggregated, non-identifying derived indicators (e.g. "District X estimated U5MR = 0.045, 95% CI [...]") are permitted downstream in `data/processed/`, the Python package, or the dashboard.
- No household/individual/cluster-level DHS records are displayed, exported, or bundled anywhere outside `data/raw/dhs/`.
- The cluster→district lookup (`data/processed/dhs_derived/cluster_district_lookup.csv`) contains cluster IDs (a survey design index, not a household/respondent identifier) mapped to districts — kept in `data/processed/` as a derived artifact, but not published verbatim in the dashboard/paper; only resulting aggregate counts/rates are surfaced there.
- Displaced GPS coordinates are used only for cluster→district spatial assignment, never for facility-distance calculations at sub-5km precision.
- Districts with thin direct DHS coverage are flagged (`low_direct_coverage`) rather than suppressed, consistent with DHS's own small-area publication norms, and are never disaggregated further.
- A PDF of any resulting report/publications will be submitted to references@dhsprogram.com per the terms — **action item for you before any public paper/report release.**
- Only your registered DHS project's approved research purpose covers this analysis; using this data for an unrelated project would require registering a new DHS project first, per DHS's own terms.

---

## 2. Pakistan Bureau of Statistics — 2017 Census (via cerp-analytics digitization)

**Status:** `[FETCHED]` — 2026-08-04

- Repo: https://github.com/cerp-analytics/pbs2017
- Original source: https://www.pbs.gov.pk/content/district-wise-results-tables-census-2017
- License: MIT
- Tables used: Table 01 (population/density/urban%), Table 12 (literacy, tehsil→district aggregated), Table 29 (household crowding), Table 35 (water source), Table 37 (sanitation/kitchen)
- Local path: `data/raw/pbs2017-main/data/`

## 3. District Boundary Shapefile

**Status:** `[FETCHED]` — 2026-08-04

- Bundled in the same repo above (`data/raw/pbs2017-main/data/00_shapefiles/District_Boundary.shp`)
- Original source: OCHA Pakistan admin boundaries, via https://data.humdata.org/dataset/pakistan-union-council-boundaries-along-with-other-admin-boundaries-dataset
- 161 polygons, WGS84 (EPSG:4326)
- Note: boundaries dated ~2010-vintage per repo README; some divergence from 2017 census district list expected (e.g. district splits) — reconciled in `scripts/cleaning/01_clean_geography.py`

---

## Still to source (planned, not yet fetched)

| Source | Purpose | Status |
|---|---|---|
| WHO Global Health Observatory | health indicators, vaccination coverage | not started |
| IHME GBD | province-level cause-specific mortality burden (for calibration/priors) | **integrated** — see below |
| Health facility locations (Pakistan) | facility density, travel-time proxy | **integrated 2026-09-01** — see below |
| WorldPop / nighttime lights (VIIRS) | population density validation, economic activity proxy | stretch goal |

### Health facility locations (OpenStreetMap via HOTOSM) — completed

**Status:** `[FETCHED]` — 2026-05-06 (exported), integrated 2026-09-01.

- Source: https://data.humdata.org/dataset/hotosm_pak_health_facilities
- Export tool: HOTOSM Raw Data API (https://github.com/hotosm/raw-data-api), OpenStreetMap data
- License: Open Database License (ODbL) 1.0; individual contents under the Database Contents License — see `data/raw/health_facilities/HDX_Readme.txt`
- Local path: `data/raw/health_facilities/hotosm_pak_health_facilities_points_geojson.geojson`
- 4,376 total points; 3,116 retained after filtering to clinically-relevant types (hospital/clinic/doctors, excluding pharmacy/dentist/lab)
- Used by: `scripts/features/02_build_facility_distance.py`
- **Key finding:** meaningful convergent validity with the existing `remoteness_proxy` (r = 0.71) and near-identical Balochistan representation in the top-20 priority list (14/20 vs. 13/20) — but coverage is itself geographically uneven (35/135 districts have zero mapped facilities, concentrated in Balochistan and former FATA). See `docs/LIMITATIONS.md` §5 for the full comparison and the important caveat about interpreting results in low-coverage districts.

### IHME GBD cross-validation — completed

**Status:** `[RECEIVED]` — user downloaded 2026-08-06/08 via IHME GBD
Results Tool (requires authenticated account; not fetchable by this
pipeline automatically).

- **Primary file** (time-matched to PDHS 2017-18 survey period):
  `IHME-GBD_2023_DATA-7bcd58a5-1.csv` — province-level 5q0, years 2017
  AND 2018 (averaged in the validation script), with upper/lower
  uncertainty bounds. Local path:
  `data/external/gbd/IHME-GBD_2023_DATA-7bcd58a5-1.csv`.
- **Supplementary file** (reference year 2019, kept to check GBD's own
  year-to-year movement): `IHME-GBD_2023_DATA-78a15125-1.csv`. Local
  path: `data/external/gbd/IHME-GBD_2023_DATA-78a15125-1.csv`.
- Citation: Global Burden of Disease Collaborative Network. Global
  Burden of Disease Study 2023 (GBD 2023) Results. Seattle, United
  States: Institute for Health Metrics and Evaluation (IHME), 2024.
  Available from https://vizhub.healthdata.org/gbd-results/.
- License: IHME free-of-charge non-commercial user agreement (data is
  small, aggregate, and non-identifying — no special compliance
  handling needed beyond standard citation).
- Used by: `scripts/models/06_validate_against_gbd.py`
- **Key finding (current, post-censoring-fix):** using the properly
  time-matched 2017-2018 average and the corrected discrete-time
  hazard model (`04_hierarchical_hazard_sae.py`), province-level
  agreement with GBD is strong — Spearman rank correlation 0.90.
  Punjab and KP are close; the largest remaining gap is Sindh
  (this project: 48.2 vs. GBD: 61.7/1,000, -22%), an ordinary-
  magnitude difference attributable to genuine methodological
  differences rather than a structural issue. See
  `docs/GBD_VALIDATION_FINDINGS.md` for the full comparison table.
  **Historical note:** an earlier, since-corrected version of the
  hierarchical model (`03_DEPRECATED_hierarchical_bayesian_sae_binomial.py`,
  which incorrectly assumed every birth had a full uncensored 5-year
  follow-up) showed a substantial 56% Balochistan divergence from GBD
  (79.1 vs. 50.7/1,000) and only 0.50 rank correlation — this was a
  real bug, now fixed; see `docs/LIMITATIONS.md` §1 for the full
  before/after account. Do not cite the 79.1/50.7/56%/0.50 figures as
  the project's current result.

*This file is updated as the pipeline grows — check back after each new layer.*
