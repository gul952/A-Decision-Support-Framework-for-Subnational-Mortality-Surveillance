"""
02_sensitivity_analysis.py

Layer 4 (Decision Engine) -- sensitivity analysis and robustness checks.

Per the project spec: "Don't simply report RMSE... Evaluate sensitivity
analysis... alternative weighting... robustness checks."

This script makes the decision engine's dependence on its weighting
scheme fully transparent, including surfacing a real finding from
development: with the DEFAULT weights, Balochistan dominates the top-20
list (17/20 districts) largely because remoteness_proxy (a population-
density inverse, itself a STOPGAP for real travel-time/facility data --
see docs/LIMITATIONS.md) rates Balochistan's sparsely-populated
districts as having the worst health access almost by construction.
This is exactly the kind of dependency a decision-support tool must
show, not hide -- a policymaker using this framework needs to know
whether "Balochistan needs surveillance first" is a robust finding or
an artifact of one proxy component's weighting.

Analyses:
    1. Weight perturbation: re-rank under several alternative weight
       configurations (mortality-only, access-only, equal-weight,
       uncertainty-only) and report how much the top-20 list changes
       (Jaccard overlap with the default ranking).
    2. Leave-one-component-out: remove each of the 4 components in turn
       and see how much the ranking shifts -- quantifies each
       component's actual influence on the final list.
    3. Province sensitivity: with remoteness_proxy removed entirely,
       does Balochistan still dominate? (tests whether the dominance is
       driven by mortality risk, which would be a more defensible
       finding, or primarily by the access proxy, which would not be).

Output:
    data/processed/decision/sensitivity_weight_scenarios.csv
    data/processed/decision/sensitivity_component_influence.csv
    docs/SENSITIVITY_FINDINGS.md (human-readable summary)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, DOCS_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "prioritization_engine",
    Path(__file__).resolve().parent / "01_prioritization_engine.py",
)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)

OUT_DIR = DATA_PROCESSED / "decision"

SCENARIOS = {
    "default (40/30/20/10)": {
        "mortality_risk": 0.40, "uncertainty": 0.30,
        "geographic_accessibility_proxy": 0.20, "population": 0.10,
    },
    "mortality_only": {
        "mortality_risk": 1.00, "uncertainty": 0.0,
        "geographic_accessibility_proxy": 0.0, "population": 0.0,
    },
    "access_only": {
        "mortality_risk": 0.0, "uncertainty": 0.0,
        "geographic_accessibility_proxy": 1.00, "population": 0.0,
    },
    "uncertainty_only": {
        "mortality_risk": 0.0, "uncertainty": 1.00,
        "geographic_accessibility_proxy": 0.0, "population": 0.0,
    },
    "equal_weight (25/25/25/25)": {
        "mortality_risk": 0.25, "uncertainty": 0.25,
        "geographic_accessibility_proxy": 0.25, "population": 0.25,
    },
    "no_access_component (50/50/0/0)": {
        "mortality_risk": 0.50, "uncertainty": 0.50,
        "geographic_accessibility_proxy": 0.0, "population": 0.0,
    },
    "population_weighted (20/20/20/40)": {
        "mortality_risk": 0.20, "uncertainty": 0.20,
        "geographic_accessibility_proxy": 0.20, "population": 0.40,
    },
}


def jaccard_overlap(list_a: set, list_b: set) -> float:
    if not list_a and not list_b:
        return 1.0
    return len(list_a & list_b) / len(list_a | list_b)


def main():
    print("Loading data...")
    df = pe.load_data()

    print("\n=== Scenario 1: Weight perturbation ===")
    default_scored = pe.compute_priority_scores(df, SCENARIOS["default (40/30/20/10)"])
    default_top20 = set(default_scored.nsmallest(20, "rank")["district_key"])

    scenario_rows = []
    for name, weights in SCENARIOS.items():
        scored = pe.compute_priority_scores(df, weights)
        top20 = set(scored.nsmallest(20, "rank")["district_key"])
        overlap = jaccard_overlap(default_top20, top20)
        n_balochistan = scored.nsmallest(20, "rank")["province"].eq("Balochistan").sum()

        scenario_rows.append(
            {
                "scenario": name,
                "weights": str(weights),
                "jaccard_overlap_with_default_top20": round(overlap, 3),
                "n_balochistan_in_top20": n_balochistan,
                "top5_districts": ", ".join(
                    scored.nsmallest(5, "rank")["district_key"].str.replace(" DISTRICT", "").tolist()
                ),
            }
        )
        print(f"\n  {name}:")
        print(f"    Jaccard overlap with default top-20: {overlap:.2f}")
        print(f"    Balochistan districts in top-20: {n_balochistan}/20")
        print(f"    Top 5: {scenario_rows[-1]['top5_districts']}")

    scenario_df = pd.DataFrame(scenario_rows)
    scenario_path = OUT_DIR / "sensitivity_weight_scenarios.csv"
    scenario_df.to_csv(scenario_path, index=False)
    print(f"\nWrote: {scenario_path}")

    print("\n=== Scenario 2: Leave-one-component-out influence ===")
    components = ["mortality_risk", "uncertainty", "geographic_accessibility_proxy", "population"]
    influence_rows = []
    for leave_out in components:
        adjusted_weights = {k: v for k, v in SCENARIOS["default (40/30/20/10)"].items()}
        removed_weight = adjusted_weights[leave_out]
        adjusted_weights[leave_out] = 0.0
        # redistribute removed weight proportionally across remaining components
        remaining = {k: v for k, v in adjusted_weights.items() if k != leave_out}
        remaining_sum = sum(remaining.values())
        for k in remaining:
            adjusted_weights[k] = remaining[k] + removed_weight * (remaining[k] / remaining_sum)

        scored = pe.compute_priority_scores(df, adjusted_weights)
        top20 = set(scored.nsmallest(20, "rank")["district_key"])
        overlap = jaccard_overlap(default_top20, top20)

        influence_rows.append(
            {
                "component_removed": leave_out,
                "original_weight": SCENARIOS["default (40/30/20/10)"][leave_out],
                "jaccard_overlap_with_full_model": round(overlap, 3),
                "influence": round(1 - overlap, 3),  # higher = more influential
            }
        )
        print(
            f"  Removing '{leave_out}' (weight={SCENARIOS['default (40/30/20/10)'][leave_out]}): "
            f"top-20 overlap drops to {overlap:.2f} (influence score: {1-overlap:.2f})"
        )

    influence_df = pd.DataFrame(influence_rows).sort_values("influence", ascending=False)
    influence_path = OUT_DIR / "sensitivity_component_influence.csv"
    influence_df.to_csv(influence_path, index=False)
    print(f"\nWrote: {influence_path}")

    print("\n=== Scenario 3: Is Balochistan dominance driven by access proxy or mortality risk? ===")
    no_access = pe.compute_priority_scores(df, SCENARIOS["no_access_component (50/50/0/0)"])
    n_baloch_no_access = no_access.nsmallest(20, "rank")["province"].eq("Balochistan").sum()
    n_baloch_default = default_scored.nsmallest(20, "rank")["province"].eq("Balochistan").sum()
    print(f"  Balochistan districts in top-20, DEFAULT weights (incl. access proxy): {n_baloch_default}/20")
    print(f"  Balochistan districts in top-20, access proxy REMOVED (mortality+uncertainty only): {n_baloch_no_access}/20")

    finding = (
        "still dominant even without the access proxy -- suggesting the finding "
        "is at least partly robust to that proxy's weaknesses"
        if n_baloch_no_access >= n_baloch_default * 0.6
        else "substantially reduced once the access proxy is removed -- suggesting "
        "Balochistan's dominance in the default ranking is heavily driven by "
        "remoteness_proxy (a population-density stopgap, not real travel-time "
        "data), and should be reported cautiously"
    )
    print(f"\n  FINDING: Balochistan's dominance is {finding}.")

    # write human-readable summary
    summary_md = f"""# Sensitivity Analysis Findings

