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
- **Terms:** IHME Free-of-Charge Non-Commercial User Agreement
  (https://www.healthdata.org/Data-tools-practices/data-practices/ihme-free-charge-non-commercial-user-agreement).
- **Confirmed restrictive clause:** *"User may not without written
  permission from UW provide to third parties the ability to download
  IHME Data Sets from User-provided hosting facilities; User may
  publish links to IHME's hosting and downloading facilities."*
- **Finding:** the raw downloaded files
  (`IHME-GBD_2023_DATA-78a15125-1.csv`, `IHME-GBD_2023_DATA-7bcd58a5-1.csv`)
  were committed to this public repository — on a plain reading, that
  is exactly the "provide to third parties the ability to download
  IHME Data Sets from User-provided hosting facilities" the agreement
  prohibits without written permission from UW, which this project
  does not have.
- **Remediation:** both files were removed from git tracking (kept
  locally, `.gitignore`d) — see `data/external/gbd/README.md` for the
  full note and how to re-obtain them yourself. `DATA_ACCESS.md` was
  updated accordingly.
- **What remains committed:** `citation.txt` /
  `citation_province_2017_2018.txt` (citation text, no data values —
  fine) and `data/processed/models/gbd_validation_comparison.csv`
  (this project's own small derived comparison table — the same
  agreement explicitly permits "Results" containing "only such
  portions... as are necessary" for internal research/Publication,
  which this qualifies as).
- Status: 🟢 (after remediation) — was 🔴 before the raw files were
  untracked; see `COMPLIANCE.md` for the historical git note.

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

## 5. District boundary shapefile (via cerp-analytics/pbs2017 bundle) — corrected attribution

- **How it reached this project:** Bundled inside
  `cerp-analytics/pbs2017`, an MIT-licensed *code* repository.
- **Corrected source identification:** this project's own documentation
  previously called this "OCHA Pakistan admin boundaries." Checking the
  actual linked HDX dataset page
  (https://data.humdata.org/dataset/pakistan-union-council-boundaries-along-with-other-admin-boundaries-dataset)
  shows the source/contributor is actually **ALHASAN Systems Private
  Limited**, a private company — not an official OCHA product, despite
  being hosted on OCHA's HDX platform. This has been corrected in
  `docs/DATA_SOURCES.md`.
- **License, per HDX's own metadata field:** "Public Domain / No
  Restrictions."
- **A contradiction worth flagging rather than resolving
  conveniently:** the same dataset page's caveats/comments text states
  "This product is the sole property of ALHASAN SYSTEMS" — in tension
  with the formal "Public Domain / No Restrictions" license field.
  HDX itself does not resolve this contradiction. This project
  proceeds on the formal license field (the more specific, structured
  metadata) while documenting the contradiction here rather than
  silently picking whichever reading is more convenient.
- **Action taken:** attribution to ALHASAN Systems (not OCHA) added to
  the dashboard footer and `docs/DATA_SOURCES.md`, correcting the
  earlier mis-attribution, and out of caution given the "sole
  property" caveat despite the public-domain license field.
- Status: 🟡 (license field says Public Domain, but the ownership
  caveat is real and unresolved — attribution kept as a precaution)

## 6. Pakistan Bureau of Statistics (PBS), 2017 Census

- **Source:** https://www.pbs.gov.pk/content/district-wise-results-tables-census-2017
  (official government statistics), reaching this project via
  `cerp-analytics/pbs2017`'s digitized tables.
- **Upstream repo license:** MIT (covers the digitization/formatting).
- **Underlying government data:** Official Pakistani census statistics
  published for public use; this project has not located a separate
  explicit open-data license statement from PBS itself, and treats the
  MIT label as applying to the digitization, not as a confirmed
  open-data grant from PBS. **Note found during verification:** PBS's
  own "Data Dissemination" page
  (https://www.pbs.gov.pk/content/data-dissemination) historically
  describes selling census data on physical media for a fee to
  external users — evidence that PBS has treated its data as something
  to control/sell rather than something it has explicitly placed under
  an open license, which weighs toward caution rather than resolving
  it. Given census summary tables are nonetheless routinely published
  for public/statistical use and contain only aggregate district-level
  figures (no individual records), risk is still assessed as low.
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
| IHME GBD 2023 | No (removed after finding an explicit prohibition — see §3) | Yes, as a derived comparison table (permitted "Result") | Yes (citation included) | 🟢 (after remediation) |
| OSM/HOTOSM | No (aggregated only) | Yes (aggregated statistic only) | Yes (added to dashboard) | 🟢 |
| District boundaries (ALHASAN Systems, mislabeled "OCHA" previously) | Yes (currently, as polygons) | — | Yes (corrected attribution added to dashboard) | 🟡 — license field says Public Domain, but a "sole property" caveat is unresolved |
| PBS 2017 Census | Yes (aggregate tables) | Yes | Recommended | 🟡 |
