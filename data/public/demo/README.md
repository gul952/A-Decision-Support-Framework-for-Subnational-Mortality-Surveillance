# data/public/demo/ — the project's demo mode already exists upstream

This project already implements the "public demo mode vs. full
reproduction mode" behavior described in `REPRODUCIBILITY.md`, but it
lives in the modeling pipeline rather than as a separate static file in
this folder, so there is nothing to duplicate here.

## How it actually works

`scripts/run_pipeline.sh` (and the individual scripts it calls) branch
on whether authorized local DHS microdata is present at `data/raw/dhs/`:

- **No local DHS data** (`--no-dhs`, or the files are simply absent):
  the pipeline runs end-to-end using
  `scripts/models/02_build_mortality_risk_proxy.py`, a deprivation-index
  calibrated proxy. Every row produced this way is labeled
  `estimate_type = "proxy"` and annotated
  `"Deprivation-index-calibrated proxy (NOT PDHS-derived)"` in
  `data/processed/mortality/district_mortality_estimate.csv` — this is
  the project's demonstration/public-safe mode. It contains no DHS
  microdata or DHS-derived small-cell counts of any kind, because none
  were used to produce it.
- **Local DHS data present**: the pipeline additionally runs the real
  synthetic-cohort direct estimation and hierarchical hazard model,
  producing `estimate_type = "dhs_direct"` / hierarchical posterior
  rows — this is full reproduction mode.

The dashboard (`dashboard/index.html`, built by
`scripts/build_dashboard_data.py`) simply displays whatever
`data/processed/models/hierarchical_hazard_sae_results.csv` and related
files contain at build time — so a dashboard built without DHS data
shows demo/proxy values, and one built with it shows real estimates.
Both cases are labeled via the `estimate_type`/`run_mode` fields; see
`docs/LIMITATIONS.md` for exactly what each label does and does not
claim.

**Nothing in the committed, public copy of this data is synthetic or
fabricated** — the "demo" values are a real, clearly-labeled,
non-DHS proxy estimate, not invented numbers standing in for DHS
results. See `COMPLIANCE.md` for the full policy discussion.
