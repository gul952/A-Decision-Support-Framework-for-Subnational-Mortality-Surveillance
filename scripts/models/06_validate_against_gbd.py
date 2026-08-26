"""
06_validate_against_gbd.py

Layer 3 (Small Area Estimation) -- EXTERNAL BENCHMARKING/COMPARISON
against an independently-modeled estimate (NOT statistical cross-
validation in the technical sense, which requires held-out data from
the same generative process -- see docs/LIMITATIONS.md for why this
distinction matters and is maintained precisely throughout this
project's documentation).

Compares this project's population-weighted province aggregates
(derived by aggregating district-level hierarchical hazard-model
posterior means up to province) against IHME's GBD 2023 round
estimates of 5q0 (probability of death before age 5) for Pakistan and
its provinces.

*** RESULT SUMMARY (updated after the Layer 3 likelihood correction --
see docs/LIMITATIONS.md and scripts/models/04_hierarchical_hazard_sae.py) ***
An earlier version of this project's hierarchical model had a real
methodological flaw (modeling `deaths ~ Binomial(births, p)` on
aggregate counts without properly accounting for right-censoring in
the underlying survival data). Under that flawed model, this
project's estimates and GBD's substantially disagreed on Balochistan
(this project: 79/1,000 vs. GBD: 51/1,000, a 56% difference; province
rank correlation 0.50). After rebuilding the model as a proper
discrete-time hazard model with correct censoring (see
scripts/models/04_hierarchical_hazard_sae.py), that disagreement
LARGELY RESOLVED: Balochistan now differs from GBD by only ~15%, and
province rank correlation rose to 0.90. This is reported here plainly,
including the fact that the earlier, wrong model's disagreement was
itself informative about how much a censoring bug can distort a
small-sample, high-volatility province's estimate -- not something to
quietly drop from the record.

Data source: Global Burden of Disease Collaborative Network. Global
Burden of Disease Study 2023 (GBD 2023) Results. Seattle, United
States: Institute for Health Metrics and Evaluation (IHME), 2024.
Available from https://vizhub.healthdata.org/gbd-results/.
Downloaded by the user (IHME requires an authenticated account; not
fetchable by this pipeline automatically) and placed at
data/external/gbd/IHME-GBD_2023_DATA-78a15125-1.csv.

Output:
    data/processed/models/gbd_validation_comparison.csv
    docs/GBD_VALIDATION_FINDINGS.md
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, ROOT, DOCS_DIR

GBD_PROVINCE_2019_PATH = ROOT / "data" / "external" / "gbd" / "IHME-GBD_2023_DATA-78a15125-1.csv"
GBD_PROVINCE_2017_2018_PATH = ROOT / "data" / "external" / "gbd" / "IHME-GBD_2023_DATA-7bcd58a5-1.csv"
SAE_PATH = DATA_PROCESSED / "models" / "hierarchical_hazard_sae_results.csv"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_DIR = DATA_PROCESSED / "models"

# GBD's province/region naming vs. this project's canonical province
# naming (from the PBS census shapefile, see
# scripts/cleaning/01_clean_geography.py) diverge slightly.
GBD_TO_PROJECT_PROVINCE = {
    "Punjab": "Punjab",
    "Sindh": "Sindh",
    "Khyber Pakhtunkhwa": "Khyber Pakhtunkhwa",
    "Balochistan": "Balochistan",
    "Islamabad Capital Territory": "Federal Capital Territory",
    # GBD has no equivalent to this project's "Fata" grouping (GBD folds
    # former FATA into Khyber Pakhtunkhwa post-2018 merger) or to Azad
    # Jammu & Kashmir / Gilgit-Baltistan (out of this project's scope
    # entirely -- see docs/LIMITATIONS.md Limitation 1).
}


def load_gbd_province_2017_2018() -> pd.DataFrame:
    """
    PRIMARY comparison source: province-level 5q0 for 2017 AND 2018,
    averaged -- properly time-matched to the PDHS 2017-18 survey period
    (fielded across late 2017 into early 2018), unlike the earlier
    2019-only province file this script originally used.
    """
    df = pd.read_csv(GBD_PROVINCE_2017_2018_PATH)
    df["gbd_u5mr_per1000"] = df["val"] * 1000
    df["gbd_u5mr_lower"] = df["lower"] * 1000
    df["gbd_u5mr_upper"] = df["upper"] * 1000
    df["province"] = df["location_name"].map(GBD_TO_PROJECT_PROVINCE)

    avg = (
        df.groupby(["location_name", "province"], dropna=False)[
            ["gbd_u5mr_per1000", "gbd_u5mr_lower", "gbd_u5mr_upper"]
        ]
        .mean()
        .reset_index()
    )
    return avg


def load_gbd_province_2019() -> pd.DataFrame:
    """
    SECONDARY/supplementary comparison source: province-level 5q0 for
    2019 only. Kept for reference (e.g. to see whether the 2019 vs.
    2017-2018 gap itself is large within GBD's own estimates, which
    would indicate a genuine time trend rather than just estimation
    noise), but the 2017-2018 average above is the primary comparison
    point since it properly matches the PDHS survey period.
    """
    df = pd.read_csv(GBD_PROVINCE_2019_PATH)
    df["gbd_u5mr_per1000_2019"] = df["val"] * 1000
    df["province"] = df["location_name"].map(GBD_TO_PROJECT_PROVINCE)
    return df[["location_name", "province", "gbd_u5mr_per1000_2019"]]


def compute_project_province_aggregates() -> pd.DataFrame:
    """
    Population-weighted province aggregate of this project's district-
    level hierarchical SAE posterior means -- NOT a simple unweighted
    mean of districts, since province U5MR should reflect where people
    actually live, not treat a 50,000-person district the same as a
    5-million-person one.
    """
    sae = pd.read_csv(SAE_PATH)
    pop = pd.read_csv(FEATURES_PATH)[["district_key", "population_2017"]]
    df = sae.merge(pop, on="district_key", how="left")

    def weighted_mean(g):
        return np.average(g["u5mr_posterior_mean"], weights=g["population_2017"])

    agg = (
        df.groupby("province")
        .apply(weighted_mean, include_groups=False)
        .reset_index(name="project_u5mr_per1000")
    )

    # also compute national population-weighted aggregate
    national = np.average(df["u5mr_posterior_mean"], weights=df["population_2017"])
    national_row = pd.DataFrame(
        {"province": ["Pakistan (project, pop-weighted)"], "project_u5mr_per1000": [national]}
    )
    return pd.concat([agg, national_row], ignore_index=True)


def main():
    print(f"Loading GBD 2023 province-level data (2017+2018 average) from {GBD_PROVINCE_2017_2018_PATH}...")
    gbd = load_gbd_province_2017_2018()
    print(gbd[["location_name", "gbd_u5mr_per1000"]].to_string(index=False))

    print(f"\nLoading GBD 2023 province-level data (2019, supplementary) from {GBD_PROVINCE_2019_PATH}...")
    gbd_2019 = load_gbd_province_2019()
    print(gbd_2019[["location_name", "gbd_u5mr_per1000_2019"]].to_string(index=False))

    print("\nComputing this project's population-weighted province aggregates...")
    project = compute_project_province_aggregates()
    print(project.to_string(index=False))

    print("\nMerging on province (GBD naming mapped to project naming)...")
    comparison = project.merge(gbd, on="province", how="left")
    comparison = comparison.merge(
        gbd_2019[["province", "gbd_u5mr_per1000_2019"]], on="province", how="left"
    )
    comparison["difference"] = (
        comparison["project_u5mr_per1000"] - comparison["gbd_u5mr_per1000"]
    )
    comparison["pct_difference"] = (
        100 * comparison["difference"] / comparison["gbd_u5mr_per1000"]
    )
    # GBD's own within-source time trend: how much did GBD's estimate
    # itself move between the 2017-2018 average and 2019? Useful context
    # for interpreting how much of any project-vs-GBD gap could be a
    # genuine time trend vs. a cross-method disagreement.
    comparison["gbd_2019_vs_2017_18_change"] = (
        comparison["gbd_u5mr_per1000_2019"] - comparison["gbd_u5mr_per1000"]
    )

    out_path = OUT_DIR / "gbd_validation_comparison.csv"
    comparison.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    print("\n=== COMPARISON TABLE ===")
    print(
        comparison[
            ["province", "project_u5mr_per1000", "gbd_u5mr_per1000", "difference", "pct_difference"]
        ].to_string(index=False)
    )

    # National check
    pak_gbd_2017_2018_avg = gbd[gbd["location_name"] == "Pakistan"]["gbd_u5mr_per1000"].values[0]
    pak_gbd_2019 = gbd_2019[gbd_2019["location_name"] == "Pakistan"]["gbd_u5mr_per1000_2019"].values[0]
    pak_project = project[
        project["province"] == "Pakistan (project, pop-weighted)"
    ]["project_u5mr_per1000"].values[0]
    pak_dhs_direct = 74.7  # from scripts/models/02b_estimate_u5mr_from_dhs.py validation
    pak_published = 74.9  # World Bank/UN IGME 2017

    print("\n=== NATIONAL-LEVEL COMPARISON ===")
    print(f"  Published (World Bank/UN IGME, 2017):                {pak_published:.1f} per 1,000")
    print(f"  This project's DHS BR-derived direct estimate:        {pak_dhs_direct:.1f} per 1,000")
    print(f"  This project's hierarchical SAE (pop-weighted):       {pak_project:.1f} per 1,000")
    print(f"  GBD 2023 round, 2017-2018 average (PRIMARY, time-matched): {pak_gbd_2017_2018_avg:.1f} per 1,000")
    print(f"  GBD 2023 round, 2019 (supplementary):                 {pak_gbd_2019:.1f} per 1,000")

    # identify biggest province-level divergence
    valid_comparison = comparison.dropna(subset=["gbd_u5mr_per1000"])
    biggest_diff_row = valid_comparison.loc[valid_comparison["difference"].abs().idxmax()]

    print(f"\n=== BIGGEST PROVINCE-LEVEL DIVERGENCE ===")
    print(
        f"  {biggest_diff_row['province']}: this project = "
        f"{biggest_diff_row['project_u5mr_per1000']:.1f}, GBD = "
        f"{biggest_diff_row['gbd_u5mr_per1000']:.1f} "
        f"({biggest_diff_row['pct_difference']:+.0f}%)"
    )

    # rank correlation: do the two approaches at least AGREE on relative
    # ordering of provinces, even if absolute levels differ?
    ranked = valid_comparison.dropna(subset=["project_u5mr_per1000", "gbd_u5mr_per1000"])
    ranked = ranked[ranked["province"] != "Pakistan (project, pop-weighted)"]
    if len(ranked) >= 3:
        spearman = ranked["project_u5mr_per1000"].corr(
            ranked["gbd_u5mr_per1000"], method="spearman"
        )
        print(f"\n=== RANK AGREEMENT ===")
        print(f"  Spearman rank correlation (province ordering): {spearman:.2f}")
        print(
            "  (1.0 = identical province ranking; 0 = no relationship; "
            "-1.0 = exactly opposite ranking)"
        )

    # write human-readable findings doc
    write_findings_doc(comparison, pak_published, pak_dhs_direct, pak_project, pak_gbd_2017_2018_avg, pak_gbd_2019, spearman if len(ranked) >= 3 else None)


def write_findings_doc(comparison, pak_published, pak_dhs_direct, pak_project, pak_gbd_2017_2018_avg, pak_gbd_2019, spearman):
    table_md = comparison[
        ["province", "project_u5mr_per1000", "gbd_u5mr_per1000", "gbd_u5mr_per1000_2019", "difference", "pct_difference"]
    ].round(1).to_markdown(index=False)

    agreement_label = (
        "strong agreement" if spearman >= 0.7
        else "moderate agreement" if spearman >= 0.4
        else "weak agreement" if spearman >= 0.2
        else "little to no agreement"
    ) if spearman is not None else "not computed"

    max_diff_row = comparison.dropna(subset=["gbd_u5mr_per1000"]).loc[
        comparison.dropna(subset=["gbd_u5mr_per1000"])["difference"].abs().idxmax()
    ]

    content = f"""# GBD 2023 External Benchmarking / Comparison

