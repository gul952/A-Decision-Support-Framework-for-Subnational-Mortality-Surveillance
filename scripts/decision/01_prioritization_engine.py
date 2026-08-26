"""
01_prioritization_engine.py

Layer 4 (Decision Engine) -- this is what turns a mortality model into
a planning tool, per the project's core philosophy: "If Pakistan can
only improve surveillance in N districts next year, which N should
they choose?"

Combines four normalized components into a single Priority Score:
    40% estimated mortality risk         (u5mr_posterior_mean, from Layer 3)
    30% data/estimate uncertainty        (ci_width, from Layer 3 -- districts
                                           we know LEAST about are themselves
                                           a surveillance priority, since you
                                           cannot manage what you cannot measure)
    20% population-density-based         (remoteness_proxy, from Layer 2 --
        geographic accessibility proxy    this is NOT actual healthcare
                                           access. It is a STOPGAP built
                                           purely from population density
                                           (sparse population -> assumed
                                           less accessible), used only
                                           because real facility-location
                                           and travel-time data was not
                                           available for this project. It
                                           does not measure road quality,
                                           hospital proximity, terrain, or
                                           any other real access barrier.
                                           See docs/LIMITATIONS.md.
    10% population                       (population_2017, from Layer 1 --
                                           larger at-risk populations get a
                                           modest boost, reflecting that fixed
                                           surveillance capacity reaches more
                                           people in a populous district)

These are the exact weights specified in the original project design.
They are a transparent, literature-informed STARTING assumption, not a
fitted or "correct" answer -- the whole point of the decision-engine
layer is to make that weighting visible and adjustable (see
02_sensitivity_analysis.py and the dashboard's weight sliders), not to
claim one true ranking.

Output:
    data/processed/decision/district_priority_scores.csv
        (district_key, province, priority_score, rank, all four
         normalized components, plus raw values for transparency)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED

SAE_PATH = DATA_PROCESSED / "models" / "hierarchical_hazard_sae_results.csv"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_DIR = DATA_PROCESSED / "decision"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Default weights -- exactly as specified in the original project design.
DEFAULT_WEIGHTS = {
    "mortality_risk": 0.40,
    "uncertainty": 0.30,
    "geographic_accessibility_proxy": 0.20,
    "population": 0.10,
}


def minmax_normalize(s: pd.Series) -> pd.Series:
    rng = s.max() - s.min()
    if rng == 0:
        return pd.Series(0.5, index=s.index)  # degenerate case: no variation
    return (s - s.min()) / rng


def load_data() -> pd.DataFrame:
    sae = pd.read_csv(SAE_PATH)
    feat = pd.read_csv(FEATURES_PATH)[
        ["district_key", "population_2017", "remoteness_proxy"]
    ]
    df = sae.merge(feat, on="district_key", how="inner")
    return df


def compute_priority_scores(
    df: pd.DataFrame, weights: dict = None
) -> pd.DataFrame:
    """
    Compute the composite priority score for a given weight configuration.
    Called both for the default weights (main pipeline output) and
    interactively (dashboard sliders / sensitivity analysis) with the
    same underlying normalized components, so results are always
    consistent with how the default score was built.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    assert abs(sum(weights.values()) - 1.0) < 1e-6, "Weights must sum to 1.0"

    df = df.copy()
    df["norm_mortality_risk"] = minmax_normalize(df["u5mr_posterior_mean"])
    df["norm_uncertainty"] = minmax_normalize(df["ci_width"])
    df["norm_geographic_accessibility_proxy"] = minmax_normalize(df["remoteness_proxy"])
    df["norm_population"] = minmax_normalize(df["population_2017"])

    df["priority_score"] = (
        weights["mortality_risk"] * df["norm_mortality_risk"]
        + weights["uncertainty"] * df["norm_uncertainty"]
        + weights["geographic_accessibility_proxy"] * df["norm_geographic_accessibility_proxy"]
        + weights["population"] * df["norm_population"]
    )

    df["rank"] = df["priority_score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank")


def add_uncertainty_variants(df: pd.DataFrame) -> pd.DataFrame:
    """
    The default "uncertainty" component (raw ci_width, in per-1,000
    units) has a real limitation: it conflates absolute uncertainty
    with the district's baseline risk level -- a district with U5MR
    around 200 will mechanically tend to have a wider absolute CI than
    one around 40, even at similar RELATIVE precision. This function
    adds an alternative uncertainty measure so the decision engine
    (and a paper's sensitivity analysis) is not dependent on a single,
    somewhat crude uncertainty metric:

        relative_uncertainty = ci_width / u5mr_posterior_mean
            (coefficient-of-variation style measure -- how uncertain is
            this estimate RELATIVE to its own magnitude, not just in
            absolute per-1,000 units)

    A second, more genuinely decision-relevant measure --
    prob_exceeds_national_median, the posterior probability that a
    district's true U5MR exceeds the national median -- is computed
    separately in scripts/decision/03_ranking_stability.py, since it
    requires re-deriving per-sample U5MR from the full MCMC trace
    (a heavier operation kept out of this script's default fast path).
    """
    df = df.copy()
    df["relative_uncertainty"] = df["ci_width"] / df["u5mr_posterior_mean"].replace(0, np.nan)
    return df


def recommend_for_budget(df: pd.DataFrame, n_districts: int) -> pd.DataFrame:
    """Return the top-N districts under a given surveillance-expansion
    budget (e.g. 'if we can only fund 20 districts, which 20?')."""
    return df.nsmallest(n_districts, "rank")[
        ["rank", "district_key", "province", "priority_score",
         "u5mr_posterior_mean", "ci_width", "had_direct_data"]
    ]


def main():
    print("Loading SAE results + features...")
    df = load_data()
    print(f"  {len(df)} districts")

    print(f"\nComputing priority scores with default weights: {DEFAULT_WEIGHTS}")
    scored = compute_priority_scores(df, DEFAULT_WEIGHTS)
    scored = add_uncertainty_variants(scored)

    out_path = OUT_DIR / "district_priority_scores.csv"
    scored.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    print("\n=== Top 20 priority districts (default weights) ===")
    top20 = recommend_for_budget(scored, 20)
    print(top20.to_string(index=False))

    print("\n=== Budget scenarios ===")
    for n in [5, 10, 20, 50]:
        subset = recommend_for_budget(scored, n)
        n_no_direct_data = (~subset["had_direct_data"]).sum()
        n_provinces = subset["province"].nunique()
        print(
            f"  Top {n:>2} districts: span {n_provinces} provinces, "
            f"{n_no_direct_data} currently have ZERO direct DHS coverage "
            "(i.e. this framework is recommending surveillance expansion "
            "precisely where current data is thinnest)."
        )


if __name__ == "__main__":
    main()
