# data/processed/dhs_derived/ — local-only, more granular than the public outputs

**This directory's contents are `.gitignore`d (see the repository
`.gitignore`) and are never committed or redistributed**, even though it
sits under `data/processed/` alongside directories that *are* public
(`features/`, `models/`, `decision/`, `geography/`, `demographics/`,
and the public-safe `mortality/`).

## What lives here (when you run the pipeline with your own DHS data)

- `cluster_district_lookup.csv` — DHS cluster ID → district crosswalk.
  Cluster IDs are a survey design index, not a household/respondent
  identifier, but this file is still one step more granular than a
  final district aggregate, so it stays local.
- `district_cluster_counts.csv` — per-district count of DHS clusters
  (the coverage diagnostic behind `low_direct_coverage`/`had_data`
  flags used downstream).
- `district_dhs_socioeconomic.csv` — district-aggregated DHS
  HR/IR-derived wealth, education, and ANC indicators.
- `district_u5mr_direct_dhs_full.csv` — the **full** direct U5MR
  estimate table, including raw `n_births_5yr`, `n_deaths_u5_5yr`, and
  `n_clusters` counts per district. Some districts have as few as 1
  sampled cluster or 0 recorded deaths in the reference window;
  publishing those exact counts next to a named district is a
  small-cell disclosure risk (see `docs/COMPLIANCE.md`). The
  **public-safe** counterpart — rate, CI, and coverage flag only, no
  raw counts — lives at `data/processed/mortality/district_u5mr_direct_dhs.csv`
  and *is* committed.
- `person_segment_records.csv` — person-period survival records used to
  fit the hierarchical hazard model. This is close to individual-level
  data (each row is a birth-segment, not a district), so it never
  leaves this directory.

## Why the boundary sits here and not one level up

`data/processed/` as a whole is not a synonym for "safe to publish."
Most of its subdirectories hold final, district-level, non-identifying
aggregates and are public. This one subdirectory holds intermediate,
more granular artifacts on the way to those aggregates, and is
deliberately kept local — see the `.gitignore` comment for the original
rationale and `docs/COMPLIANCE.md` for the full policy.