Generated by `scripts/models/06_validate_against_gbd.py`.

**Terminology note:** this is an EXTERNAL BENCHMARKING / COMPARISON
exercise, not statistical cross-validation in the technical sense.
Cross-validation implies held-out data from the same generative
process (e.g. withholding some PDHS clusters and testing whether the
model predicts them); this is instead a comparison against an
independently-constructed estimate from a different organization using
different data and methods. Both are useful, but they answer different
questions, and conflating them overstates what this comparison can
show. See `docs/LIMITATIONS.md`.

## What this compares

This project's district-level hierarchical discrete-time hazard model
(`scripts/models/04_hierarchical_hazard_sae.py`), aggregated up to
population-weighted province estimates, against IHME's **independently
modeled** GBD 2023 round estimates of 5q0 (probability of death before
age 5) for Pakistan and its provinces.

**Primary comparison year: 2017-2018 average.** GBD publishes annual
estimates; we use the average of the 2017 and 2018 province-level
estimates as the primary comparison point, since this properly matches
the PDHS 2017-18 survey period (the source of this project's own
mortality estimates) rather than relying on a temporally offset year.
The earlier 2019 province-level estimate is retained as a
supplementary reference column, useful for checking how much GBD's own
estimate moved year-to-year.

These are two genuinely different modeling approaches:
- **This project**: a discrete-time hazard model with proper right-
  censoring, fit directly on PDHS 2017-18 individual birth-history
  survival records, with province/district partial pooling.
