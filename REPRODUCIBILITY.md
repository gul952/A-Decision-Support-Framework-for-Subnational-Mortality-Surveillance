# Reproducibility Guide

This is a step-by-step guide to reproducing this project's analysis,
in either mode:

- **Public demo mode** — no DHS access needed, runs entirely on
  committed public/auto-fetched data, produces a clearly-labeled
  deprivation-index proxy instead of real survey-derived mortality
  estimates.
- **Full reproduction mode** — requires your own authorized DHS data
  (see `DATA_ACCESS.md`), produces the real PDHS-derived estimates.

Exact numerical results are reproducible **only** given the exact same
DHS data vintage, the same software environment (see `environment.yml`
for pinned versions), and the same random seeds used in bootstrap/MCMC
steps. This guide does not claim byte-identical output is guaranteed
across different environments or DHS data extract dates — only that
the method is fully specified and re-runnable.

## 1. Environment setup

Requires Python 3.10+ (this project was built and tested with the
version pinned in `environment.yml`).

```bash
git clone <this-repo>
cd A-Decision-Support-Framework-for-Subnational-Mortality-Surveillance

# Option A: conda (recommended, pins exact versions)
conda env create -f environment.yml
conda activate pk-mortality-surveillance

# Option B: pip
pip install -r requirements.txt
```

## 2. Data acquisition

- Public demo mode: nothing to do yet — `scripts/run_pipeline.sh
  --no-dhs` fetches the PBS census data automatically.
- Full reproduction mode: follow `DATA_ACCESS.md` to obtain your own
  authorized DHS files, and place them at the documented paths under
  `data/raw/dhs/` before continuing.

## 3. Directory structure check

After setup, you should have:

```
data/
  raw/
    dhs/            # empty unless you added your own DHS files (gitignored)
    health_facilities/   # committed OSM/HOTOSM data
    pbs2017-main/   # auto-fetched by run_pipeline.sh, not committed
  external/gbd/     # committed IHME GBD comparison data
  processed/        # created/overwritten by the pipeline
```

## 4. Validation checks (optional but recommended)

```bash
python -m pytest tests/ -v
```

This exercises the config module, feature engineering, decision engine,
and U5MR estimation logic against known small fixtures — it does not
require DHS data.

## 5. Run the pipeline

```bash
# Public demo mode (no DHS data required):
bash scripts/run_pipeline.sh --no-dhs

# Full reproduction mode (after placing DHS files per DATA_ACCESS.md):
bash scripts/run_pipeline.sh
```

This runs, in order: geography/demographics cleaning → (if DHS data
present) DHS cluster/HR/IR/KR cleaning → composite feature indices →
facility-distance covariate → baseline regression → mortality
risk proxy (demo mode) or direct DHS U5MR estimation + hierarchical
hazard model (full mode) → GBD/vaccination validation → decision
engine (prioritization, sensitivity, ranking stability) →
`scripts/build_dashboard_data.py` to regenerate the dashboard's
embedded data.

Each stage prints its own diagnostics (row counts, coverage flags,
sanity-check comparisons against published national figures) —- read
these as you go; they're designed to surface data-join problems early
rather than fail silently.

## 6. Generate public-safe outputs

This happens automatically as part of step 5:
`scripts/models/02b_estimate_u5mr_from_dhs.py` (when run in full mode)
writes both a full local-only file
(`data/processed/dhs_derived/district_u5mr_direct_dhs_full.csv`, never
committed) and a public-safe subset
(`data/processed/mortality/district_u5mr_direct_dhs.csv`, small-cell
counts removed — see `COMPLIANCE.md`). No manual step is needed,
but if you're adding a new DHS-derived output of your own, follow the
same two-tier pattern.

## 7. Launch the dashboard

```bash
open dashboard/index.html   # or double-click it, or drag into a browser tab
```

No server needed — it's a self-contained HTML file with the pipeline's
output data embedded at build time by `scripts/build_dashboard_data.py`.

## 8. Run the compliance/safety scanner

Before publishing any change, or after regenerating data:

```bash
python scripts/audit_public_release.py
```

Exits non-zero and lists specifics if it finds anything that shouldn't
be there (DHS microdata file extensions, likely credential files, etc.)
— see the script's own `--help` and docstring for exactly what it
checks and why each check exists.

## Troubleshooting

**`FileNotFoundError` for `data/raw/dhs/...`** — expected if you
haven't supplied DHS data; either add it (see `DATA_ACCESS.md`) or
re-run with `--no-dhs`.

**Pipeline runs but produces `estimate_type = "proxy"` everywhere even
though you added DHS files** — check the exact paths in `DATA_ACCESS.md`
match what you placed; the cleaning scripts fail closed (skip DHS
integration) rather than partially trusting a malformed path.

**`run_mode = "no_dhs_prior_only"` in the hierarchical model output**
— this is a deliberate degenerate fallback for `--no-dhs` runs; it
reflects only the model's prior, not survey evidence, and per
`docs/LIMITATIONS.md` should not be cited as a mortality estimate. It
is guarded by a `--force-no-dhs` flag precisely so it can't silently
overwrite a real result — if you see this unexpectedly with real DHS
data present, check that the cluster→district join in
`scripts/cleaning/03_clean_dhs_cluster_geography.py` actually matched
clusters (a common cause is a stale or missing
`cluster_district_lookup.csv`).

**GBD/vaccination validation scripts fail** — these require the files
in `data/external/gbd/` (already committed) and, for vaccination
validation, your own KR file — they are validation steps, not required
for the core pipeline to run.

**Dashboard shows stale numbers after re-running the pipeline** — re-run
`python scripts/build_dashboard_data.py` explicitly; it's the last
step of `run_pipeline.sh` but can be skipped if you interrupted a run.

**Different numbers than the ones documented in `docs/*_FINDINGS.md`**
— expected if your DHS extract date, software versions, or random
seeds differ from the original run; see the caveat at the top of this
document. Open an issue with your `environment.yml`/`requirements.txt`
diff if the difference seems larger than normal sampling variation.
