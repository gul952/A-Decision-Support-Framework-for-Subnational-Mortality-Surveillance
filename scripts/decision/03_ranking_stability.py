"""
03_ranking_stability.py

Layer 4 (Decision Engine) -- addresses external review feedback items
7 and 11: "test ranking stability" and "quantify uncertainty around
the top 20" rather than presenting a single point-estimate ranking as
if it were certain.

Two complementary stability analyses:

1. POSTERIOR RANKING STABILITY: using the hierarchical hazard model's
   full MCMC trace (not just its posterior mean), recompute each
   district's U5MR-based rank for EVERY posterior draw, then report
   what fraction of draws place each district in the top 20. A
   district that is "#1" only because of where the posterior MEAN
   happens to fall, but is highly variable draw-to-draw, is a very
   different finding from a district that is robustly top-20 across
   nearly all posterior uncertainty. This also yields
   prob_exceeds_national_median (the posterior probability a
   district's true U5MR exceeds the national median) -- a genuinely
   decision-relevant confidence measure, not just raw CI width.

2. WEIGHT-PERTURBATION RANKING STABILITY: reuses
   scripts/decision/02_sensitivity_analysis.py's weight scenarios to
   report, for the DEFAULT-weight top 20, what fraction of those
   alternative weight scenarios also place each district in their own
   top 20 -- i.e., is a district's high rank an artifact of the
   specific 40/30/20/10 weighting, or does it hold up under a range of
   reasonable alternative weightings?

Output:
    data/processed/decision/ranking_stability_posterior.csv
    data/processed/decision/ranking_stability_weights.csv
    docs/RANKING_STABILITY_FINDINGS.md
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, MODELS_DIR, DOCS_DIR, ROOT

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

pe_spec = importlib.util.spec_from_file_location(
    "prioritization_engine", Path(__file__).resolve().parent / "01_prioritization_engine.py"
)
pe = importlib.util.module_from_spec(pe_spec)
pe_spec.loader.exec_module(pe)

sens_spec = importlib.util.spec_from_file_location(
    "sensitivity_analysis", Path(__file__).resolve().parent / "02_sensitivity_analysis.py"
)
sens = importlib.util.module_from_spec(sens_spec)
sens_spec.loader.exec_module(sens)

TRACE_PATH = MODELS_DIR / "hierarchical_hazard_sae_trace.pkl"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_DIR = DATA_PROCESSED / "decision"

AGE_SEGMENTS = [(0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 36), (36, 48), (48, 60)]


def rebuild_grid_district_segment_order() -> pd.DataFrame:
    """
    Reconstructs the exact (district_key, segment_idx) row order the
    hazard model's `obs` dimension was built with, by re-running the
    same grid-construction logic as
    scripts/models/04_hierarchical_hazard_sae.py. This MUST match
    exactly, or ranking stability results will suffer from the same
    ordering bug that was found and fixed in that script -- see its
    reconstruct_u5mr_from_hazards() docstring for the full incident.
    """
    hazard_spec = importlib.util.spec_from_file_location(
        "hierarchical_hazard_sae",
        Path(__file__).resolve().parents[1] / "models" / "04_hierarchical_hazard_sae.py",
    )
    hazard_mod = importlib.util.module_from_spec(hazard_spec)
    hazard_spec.loader.exec_module(hazard_mod)
    return hazard_mod.build_district_segment_grid()


def compute_per_draw_u5mr(trace, grid: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a (n_districts, n_samples) matrix of U5MR values, one per
    posterior draw, reconstructed via the same actuarial chaining as
    the main model script. Rows are indexed by district_key.
    """
    p_posterior = trace.posterior["p"]
    p_flat = p_posterior.stack(sample=("chain", "draw")).values
    p_flat = np.clip(p_flat, 0, 1)
    n_samples = p_flat.shape[-1]

    grid_ordered = grid.reset_index(drop=True)
    district_order = grid_ordered["district_key"].values
    segment_order = grid_ordered["segment_idx"].values
    unique_districts = pd.unique(district_order)

    u5mr_matrix = np.zeros((len(unique_districts), n_samples))
    for i, district in enumerate(unique_districts):
        rows = np.where(district_order == district)[0]
        rows_sorted = rows[np.argsort(segment_order[rows])]
        survival = np.ones(n_samples)
        for row in rows_sorted:
            survival *= (1 - p_flat[row, :])
        u5mr_matrix[i, :] = (1 - survival) * 1000

    return pd.DataFrame(u5mr_matrix, index=unique_districts)


