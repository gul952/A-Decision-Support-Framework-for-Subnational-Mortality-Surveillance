#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_pipeline.sh -- rebuild the entire project from raw data in one command.
#
# Usage:
#   bash scripts/run_pipeline.sh              # full pipeline, incl. DHS steps
#   bash scripts/run_pipeline.sh --no-dhs      # skip DHS-dependent steps
#                                                (use if you have not yet
#                                                 placed DHS files in
#                                                 data/raw/dhs/ -- see
#                                                 docs/DATA_SOURCES.md)
#
# Prerequisites:
#   1. Python environment created from environment.yml or requirements.txt
#   2. data/raw/pbs2017-main/ present (auto-fetched by this script if missing)
#   3. [OPTIONAL, for real mortality estimates] Your own DHS-authenticated
#      download of PK BR/HR/IR/GE recode files placed under:
#        data/raw/dhs/2017-18_DHS_GPS/PKBR71DT/PKBR71FL.DTA
#        data/raw/dhs/2017-18_DHS_GPS/PKGE71FL/PKGE71FL.shp
#      See docs/DATA_SOURCES.md for exact download instructions -- this
#      data requires your own registered DHS Program account and CANNOT
#      be fetched automatically (nor should it be, per DHS terms of use).
#      Without it, the pipeline still runs end-to-end using the
#      deprivation-index-calibrated mortality PROXY (clearly labeled as
#      such throughout outputs) -- see docs/LIMITATIONS.md.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

RUN_DHS=true
if [[ "${1:-}" == "--no-dhs" ]]; then
  RUN_DHS=false
fi

DHS_BR="data/raw/dhs/2017-18_DHS_GPS/PKBR71DT/PKBR71FL.DTA"
DHS_GE="data/raw/dhs/2017-18_DHS_GPS/PKGE71FL/PKGE71FL.shp"

echo "==================================================================="
echo " Pakistan Subnational Mortality Surveillance -- Pipeline Runner"
echo "==================================================================="

# --- Step 0: fetch PBS 2017 census data if not already present -----------
if [ ! -d "data/raw/pbs2017-main" ]; then
  echo ""
  echo "[0/5] Fetching PBS 2017 census data (cerp-analytics/pbs2017)..."
  mkdir -p data/raw
  curl -sL -o /tmp/pbs2017.tar.gz \
    "https://codeload.github.com/cerp-analytics/pbs2017/tar.gz/refs/heads/main"
  tar -xzf /tmp/pbs2017.tar.gz -C data/raw/
  rm /tmp/pbs2017.tar.gz
  echo "  Done."
else
  echo ""
  echo "[0/5] PBS 2017 census data already present, skipping fetch."
fi

# --- Step 1: Layer 1 -- Data cleaning -------------------------------------
echo ""
echo "[1/5] Layer 1: Data cleaning..."
python3 scripts/cleaning/01_clean_geography.py
python3 scripts/cleaning/02_clean_demographics_socioeconomic.py

if [ "$RUN_DHS" = true ]; then
  if [ -f "$DHS_GE" ]; then
    python3 scripts/cleaning/03_clean_dhs_cluster_geography.py
  else
    echo "  WARNING: DHS GPS file not found at $DHS_GE"
    echo "  Skipping DHS cluster geography step. See docs/DATA_SOURCES.md."
    echo "  Re-run with real DHS data placed correctly, or use --no-dhs to"
    echo "  suppress this warning and proceed on the proxy pathway only."
  fi

  DHS_HR="data/raw/dhs/2017-18_DHS_GPS/PKHR71DT/PKHR71FL.DTA"
  DHS_IR="data/raw/dhs/2017-18_DHS_GPS/PKIR71DT/PKIR71FL.DTA"
  if [ -f "$DHS_HR" ] && [ -f "$DHS_IR" ] && [ -f "data/processed/dhs_derived/cluster_district_lookup.csv" ]; then
    python3 scripts/cleaning/04_clean_dhs_hr_ir.py
  else
    echo "  WARNING: DHS HR/IR files not found or cluster lookup missing."
    echo "  Skipping DHS household/individual indicators (wealth, education,"
    echo "  ANC). Layer 2 will fall back to census-only indicators for all"
    echo "  districts. See docs/DATA_SOURCES.md."
  fi
