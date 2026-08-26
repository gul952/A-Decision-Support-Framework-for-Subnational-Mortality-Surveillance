"""
02_build_mortality_risk_proxy.py

*** THIS IS A PROXY, NOT A MORTALITY ESTIMATE. READ THIS DOCSTRING. ***

Layer 2/3 boundary: constructs a district-level "mortality risk proxy"
from the deprivation_index and its components, calibrated to plausible
U5MR magnitudes using published province/national benchmarks. This
proxy exists ONLY because we do not yet have your PDHS BR (Births
Recode) file, which is the actual data source for a real district-level
U5MR estimate via birth-history survival analysis.

The proxy is built like this:
    1. Take deprivation_index in [0, 1] (from Layer 2 composite indices)
    2. Map it onto a plausible U5MR range using a calibration anchored
       to published, cited national/province figures:
         - National U5MR 2017: 74.9 per 1,000 live births
           (World Bank/UN IGME, https://data.worldbank.org/indicator/SH.DYN.MORT?locations=PK)
         - Punjab: ~94/1,000, Balochistan: ~92.6/1,000
           (province-level 2017 census demographic analysis; see
           docs/DATA_SOURCES.md for full citation)
       We anchor the proxy's mean to the national figure and its spread
       to roughly span the known province-level range, NOT to any
       district-level ground truth (none exists yet in this pipeline).
    3. Add calibrated Gaussian noise reflecting sampling-type uncertainty,
       so the proxy has a distribution (not a point value) -- this
       lets the SAE and decision-engine code paths be built and tested
       against something that behaves like real uncertain data, without
       pretending precision we do not have.

WHEN YOU UPLOAD PDHS BR/HR/IR FILES:
    Replace this script's output with `02b_estimate_u5mr_from_dhs.py`
    (birth-history direct/indirect estimation + small-area smoothing).
    Every downstream script (SAE model, decision engine, dashboard)
    reads from data/processed/mortality/district_mortality_estimate.csv
    regardless of which script produced it, so swapping the source
    requires no changes elsewhere in the pipeline.

Output:
    data/processed/mortality/district_mortality_estimate.csv
    columns: district_key, mortality_estimate_per1000, mortality_lower95,
             mortality_upper95, estimate_type ("proxy" until DHS-derived)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, RANDOM_SEED

IN_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_DIR = DATA_PROCESSED / "mortality"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Calibration anchors (cited, not invented) ---------------------------
NATIONAL_U5MR_2017 = 74.9   # World Bank/UN IGME, per 1,000 live births
U5MR_LOW_ANCHOR = 45.0      # plausible low end (best-off urban districts;
                             # PDHS urban U5MR historically runs well below
                             # the national rural-weighted average)
U5MR_HIGH_ANCHOR = 130.0    # plausible high end (worst-off districts;
                             # province-level Balochistan/interior Sindh
                             # figures in the 90-110 range, with individual
                             # districts plausibly higher -- see DATA_SOURCES.md)

# Proxy uncertainty: wider intervals for districts inferred purely from
# deprivation (no local data at all) vs narrower where we at least have
# full census coverage. Because NO district here has actual DHS cluster
# data yet, uncertainty is deliberately kept wide across the board.
PROXY_CI_HALF_WIDTH_PCT = 0.35  # +/- 35% of point estimate, reflecting
                                  # that this is a socioeconomic proxy,
                                  # not a design-based survey estimate


def calibrate_proxy(deprivation: pd.Series) -> pd.Series:
    """Linear map from deprivation_index [0,1] to plausible U5MR range,
    re-centered so the population-weighted mean lands near the cited
    national figure (see main() for the recentering step)."""
    return U5MR_LOW_ANCHOR + deprivation * (U5MR_HIGH_ANCHOR - U5MR_LOW_ANCHOR)


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    print(f"Loading {IN_PATH}...")
    df = pd.read_csv(IN_PATH)

    print("Calibrating mortality risk proxy from deprivation_index...")
    raw_proxy = calibrate_proxy(df["deprivation_index"])

    # Add genuine stochastic noise BEFORE recentering, not just a display
    # uncertainty band. Without this, mortality_estimate_per1000 is a
    # deterministic linear function of deprivation_index's own inputs
    # (literacy, WASH, crowding) -- perfectly collinear with them by
    # construction, which would make any downstream regression on those
    # same covariates a circular, R^2=1.0 exercise rather than a real
    # modeling problem. The noise magnitude (SD = 8% of the anchor range)
    # is a modeling choice, not measured sampling error -- it exists only
    # so the SAE scripts in this pipeline have something non-trivial to
    # estimate and validate against until real PDHS data replaces this
    # proxy entirely.
    noise_sd = 0.08 * (U5MR_HIGH_ANCHOR - U5MR_LOW_ANCHOR)
    noise = rng.normal(loc=0, scale=noise_sd, size=len(df))
    raw_proxy_noisy = raw_proxy + noise

    # Re-center so the population-weighted mean matches the cited national
    # U5MR (74.9/1000) -- this is the calibration step that keeps the
    # proxy's overall magnitude defensible even though its district-level
    # *shape* is driven mostly by our deprivation index, not real mortality
    # data.
    pop_weighted_mean = np.average(raw_proxy_noisy, weights=df["population_2017"])
    shift = NATIONAL_U5MR_2017 - pop_weighted_mean
    df["mortality_estimate_per1000"] = raw_proxy_noisy + shift
    df["mortality_estimate_per1000"] = df["mortality_estimate_per1000"].clip(lower=20)

    print(
        f"  Population-weighted mean before recentering: {pop_weighted_mean:.1f}\n"
        f"  Shift applied: {shift:+.1f}\n"
        f"  Population-weighted mean after recentering: "
        f"{np.average(df['mortality_estimate_per1000'], weights=df['population_2017']):.1f} "
        f"(target: {NATIONAL_U5MR_2017})"
    )

    # Uncertainty interval -- proportional half-width, not a real survey CI
    half_width = df["mortality_estimate_per1000"] * PROXY_CI_HALF_WIDTH_PCT
    df["mortality_lower95"] = (df["mortality_estimate_per1000"] - half_width).clip(lower=10)
    df["mortality_upper95"] = df["mortality_estimate_per1000"] + half_width

    df["estimate_type"] = "proxy"
    df["estimate_source"] = (
        "Deprivation-index-calibrated proxy (NOT PDHS-derived). "
        "See docs/LIMITATIONS.md."
    )

    out_cols = [
        "district_key",
        "province",
        "population_2017",
        "population_under5",
        "deprivation_index",
        "mortality_estimate_per1000",
        "mortality_lower95",
        "mortality_upper95",
        "estimate_type",
        "estimate_source",
    ]
    out = df[out_cols].copy()

    out_path = OUT_DIR / "district_mortality_estimate.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    print("\nDistribution check:")
    print(out["mortality_estimate_per1000"].describe())

    print("\nTop 10 highest estimated risk:")
    top = out.nlargest(10, "mortality_estimate_per1000")[
        ["district_key", "mortality_estimate_per1000", "mortality_lower95", "mortality_upper95"]
    ]
    print(top.to_string(index=False))

    print("\n*** REMINDER: This is a calibrated PROXY, not a DHS-derived  ***")
    print("*** mortality estimate. See docs/LIMITATIONS.md before using  ***")
    print("*** this output for any real decision-making.                 ***")


if __name__ == "__main__":
    main()
