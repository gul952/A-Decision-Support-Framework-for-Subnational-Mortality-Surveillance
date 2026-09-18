# Third-Party Data Licenses

The root `LICENSE` file (MIT) covers **this project's original source
code only** — the Python pipeline, the dashboard's original code, and
this documentation's original prose. It does **not** automatically
extend to any third-party dataset used or referenced by the project.
Each data source below is licensed (or not) on its own terms, set by
its own provider, independent of how this repository licenses its own
code.

Status key: 🟢 GREEN (verified/low concern) · 🟡 YELLOW (conservative
handling recommended, or terms not independently re-verified) · 🔴 RED
(not applicable here — nothing at RED status is in this repository).

---

## 1. Original source code (this repository)

- **License:** MIT — see `LICENSE`.
- **Scope:** Python package (`pkmortality/`), pipeline scripts
  (`scripts/`), dashboard code (`dashboard/*.jsx`, `dashboard/index.html`
  markup/JS), tests, and this documentation's original prose.
- Status: 🟢

## 2. DHS / PDHS 2017-18 (Demographic and Health Surveys)

- **Source:** The DHS Program, ICF International, funded by USAID.
- **Terms:** https://dhsprogram.com/Data/terms-of-use.cfm
- **Raw microdata redistribution:** Not permitted, and not attempted.
  No PDHS microdata file is committed to this repository
  (`data/raw/dhs/` is `.gitignore`d).
- **Derived data redistribution:** DHS's terms do not specify an exact
  numeric small-cell threshold for derived aggregates. This project
  applies its own conservative policy (district-level, non-identifying
  aggregates only; raw small-cell counts such as exact death/cluster
  counts are additionally suppressed even at the district level — see
  `docs/COMPLIANCE.md`).
- **Purpose restriction:** Use of DHS data is tied to the specific
  registered DHS research project that obtained it. This repository's
  code does not grant, and cannot grant, permission to use DHS data —
  anyone reproducing this project must have their own DHS
  authorization covering their intended purpose.
- Status: 🟡 (structurally conservative, but DHS itself does not
  publish a bright-line numeric disclosure-risk rule, so "district
  aggregate" vs. "too granular" involved this project's own judgment)

## 3. IHME Global Burden of Disease (GBD) 2023

- **Source:** Global Burden of Disease Collaborative Network, GBD 2023
  Results, IHME, 2024. https://vizhub.healthdata.org/gbd-results/
- **Terms:** IHME free-of-charge, non-commercial GBD Results Tool user
  agreement.
- **Files committed:** `data/external/gbd/IHME-GBD_2023_DATA-*.csv`
  (province-level 5q0 estimates with uncertainty intervals — small,
  aggregate, non-identifying).
- **Status:** 🟡. Citation requirements are followed
  (`data/external/gbd/citation*.txt`). This project has not obtained a
  separate confirmation that redistributing the downloaded rows
  (rather than only using them internally and citing IHME) is
  explicitly within the free-of-charge agreement's terms. Given the
  data's aggregate, non-identifying, province-level nature, risk is
  assessed as low, but "low risk" is documented here as a judgment
  call, not a verified permission.

## 4. OpenStreetMap / HOTOSM (health facility locations)

- **Source:** OpenStreetMap contributors, exported via the HOTOSM Raw
  Data API. https://data.humdata.org/dataset/hotosm_pak_health_facilities
- **License:** Open Database License (ODbL) 1.0 for the database as a
  whole; individual contents under the Database Contents License. See
  `data/raw/health_facilities/HDX_Readme.txt`.
- **What this means:** ODbL permits redistribution and adaptation with
  **attribution** and, for "produced works," a **share-alike**
  obligation on the database itself (not on unrelated code). This
  project does **not** redistribute the raw OSM point data in the
  dashboard or public CSVs — only an aggregated derived statistic
  (`facility_count_in_district`, `facility_distance_km` in
  `data/processed/features/district_features.csv`) is published.
  Attribution ("© OpenStreetMap contributors") is included in the
  dashboard footer and here, satisfying ODbL's attribution requirement
  for the derived work, out of caution even though the published
  figures are aggregated rather than raw database extracts.
- **Not relicensed as MIT.** The OSM data and the project's own MIT
  code license are and remain separate; ODbL is not compatible with
  simply re-labeling the data MIT.
- Status: 🟢 (attribution present; only aggregated statistics
  published, not raw ODbL database contents)

## 5. OCHA administrative boundaries (via cerp-analytics/pbs2017 bundle)

- **Source claimed by upstream repo:** OCHA Pakistan administrative
  boundaries, via
  https://data.humdata.org/dataset/pakistan-union-council-boundaries-along-with-other-admin-boundaries-dataset
- **How it reached this project:** Bundled inside
  `cerp-analytics/pbs2017`, an MIT-licensed *code* repository. **The
  boundary shapefile's own license was not independently re-verified
  against the original HDX dataset page** — this project does not
  claim the boundaries are MIT-licensed merely because the repository
  that bundled them is. HDX-hosted OCHA boundary datasets are commonly
  CC BY-IGO or similar attribution-required terms, but the exact terms
  for this specific dataset/vintage have not been confirmed here.
- **Action taken:** Attribution to OCHA/HDX added to the dashboard
  footer and `docs/DATA_SOURCES.md` as a conservative precaution
  regardless of the exact license.
- **To resolve fully:** visit the HDX dataset page linked above and
  confirm the license field for the vintage actually bundled
  (~2010-vintage per the upstream repo's own README), then update this
  entry to 🟢.
- Status: 🟡

## 6. Pakistan Bureau of Statistics (PBS), 2017 Census

- **Source:** https://www.pbs.gov.pk/content/district-wise-results-tables-census-2017
  (official government statistics), reaching this project via
  `cerp-analytics/pbs2017`'s digitized tables.
- **Upstream repo license:** MIT (covers the digitization/formatting).
- **Underlying government data:** Official Pakistani census statistics
  published for public use; this project has not located a separate
  explicit open-data license statement from PBS itself, and treats the
  MIT label as applying to the digitization, not as a confirmed
  open-data grant from PBS. Given census summary tables are routinely
  published for public/statistical use and contain only aggregate
  district-level figures (no individual records), risk is assessed as
  low.
- Status: 🟡

## 7. World Bank / UN / WHO data

- **Status:** Not currently integrated into this project (see
  `docs/DATA_SOURCES.md`, "Still to source"). No license entry needed
  until/unless one of these sources is actually used.

## Summary table

| Source | Redistribute raw? | Redistribute derived/aggregate? | Attribution required? | Status |
|---|---|---|---|---|
| Original code | — | — | — | 🟢 MIT |
| DHS/PDHS | No | Conservatively, district-level only, small cells suppressed | Yes (terms-of-use link) | 🟡 |
| IHME GBD 2023 | Aggregate rows only | Yes (assessed low-risk, not independently confirmed) | Yes (citation included) | 🟡 |
| OSM/HOTOSM | No (aggregated only) | Yes (aggregated statistic only) | Yes (added to dashboard) | 🟢 |
| OCHA boundaries | Yes (currently, as polygons) | — | Yes (added to dashboard) | 🟡 — license not independently re-verified |
| PBS 2017 Census | Yes (aggregate tables) | Yes | Recommended | 🟡 |