Generated by `scripts/decision/02_sensitivity_analysis.py`.

## Key finding: Balochistan dominance under default weights

With the default 40/30/20/10 weighting (mortality risk / uncertainty /
health access deficit / population), **{n_baloch_default}/20** of the
top-priority districts are in Balochistan. This is a real result, not
a display bug -- but it warrants a specific caveat before being
presented as a policy recommendation:

- With the health-access-deficit component REMOVED entirely (weights
  redistributed to mortality risk 50% / uncertainty 50%), Balochistan
  still accounts for **{n_baloch_no_access}/20** top-priority districts.
- **Interpretation: {finding}.**

This matters because `geographic_accessibility_proxy` is currently built from
`remoteness_proxy`, a population-density-inverse STOPGAP (see
`docs/LIMITATIONS.md`) rather than real travel-time or facility-location
data. Balochistan is Pakistan's largest and most sparsely populated
province, so this proxy rates it as having poor access almost by
construction. The finding above tells us how much of Balochistan's
apparent priority survives that proxy's removal.

## Component influence ranking (leave-one-out)

Components ranked by how much removing them changes the top-20 list
(1 - Jaccard overlap with the full default model):

{influence_df.to_markdown(index=False)}

Note: with only 20 districts in the comparison set, the overlap metric
is coarse -- it can only take values in increments of 1/20 (since it
counts shared districts out of a fixed-size list), so two components
producing numerically identical or very close influence scores is a
real possibility and does not by itself indicate a computation error.
What matters is the ranking (which components matter most/least), not
the precision of the numeric gap between adjacent scores.

## Weight scenario comparison

{scenario_df.to_markdown(index=False)}

## How to read this table

`jaccard_overlap_with_default_top20` = the fraction of districts shared
between a scenario's top-20 and the default weighting's top-20 (1.0 =
identical lists, 0.0 = no districts in common). Low overlap for very
different weight schemes (e.g. `access_only` vs `mortality_only`) is
expected and healthy -- it shows the components are measuring genuinely
different things, not all pointing to the same districts by construction.
"""
    summary_path = DOCS_DIR / "SENSITIVITY_FINDINGS.md"
    summary_path.write_text(summary_md)
    print(f"\nWrote: {summary_path}")


if __name__ == "__main__":
    main()
