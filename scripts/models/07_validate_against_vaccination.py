"""
07_validate_against_vaccination.py

Layer 3/Validation -- reproduces the mortality-model-vs-vaccination-
coverage comparison documented in docs/LIMITATIONS.md Sec 10a. See
that section for full interpretation; this script exists so the
correlation figures cited there are independently re-runnable, not
just narrated.

Uses district_features.csv (published) rather than the standalone
gitignored district_vaccination_coverage.csv, since the former is
what any external user of this repo actually has access to.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED

SAE_PATH = DATA_PROCESSED / "models" / "hierarchical_hazard_sae_results.csv"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"

MIN_SAMPLE_FOR_ADEQUATE = 10  # districts with fewer than this many sampled
                                # 12-23mo children are treated as too thin
                                # for the "adequately sampled" subset check


def main():
    sae = pd.read_csv(SAE_PATH)
    feat = pd.read_csv(FEATURES_PATH)[
        [
            "district_key",
            "n_children_12_23mo", "pct_fully_vaccinated", "low_vaccination_sample",
        ]
    ]
    merged = sae.merge(feat, on="district_key", how="inner")
    merged = merged.dropna(subset=["pct_fully_vaccinated"])

    print(f"Districts with both mortality estimate and vaccination data: {len(merged)}")

    r, p = stats.pearsonr(merged["u5mr_posterior_mean"], merged["pct_fully_vaccinated"])
    rho, p_s = stats.spearmanr(merged["u5mr_posterior_mean"], merged["pct_fully_vaccinated"])
    print(f"\nAll districts (n={len(merged)}):")
    print(f"  Pearson r  = {r:.3f} (p={p:.4f})")
    print(f"  Spearman rho = {rho:.3f} (p={p_s:.4f})")

    adequate = merged[merged["n_children_12_23mo"] >= MIN_SAMPLE_FOR_ADEQUATE]
    r2, p2 = stats.pearsonr(adequate["u5mr_posterior_mean"], adequate["pct_fully_vaccinated"])
    print(f"\nDistricts with n_children_12_23mo >= {MIN_SAMPLE_FOR_ADEQUATE} "
          f"(n={len(adequate)}):")
    print(f"  Pearson r  = {r2:.3f} (p={p2:.4f})")

    feat_pop = pd.read_csv(FEATURES_PATH)[["district_key", "population_2017"]]
    merged = merged.merge(feat_pop, on="district_key", how="left")

    prov_agg = merged.groupby("province").apply(
        lambda g: pd.Series({
            "mean_u5mr": np.average(
                g["u5mr_posterior_mean"],
                weights=g["population_2017"],
            ),
            "mean_fully_vacc": np.average(
                g["pct_fully_vaccinated"], weights=g["n_children_12_23mo"]
            ),
            "n_districts": len(g),
        }),
        include_groups=False,
    ).reset_index()
    print(f"\nProvince-level aggregation (n={len(prov_agg)} provinces):")
    print(prov_agg.to_string(index=False))
    if len(prov_agg) > 2:
        r3, p3 = stats.pearsonr(prov_agg["mean_u5mr"], prov_agg["mean_fully_vacc"])
        print(f"\n  Province-level Pearson r = {r3:.3f} (p={p3:.4f}, "
              f"not statistically powered with only {len(prov_agg)} provinces)")

    print(
        "\nInterpretation: see docs/LIMITATIONS.md Sec 10a. Summary: no "
        "significant district-level correlation, most likely due to thin "
        "per-district vaccination samples (median ~13 children) rather than "
        "a finding about the mortality model's validity. Reported as an "
        "honest null/mixed result, not adjusted or reframed as confirmatory."
    )


if __name__ == "__main__":
    main()
