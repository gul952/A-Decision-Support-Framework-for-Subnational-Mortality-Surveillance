# A Decision-Support Framework for Subnational Mortality Surveillance in Pakistan

*A reproducible small-area estimation and geospatial prioritization
platform for strengthening mortality surveillance.*

---

## The problem

Pakistan does not have reliable district-level mortality surveillance.
If Pakistan can only strengthen surveillance capacity in 20 districts
next year, **which 20 should it choose?** No transparent, reproducible
answer to that question currently exists publicly.

This project builds one: an open framework that integrates publicly
available demographic, geographic, and (registered-access) survey data
into a transparent system for prioritizing districts for mortality
surveillance investment under uncertainty — not a black-box prediction,
a decision-support tool that shows its work.

## What this is (and isn't)

It is **not** a dashboard, a machine learning project, a GIS project, or
a mortality prediction model in isolation. It is all of these combined
into one coherent system, organized into five layers:

```
Raw Data → Cleaning Pipeline → Statistical Model → Decision Engine → Interactive Platform
```

| Layer | What it does | Key output |
|---|---|---|
| 1. Data Engineering | Ingest and reconcile PBS census + DHS survey data into one clean, joinable district-level panel | `data/processed/geography/`, `data/processed/demographics/` |
| 2. Feature Engineering | Build interpretable composite indices (deprivation, WASH, crowding, remoteness) | `data/processed/features/` |
| 3. Small Area Estimation | Real DHS-derived district U5MR + Bayesian hierarchical discrete-time hazard model with province-level pooling | `data/processed/models/hierarchical_hazard_sae_results.csv` |
| 4. Decision Engine | Transparent, adjustable-weight prioritization scoring | `data/processed/decision/district_priority_scores.csv` |
| 5. Interactive Platform | Standalone dashboard: map, live weight sliders, per-district explainability | `dashboard/index.html` |

## Quickstart

```bash
git clone <this-repo>
cd pk-mortality-surveillance

# Option A: conda
conda env create -f environment.yml
conda activate pk-mortality-surveillance

# Option B: pip
pip install -r requirements.txt

# Run the full pipeline (fetches PBS census data automatically)
bash scripts/run_pipeline.sh --no-dhs   # without DHS access
# OR, if you have your own DHS-authenticated data (see below):
bash scripts/run_pipeline.sh
```

Then open `dashboard/index.html` directly in a browser (double-click it,
or drag it into a tab) to explore the results interactively -- no setup
needed. See `dashboard/README.md` for details, including the developer
option (`dashboard.jsx`) for integrating into a larger React app.

## About the DHS data requirement

