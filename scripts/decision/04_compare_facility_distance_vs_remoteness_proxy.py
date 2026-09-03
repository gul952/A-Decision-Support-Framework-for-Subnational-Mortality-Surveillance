"""
04_compare_facility_distance_vs_remoteness_proxy.py

Layer 4 (Decision Engine) -- empirical comparison of the new real
facility-distance covariate (scripts/features/02_build_facility_distance.py)
against the existing remoteness_proxy STOPGAP, per the documented plan
in docs/LIMITATIONS.md Sec 5: add the new covariate ALONGSIDE the
existing one first, then let this comparison -- not assumption --
decide whether/how it should change the decision engine.

Note: `norm_geographic_accessibility_proxy` is INVERTED for
facility_distance_km relative to remoteness_proxy, because higher
remoteness_proxy = more remote (worse access), while higher
facility_distance_km ALSO = more remote (worse access) -- both point
the same direction (higher = worse), so no sign flip is actually
needed. Confirmed by construction: remoteness_proxy = 1 - norm(log(density)),
higher for LOWER density (more remote); facility_distance_km is a raw
distance, higher = farther = more remote. Both normalized the same way
(min-max, no inversion) is correct.

Does NOT modify the main pipeline's output files
(district_priority_scores.csv keeps using remoteness_proxy, unchanged)
-- this is a side-by-side diagnostic only.

Output:
    data/processed/decision/facility_vs_remoteness_comparison.csv
    Printed summary for docs/LIMITATIONS.md / paper Results section.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "prioritization_engine",
    Path(__file__).resolve().parent / "01_prioritization_engine.py",
)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)

SAE_PATH = DATA_PROCESSED / "models" / "hierarchical_hazard_sae_results.csv"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_PATH = DATA_PROCESSED / "decision" / "facility_vs_remoteness_comparison.csv"

TOP_N = 20


def load_data_with_facility_distance() -> pd.DataFrame:
    sae = pd.read_csv(SAE_PATH)
    feat = pd.read_csv(FEATURES_PATH)[
        [
            "district_key",
            "population_2017",
            "remoteness_proxy",
            "facility_distance_km",
            "low_osm_facility_coverage",
        ]
    ]
    df = sae.merge(feat, on="district_key", how="inner")
    return df


def compute_scores_with_facility_distance(df: pd.DataFrame) -> pd.DataFrame:
    """Same weights/logic as 01_prioritization_engine.py's default,
    but with facility_distance_km substituted for remoteness_proxy in
    the geographic-accessibility component."""
    df = df.copy()
    w = pe.DEFAULT_WEIGHTS
    df["norm_mortality_risk"] = pe.minmax_normalize(df["u5mr_posterior_mean"])
    df["norm_uncertainty"] = pe.minmax_normalize(df["ci_width"])
    df["norm_geographic_accessibility_proxy"] = pe.minmax_normalize(
        df["facility_distance_km"]
    )
    df["norm_population"] = pe.minmax_normalize(df["population_2017"])
    df["priority_score"] = (
        w["mortality_risk"] * df["norm_mortality_risk"]
        + w["uncertainty"] * df["norm_uncertainty"]
        + w["geographic_accessibility_proxy"] * df["norm_geographic_accessibility_proxy"]
        + w["population"] * df["norm_population"]
    )
    df["rank"] = df["priority_score"].rank(method="min", ascending=False).astype(int)
    return df


def main():
    df = load_data_with_facility_distance()

    default_scores = pe.compute_priority_scores(df)  # uses remoteness_proxy
    facility_scores = compute_scores_with_facility_distance(df)  # uses facility_distance_km

    default_top20 = set(
        default_scores.nsmallest(TOP_N, "rank")["district_key"]
    )
    facility_top20 = set(
        facility_scores.nsmallest(TOP_N, "rank")["district_key"]
    )

    overlap = default_top20 & facility_top20
    jaccard = len(overlap) / len(default_top20 | facility_top20)

    print(f"=== Comparison: remoteness_proxy vs. facility_distance_km ===")
    print(f"(default weights 40/30/20/10, same as main pipeline)\n")
    print(f"Top-{TOP_N} overlap (Jaccard): {jaccard:.3f}")
    print(f"Districts in BOTH top-20: {len(overlap)}/{TOP_N}")
    print(f"Districts ONLY in remoteness_proxy top-20: "
          f"{sorted(default_top20 - facility_top20)}")
    print(f"Districts ONLY in facility_distance_km top-20: "
          f"{sorted(facility_top20 - default_top20)}")

    # Province breakdown for both
    default_top20_df = default_scores.nsmallest(TOP_N, "rank")
    facility_top20_df = facility_scores.nsmallest(TOP_N, "rank")
    print(f"\nBalochistan count in remoteness_proxy top-20: "
          f"{(default_top20_df['province'] == 'Balochistan').sum()}")
    print(f"Balochistan count in facility_distance_km top-20: "
          f"{(facility_top20_df['province'] == 'Balochistan').sum()}")

    # How many of the facility-based top-20 are low-OSM-coverage districts?
    # (a coverage-bias sanity flag -- if most of the "high priority by
    # facility distance" list is just under-mapped districts, that's a
    # data-artifact result, not a genuine access finding)
    n_low_cov_in_facility_top20 = facility_top20_df["low_osm_facility_coverage"].sum()
    print(f"\nOf the facility_distance_km top-20, "
          f"{int(n_low_cov_in_facility_top20)}/{TOP_N} are "
          f"low_osm_facility_coverage districts (mapping-bias caution flag).")

    comparison = default_scores[["district_key", "province", "rank", "priority_score"]].rename(
        columns={"rank": "rank_remoteness_proxy", "priority_score": "score_remoteness_proxy"}
    ).merge(
        facility_scores[["district_key", "rank", "priority_score", "low_osm_facility_coverage"]].rename(
            columns={"rank": "rank_facility_distance", "priority_score": "score_facility_distance"}
        ),
        on="district_key",
    )
    comparison["rank_change"] = (
        comparison["rank_remoteness_proxy"] - comparison["rank_facility_distance"]
    )
    comparison.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