def posterior_ranking_stability(u5mr_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    For each posterior draw (column), rank districts by U5MR and check
    top-N membership. Aggregate across draws to get, per district, the
    fraction of posterior draws where it lands in the top N -- this is
    a direct, sampling-based measure of ranking robustness under the
    model's own uncertainty, not just a point-estimate ranking.
    """
    n_samples = u5mr_df.shape[1]
    in_top_n_counts = pd.Series(0, index=u5mr_df.index)

    national_median_per_draw = u5mr_df.median(axis=0)
    prob_exceeds_median = pd.Series(0.0, index=u5mr_df.index)

    for col in u5mr_df.columns:
        draw = u5mr_df[col]
        top_n_districts = draw.nlargest(top_n).index
        in_top_n_counts.loc[top_n_districts] += 1
        prob_exceeds_median += (draw > national_median_per_draw[col]).astype(float)

    result = pd.DataFrame(
        {
            "district_key": u5mr_df.index,
            "pct_draws_in_top20": 100 * in_top_n_counts.values / n_samples,
            "prob_exceeds_national_median": prob_exceeds_median.values / n_samples,
            "posterior_mean_u5mr": u5mr_df.mean(axis=1).values,
            "posterior_rank_by_mean": u5mr_df.mean(axis=1).rank(ascending=False, method="min").values,
        }
    )
    return result.sort_values("posterior_rank_by_mean")


def weight_perturbation_stability(top_n: int = 20) -> pd.DataFrame:
    """
    For the default-weight top-N districts, check what fraction of
    alternative weight scenarios (from 02_sensitivity_analysis.py's
    SCENARIOS dict) ALSO place each district in their own top-N -- a
    district robust to reasonable weight choices is a stronger finding
    than one that's only top-N under the exact default weights.
    """
    df = pe.load_data()
    default_scored = pe.compute_priority_scores(df, sens.SCENARIOS["default (40/30/20/10)"])
    default_top_n = default_scored.nsmallest(top_n, "rank")["district_key"].tolist()

    membership_counts = pd.Series(0, index=default_top_n)
    n_scenarios = len(sens.SCENARIOS)

    for name, weights in sens.SCENARIOS.items():
        scored = pe.compute_priority_scores(df, weights)
        scenario_top_n = set(scored.nsmallest(top_n, "rank")["district_key"])
        for d in default_top_n:
            if d in scenario_top_n:
                membership_counts[d] += 1

    result = pd.DataFrame(
        {
            "district_key": default_top_n,
            "pct_weight_scenarios_in_top20": 100 * membership_counts.values / n_scenarios,
        }
    )
    result["default_rank"] = result["district_key"].map(
        default_scored.set_index("district_key")["rank"]
    )
    return result.sort_values("default_rank")


def main():
    print("Rebuilding district-segment grid (must match model's obs order exactly)...")
    grid = rebuild_grid_district_segment_order()

    print(f"Loading MCMC trace from {TRACE_PATH}...")
    with open(TRACE_PATH, "rb") as f:
        trace = pickle.load(f)

    print("Reconstructing per-draw U5MR for all districts (this may take a moment)...")
    u5mr_df = compute_per_draw_u5mr(trace, grid)
    print(f"  {u5mr_df.shape[0]} districts x {u5mr_df.shape[1]} posterior draws")

    print("\nComputing posterior ranking stability (top 20)...")
    posterior_stability = posterior_ranking_stability(u5mr_df, top_n=20)
    posterior_path = OUT_DIR / "ranking_stability_posterior.csv"
    posterior_stability.to_csv(posterior_path, index=False)
    print(f"Wrote: {posterior_path}")
    print(posterior_stability.head(20).to_string(index=False))

    print("\nComputing weight-perturbation ranking stability (top 20)...")
    weight_stability = weight_perturbation_stability(top_n=20)
    weight_path = OUT_DIR / "ranking_stability_weights.csv"
    weight_stability.to_csv(weight_path, index=False)
    print(f"Wrote: {weight_path}")
    print(weight_stability.to_string(index=False))

    n_robust_posterior = (posterior_stability["pct_draws_in_top20"] >= 90).sum()
    n_robust_weights = (weight_stability["pct_weight_scenarios_in_top20"] >= 90).sum()

    findings = f"""# Ranking Stability Findings

Generated by `scripts/decision/03_ranking_stability.py`.

Addresses external review feedback: "Don't just say District X is #1
-- show whether it is robustly high-priority." A single point-estimate
ranking hides two very different situations: a district that is
top-priority across nearly all plausible parameter values and model
uncertainty, versus one that only looks top-priority because of where
a single posterior mean or a single weight choice happens to fall.

## Posterior (model uncertainty) ranking stability

For every one of the {u5mr_df.shape[1]} MCMC posterior draws, we
recomputed the full district ranking and checked top-20 membership.
`pct_draws_in_top20` is the fraction of draws where a district lands
in the top 20 by that draw's U5MR alone.

{posterior_stability.head(20).round(1).to_markdown(index=False)}

**{n_robust_posterior} of the top 20 districts (by posterior mean) are
in the top 20 in at least 90% of posterior draws** -- these are
robustly high-priority under the model's own uncertainty, not
artifacts of the posterior mean alone. Districts below that threshold
should be read with more caution: their point-estimate rank may not
survive resampling from the same model.

## Weight-perturbation ranking stability

For the default-weight (40/30/20/10) top 20, we checked what fraction
of the 7 alternative weight scenarios in
`docs/SENSITIVITY_FINDINGS.md` also place each district in their OWN
top 20.

{weight_stability.round(1).to_markdown(index=False)}

**{n_robust_weights} of the default top-20 districts remain in the
top 20 across at least 90% of alternative weight scenarios tested.**
This is a stricter and more informative claim than "District X is
ranked #1 under our chosen weights" -- it tells a reader whether that
ranking is a robust finding or sensitive to the specific (subjective)
weighting choice.

## How to use this in a paper

Report BOTH stability measures alongside any top-N list. A defensible
claim is closer to: "District X is in the top 20 under [pct_draws_in_top20]%
of posterior draws and [pct_weight_scenarios_in_top20]% of alternative
weight schemes tested" -- not simply "District X ranks #1."
"""
    findings_path = DOCS_DIR / "RANKING_STABILITY_FINDINGS.md"
    findings_path.write_text(findings)
    print(f"\nWrote: {findings_path}")


if __name__ == "__main__":
    main()