fi

# --- Step 2: Layer 2 -- Feature engineering -------------------------------
echo ""
echo "[2/5] Layer 2: Feature engineering..."
python3 scripts/features/01_build_composite_indices.py

# --- Step 3: Layer 3 -- Small area estimation -----------------------------
echo ""
echo "[3/6] Layer 3: Small area estimation..."
python3 scripts/models/02_build_mortality_risk_proxy.py

if [ "$RUN_DHS" = true ] && [ -f "$DHS_BR" ]; then
  python3 scripts/models/02b_estimate_u5mr_from_dhs.py
  python3 scripts/models/03_build_person_segment_records.py
else
  echo "  Skipping DHS-derived U5MR estimation and person-segment record"
  echo "  construction (BR file not found or --no-dhs used)."
  echo "  The hierarchical hazard model below will run in NO-DHS PRIOR-ONLY"
  echo "  mode: every district gets a pure covariate/province-based estimate"
  echo "  with no survey data anchoring it. This is NOT a usable mortality"
  echo "  estimate -- see docs/LIMITATIONS.md. Obtain real PDHS BR data for"
  echo "  a real analysis."
fi

python3 scripts/models/01_baseline_regression.py

if [ "$RUN_DHS" = false ]; then
  python3 scripts/models/04_hierarchical_hazard_sae.py --force-no-dhs
else
  python3 scripts/models/04_hierarchical_hazard_sae.py
fi

if [ -f "data/external/gbd/IHME-GBD_2023_DATA-7bcd58a5-1.csv" ]; then
  python3 scripts/models/06_validate_against_gbd.py
else
  echo "  Skipping GBD external benchmarking (data/external/gbd/ file not found)."
  echo "  See docs/DATA_SOURCES.md for how to obtain it -- requires a free"
  echo "  IHME account, not fetchable automatically."
fi

if [ "$RUN_DHS" = true ] && [ -f "$DHS_BR" ]; then
  echo ""
  echo "[3b/6] Layer 3: Model validation (posterior predictive checks,"
  echo "        simulation recovery, calibration, model comparison)..."
  python3 scripts/models/07_model_validation.py
else
  echo "  Skipping model validation (requires real DHS-anchored model)."
fi

# --- Step 4: Layer 4 -- Decision engine -----------------------------------
echo ""
echo "[4/6] Layer 4: Decision engine..."
python3 scripts/decision/01_prioritization_engine.py
python3 scripts/decision/02_sensitivity_analysis.py

if [ "$RUN_DHS" = true ] && [ -f "$DHS_BR" ]; then
  python3 scripts/decision/03_ranking_stability.py
else
  echo "  Skipping ranking stability analysis (requires real DHS-anchored model trace)."
fi

# --- Step 5: Done ----------------------------------------------------------
echo ""
echo "[5/6] Pipeline complete."
echo ""
echo "Key outputs:"
echo "  data/processed/geography/districts.geojson"
echo "  data/processed/features/district_features.csv"
echo "  data/processed/models/hierarchical_hazard_sae_results.csv"
echo "  data/processed/decision/district_priority_scores.csv"
echo "  docs/SENSITIVITY_FINDINGS.md"
echo "  docs/RANKING_STABILITY_FINDINGS.md"
echo "  docs/MODEL_VALIDATION.md"
echo "  docs/GBD_VALIDATION_FINDINGS.md"
echo ""
echo "[6/6] Dashboard: open dashboard/index.html directly in a browser"
echo "(double-click it, no setup needed), or run 'python3"
echo "scripts/build_dashboard_data.py' to refresh its data after this"
echo "pipeline run (see dashboard/README.md)."
echo "==================================================================="