Real district-level mortality estimation in this project uses **PDHS
2017-18 birth-history data**, which requires your own registered,
approved account with [The DHS Program](https://dhsprogram.com). This
data:

- **Cannot be fetched or redistributed by this repository** — it is not
  included, and `data/raw/dhs/` is git-ignored.
- **Requires you to register your own research project** at
  dhsprogram.com and request the Pakistan PDHS 2017-18 Births Recode
  (BR), Household Recode (HR), Individual Recode (IR), and GPS/
  Geographic (GE) datasets.
- Once downloaded, place the files at the paths documented in
  `docs/DATA_SOURCES.md` and re-run `scripts/run_pipeline.sh` (without
  `--no-dhs`).

**Without DHS data**, the pipeline still runs end-to-end using a
clearly-labeled deprivation-index-calibrated mortality *proxy* instead
of real survey-derived estimates — see `docs/LIMITATIONS.md` §2 for
exactly what that means and doesn't mean.

## Repository structure

```
data/
  raw/            # Original source data (PBS census auto-fetched;
                   # DHS microdata git-ignored, must be supplied by you)
  external/        # Third-party comparison data (e.g. IHME GBD, user-supplied)
  processed/       # Cleaned, feature-engineered, model-ready outputs
scripts/
  cleaning/        # Layer 1
  features/        # Layer 2
  models/          # Layer 3 (SAE)
  decision/        # Layer 4
  run_pipeline.sh  # One-command full rebuild
  build_dashboard_data.py   # Regenerate dashboard's embedded data
pkmortality/        # Shared config (paths, CRS, naming conventions)
dashboard/          # Layer 5 -- standalone React dashboard
models/              # Saved fitted models (regression .pkl, MCMC trace)
docs/
  DATA_SOURCES.md        # Every dataset used, with links, for your own records
  VARIABLE_DICTIONARY.md # Every variable, its source, and its transformation
  LIMITATIONS.md          # What this framework does and does not claim
  SENSITIVITY_FINDINGS.md # Robustness/sensitivity analysis results
  GBD_VALIDATION_FINDINGS.md # External cross-validation against IHME GBD 2023
paper/               # Research paper draft (in progress)
figures/             # Generated figures for the paper
```

## Key methodological notes

- **Real, corrected mortality estimation.** The district-level U5MR
  underlying this project's SAE model is computed from actual PDHS
  2017-18 individual birth-history survival records, via a discrete-
  time hazard model with proper right-censoring (see
  `scripts/models/04_hierarchical_hazard_sae.py`). An earlier version
  of this model had a real censoring-handling bug (fitting a plain
  binomial likelihood on already-aggregated counts); this was found,
  documented, and corrected -- see `docs/LIMITATIONS.md` for the full
  account, including two related indexing bugs found and fixed during
  the rebuild.
- **Aggregate consistency check (not "validation")**: this project's
  own direct synthetic-cohort national estimate (74.7/1,000) closely
  matches the published national U5MR (74.9/1,000). This confirms the
  estimator's basic arithmetic is correct at the national level; it is
  explicitly NOT evidence that district-level or hierarchical-model
  estimates are accurate, and is labeled as an aggregate consistency
  check throughout this project's documentation rather than
  "validation." See `docs/MODEL_VALIDATION.md` for genuine validation
  (posterior predictive checks, simulation recovery, calibration).
- **External benchmarking against IHME GBD 2023** (not cross-
  validation -- see terminology note in `docs/GBD_VALIDATION_FINDINGS.md`),
  using GBD's 2017-2018 average (time-matched to the PDHS 2017-18
  survey period). Under the corrected model, province rank correlation
  with GBD's independent estimate is 0.90 (up from 0.50 under the
  earlier, uncorrected model) -- reported as a real before/after
  comparison, not just a final number.
- **Honest uncertainty.** 13 of 135 districts have zero sampled DHS
  clusters and no direct survey information whatsoever. The Bayesian
  hierarchical model (Layer 3) handles this by pooling information
  across province and covariates — and its posterior credible intervals
  are visibly, correctly wider for these districts.
- **Transparent, adjustable weighting — not a fitted "correct" answer.**
  The Layer 4 priority score's default weights (40% mortality risk, 30%
  uncertainty, 20% geographic accessibility proxy, 10% population) are a
  literature-informed starting assumption. A full sensitivity analysis
  (`docs/SENSITIVITY_FINDINGS.md`) quantifies exactly how much the
  final ranking depends on that choice, and `docs/RANKING_STABILITY_FINDINGS.md`
  quantifies which top-priority districts are robust across posterior
  uncertainty and weight choices, versus which are more sensitive to them.
- **DHS compliance is structural, not just promised.** Raw DHS microdata
  never leaves `data/raw/dhs/` (git-ignored); every downstream file is
  aggregated, non-identifying, district-level statistics only. See
  `docs/DATA_SOURCES.md` for the full compliance notes.

## License

Code in this repository: MIT (see `LICENSE`).

Data: PBS 2017 Census data is redistributed here under the license of
its source repository (`cerp-analytics/pbs2017`, MIT). DHS data is
**not** redistributed — see the DHS terms of use at
https://dhsprogram.com/Data/terms-of-use.cfm, which govern any use of
that dataset by anyone reproducing this project.

## Citation / acknowledgment

If you use or extend this framework, please cite it and, if you use DHS
data, ensure you separately fulfill DHS's own requirement to submit a
copy of any resulting report/publication to references@dhsprogram.com.