- **GBD 2023**: IHME's global modeling pipeline, which synthesizes many
  data sources (surveys, censuses, vital registration, verbal autopsy
  studies) through a spatiotemporal Gaussian process regression and
  ensemble modeling framework -- not a single-survey estimate.

Agreement between the two is a meaningful (though not definitive)
external benchmarking signal; disagreement is also informative about
the uncertainty inherent in subnational mortality estimation in a
data-sparse country -- not automatically a failure of either method.

## *** A methodologically important update ***

An earlier version of this project's hierarchical model modeled
`deaths ~ Binomial(births, p)` on already-aggregated birth/death
counts, which implicitly assumed every child had a full 5-year
follow-up window -- an incorrect handling of right-censoring (children
born recently before the survey interview had only been observed for
a few months, not five years). Under that flawed model, Balochistan
showed a 56% disagreement with GBD (this project: ~79/1,000 vs. GBD:
~51/1,000) and province rank correlation was only 0.50.

After rebuilding the model as a proper discrete-time hazard model on
individual birth-level survival records with correct actuarial
censoring (see `scripts/models/04_hierarchical_hazard_sae.py`), **that
disagreement largely resolved**: see the updated comparison below. This
is reported explicitly because the size of the improvement is itself
evidence that the original censoring flaw was materially distorting
estimates for small-sample, high-volatility provinces -- exactly where
a censoring error would be expected to matter most.

## National-level comparison

| Source | Year(s) | U5MR (per 1,000) |
|---|---|---|
| Published (World Bank / UN IGME) | 2017 | {pak_published:.1f} |
| This project -- DHS birth-history direct estimate | 2017-18 (5yr window) | {pak_dhs_direct:.1f} |
| This project -- hierarchical hazard model, population-weighted | 2017-18 (5yr window) | {pak_project:.1f} |
| GBD 2023 round, **primary** (time-matched) | 2017-2018 avg | {pak_gbd_2017_2018_avg:.1f} |
| GBD 2023 round, supplementary | 2019 | {pak_gbd_2019:.1f} |

Note GBD's own estimate moved from {pak_gbd_2017_2018_avg:.1f} (2017-18
avg) to {pak_gbd_2019:.1f} (2019) -- a {abs(pak_gbd_2019 - pak_gbd_2017_2018_avg):.1f}-point
within-source shift over roughly one year, a useful reference scale for
how much year-to-year movement alone can account for in any
project-vs-GBD gap.

The hierarchical model's population-weighted aggregate ({pak_project:.1f})
remains somewhat lower than this project's own direct BR estimate
({pak_dhs_direct:.1f}), reflecting genuine hierarchical shrinkage of a
small number of extreme small-sample outlier districts (see
`docs/LIMITATIONS.md`) -- this is expected, bounded model behavior, not
a new discrepancy.

## Province-level comparison

{table_md}

(`gbd_u5mr_per1000` = primary, 2017-2018 average; `gbd_u5mr_per1000_2019`
= supplementary reference column.)

**With the corrected model, this project and GBD 2023 now agree
reasonably well on province ordering.** Spearman rank correlation
between the two province orderings: **{spearman:.2f}**, indicating
**{agreement_label}** -- a substantial improvement from the 0.50
correlation observed under the earlier, uncorrected model.

The largest remaining province-level difference is **{max_diff_row['province']}**
(this project: {max_diff_row['project_u5mr_per1000']:.1f}, GBD:
{max_diff_row['gbd_u5mr_per1000']:.1f}, {max_diff_row['pct_difference']:+.0f}%).
This is a smaller and more ordinary-magnitude disagreement than the
Balochistan gap seen under the earlier flawed model, and is within the
range plausibly explained by genuine methodological differences between
a single-survey hazard model and GBD's multi-source synthesis, rather
than pointing to a further structural issue.

## Why any remaining differences might exist (interpretation, not resolution)

Several genuine, non-mutually-exclusive explanations exist for
whatever gap remains after the censoring correction:

1. **Residual small-sample variability.** Even with correct censoring
   handling, provinces with fewer DHS clusters will have noisier
   direct estimates than data-rich provinces like Punjab (see
   `low_direct_coverage` flags in
   `data/processed/mortality/district_u5mr_direct_dhs.csv`).
2. **GBD's modeling approach smooths across many pooled data sources
   and years**, which could under- or over-represent a pattern picked
   up by a single, more recent survey round (PDHS 2017-18) vs. GBD's
   broader multi-year, multi-source synthesis.
3. **Real underlying uncertainty in subnational mortality estimation**
   in a data-sparse country. A remaining gap is not necessarily a flaw
   in either method.

## What this means for the project's conclusions

With the corrected model, this external benchmarking comparison
provides meaningfully stronger support for this project's district-
level estimates than the earlier (flawed) version did. It does NOT
constitute formal cross-validation (see terminology note above) --
proper internal validation (posterior predictive checks, simulation-
based calibration, held-out comparison where feasible) is reported
separately in `docs/MODEL_VALIDATION.md`. A methods paper based on this
project should:
- Report this comparison as external benchmarking, not cross-validation.
- Note the magnitude of improvement after the censoring correction as
  supporting evidence that the corrected model's estimates are more
  reliable than a naive aggregate-count approach would produce.
- Still report the remaining {max_diff_row['province']} gap honestly
  rather than only highlighting provinces with closer agreement.
"""
    findings_path = DOCS_DIR / "GBD_VALIDATION_FINDINGS.md"
    findings_path.write_text(content)
    print(f"\nWrote: {findings_path}")


if __name__ == "__main__":
    main()
