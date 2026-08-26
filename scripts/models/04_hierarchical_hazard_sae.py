"""
04_hierarchical_hazard_sae.py

Layer 3 (Small Area Estimation) -- REPLACES the earlier binomial-on-
aggregate-counts hierarchical model (03_DEPRECATED_hierarchical_bayesian_sae_binomial.py)
with a statistically correct discrete-time hazard model, addressing a
real flaw identified in external methodological review.

*** WHY THIS REPLACES THE EARLIER MODEL ***
The earlier model fit `n_deaths_u5_5yr ~ Binomial(n_births_5yr, p)`,
which implicitly assumes every birth had a full, uncensored 5-year
follow-up. This is wrong: children born recently before the interview
have only been at risk for a few months, not five years. Feeding an
already right-censoring-corrected point estimate into a naive binomial
double-handles censoring incorrectly and understates uncertainty.

*** THE CORRECTED APPROACH ***
A discrete-time hazard (Poisson person-time) model, fit on person-
segment survival records built by
scripts/models/03_build_person_segment_records.py, where each child
contributes exposure only for the age segments they were actually
observed alive for (with proper actuarial partial-exposure correction
for children censored mid-segment -- see that script's docstring).
This is the standard, textbook-correct way to handle censoring in
survival analysis and is structurally equivalent to methods used in
DHS/IGME's own official child mortality estimation methodology.

MODEL STRUCTURE:
    For each (district, age segment) cell:
        weighted_events_ds ~ Poisson(p_ds * weighted_exposure_ds)
        logit(p_ds) = alpha_segment[s] + mu_province[province_d]
                      + beta . X_d + eps_district_d
        p_ds = probability of death WITHIN this segment, for a child who
               entered the segment alive (a discrete-time hazard on the
               segment scale, not an instantaneous per-month rate).
               NOTE: an earlier version of this model treated the
               segment-level actuarial `exposure` weight (1.0 fully
               observed, 0.5 partially observed) as if it were true
               person-MONTHS of exposure, then reconstructed U5MR via
               1-exp(-hazard*segment_width) -- effectively double-
               applying the segment width and inflating the national
               aggregate to ~149/1,000 vs. the known-correct ~75/1,000.
               This was caught via the mandatory aggregate consistency
               check below and fixed by keeping the model on the
               segment-probability scale throughout, matching the units
               `exposure` actually represents (a count of children
               observed for all/half of a discrete segment, not a
               continuous time duration).
        alpha_segment[s] ~ Normal(0, 2)         # segment-specific baseline
                                                  # hazard (age pattern of
                                                  # mortality risk -- much
                                                  # higher in month 0-1
                                                  # than 48-60)
        mu_province[p] ~ Normal(mu_national, sigma_province)
        mu_national ~ Normal(0, 1)
        beta ~ Normal(0, 1)   [covariates: deprivation_index, urban_pct,
                                remoteness_proxy, standardized]
        eps_district ~ Normal(0, sigma_district)
        sigma_province, sigma_district ~ HalfNormal(1)

    District-level U5MR is then reconstructed from the fitted segment
    death probabilities via the same actuarial chaining formula used in
    the direct estimator: U5MR = 1 - PROD_segments(1 - p_s), computed
    from POSTERIOR SAMPLES of the segment probabilities, which correctly
    propagates all model uncertainty into the final U5MR credible
    interval (not just uncertainty in a single aggregate rate).

Districts with zero DHS clusters contribute no likelihood term at all
(same borrowing-strength mechanism as before) and are predicted purely
from mu_province + beta*X + segment baseline hazard.

Output:
    data/processed/models/hierarchical_hazard_sae_results.csv
    models/hierarchical_hazard_sae_trace.pkl
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, MODELS_DIR, RANDOM_SEED

warnings.filterwarnings("ignore")

PERSON_SEGMENT_PATH = DATA_PROCESSED / "dhs_derived" / "person_segment_records.csv"
FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
OUT_DIR = DATA_PROCESSED / "models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AGE_SEGMENTS = [
    (0, 1), (1, 3), (3, 6), (6, 12),
    (12, 24), (24, 36), (36, 48), (48, 60),
]
SEGMENT_WIDTHS = np.array([end - start for start, end in AGE_SEGMENTS])

COVARIATES = ["deprivation_index", "urban_pct", "remoteness_proxy"]


def build_district_segment_grid() -> pd.DataFrame:
    """
    Build the FULL district x segment grid (135 districts x 8 segments
    = 1080 rows), including districts with zero DHS data (exposure=0,
    events=0 -- contributing no likelihood, exactly as in the prior
    model's borrowing-strength design), not just the districts that
    happen to appear in the person-segment file.

    If PERSON_SEGMENT_PATH does not exist at all (e.g. reproducing this
    project via `scripts/run_pipeline.sh --no-dhs`, without DHS access),
    this degrades gracefully to an all-zero-exposure grid rather than
    crashing -- the resulting model runs in pure prior/covariate-only
    mode (see main()'s explicit warning and the --force-no-dhs guard,
    mirroring the same safeguard pattern used in the now-deprecated
    03_DEPRECATED_hierarchical_bayesian_sae_binomial.py, carried forward
    here so this exact reproducibility gap cannot silently reappear).
    """
    feat = pd.read_csv(FEATURES_PATH)
    all_districts = feat[["district_key", "province"] + COVARIATES].copy()
    segment_index = pd.DataFrame(
        {"segment_idx": range(len(AGE_SEGMENTS)),
         "segment_label": [f"{s}-{e}" for s, e in AGE_SEGMENTS]}
    )

    if not PERSON_SEGMENT_PATH.exists():
        print(
            f"\n  WARNING: {PERSON_SEGMENT_PATH} not found. Building an "
            "all-zero-exposure grid (no DHS data anywhere) -- see main()'s "
            "no-DHS safeguard for what happens next.\n"
        )
        full_grid = all_districts.merge(segment_index, how="cross")
        full_grid["weighted_exposure"] = 0.0
        full_grid["weighted_events"] = 0.0
        full_grid["raw_births_in_segment"] = 0
        full_grid["had_direct_data"] = False
        return full_grid

    person_segment = pd.read_csv(PERSON_SEGMENT_PATH)
    person_segment["weighted_exposure"] = (
        person_segment["exposure"] * person_segment["weight"]
    )
    person_segment["weighted_events"] = (
        person_segment["event"] * person_segment["weight"]
    )

    agg = (
        person_segment.groupby(["district_key", "segment_idx"])
        .agg(
            weighted_exposure=("weighted_exposure", "sum"),
            weighted_events=("weighted_events", "sum"),
            raw_births_in_segment=("event", "count"),
        )
        .reset_index()
    )
    full_grid = all_districts.merge(segment_index, how="cross")
    full_grid = full_grid.merge(agg, on=["district_key", "segment_idx"], how="left")

    full_grid["weighted_exposure"] = full_grid["weighted_exposure"].fillna(0.0)
    full_grid["weighted_events"] = full_grid["weighted_events"].fillna(0.0)
    full_grid["raw_births_in_segment"] = full_grid["raw_births_in_segment"].fillna(0).astype(int)
    full_grid["had_direct_data"] = full_grid.groupby("district_key")[
        "raw_births_in_segment"
    ].transform("sum") > 0

    return full_grid


def fit_hazard_model(grid: pd.DataFrame):
    districts = grid["district_key"].astype("category")
    district_idx = districts.cat.codes.values

    district_province_map = (
        grid.drop_duplicates("district_key")
        .set_index("district_key")["province"]
        .astype("category")
    )
    province_categories = district_province_map.cat.categories.tolist()

    province_idx_per_row = pd.Categorical(
        grid["province"], categories=province_categories
    ).codes

    segment_idx = grid["segment_idx"].values

    X = grid[[f"{c}_z" for c in COVARIATES]].values
    exposure = grid["weighted_exposure"].values
    events = grid["weighted_events"].values

    # p_ds = probability of death WITHIN a segment (discrete-time hazard
    # on the segment scale -- see module docstring for why this replaces
    # an earlier, incorrect instantaneous-rate parameterization). A
    # crude empirical check (event/exposure per segment) gives ~0.04 for
    # the 0-1 month segment, dropping to ~0.002-0.008 for later segments
    # -- so a logit-scale prior centered near logit(0.01) is a
    # reasonable weakly-informative starting point.
    baseline_logit_prior = float(np.log(0.01 / (1 - 0.01)))

    coords = {
        "district": districts.cat.categories.tolist(),
        "province": province_categories,
        "segment": [f"{s}-{e}" for s, e in AGE_SEGMENTS],
        "covariate": COVARIATES,
        "obs": grid.index.tolist(),
    }

    with pm.Model(coords=coords) as model:
        alpha_segment = pm.Normal(
            "alpha_segment", mu=baseline_logit_prior, sigma=2.0, dims="segment"
        )

        mu_national = pm.Normal("mu_national", mu=0.0, sigma=1.0)
        sigma_province = pm.HalfNormal("sigma_province", sigma=1.0)
        z_province = pm.Normal("z_province", mu=0, sigma=1, dims="province")
        mu_province = pm.Deterministic(
            "mu_province", mu_national + z_province * sigma_province, dims="province"
        )

        beta = pm.Normal("beta", mu=0, sigma=1, dims="covariate")

        sigma_district = pm.HalfNormal("sigma_district", sigma=0.5)
        z_district = pm.Normal("z_district", mu=0, sigma=1, dims="district")
        eps_district = z_district * sigma_district

        logit_p = (
            alpha_segment[segment_idx]
            + mu_province[province_idx_per_row]
            + pm.math.dot(X, beta)[district_idx]
            + eps_district[district_idx]
        )
        # p = segment-level death probability, NOT an instantaneous
        # rate -- exposure (below) is a unitless actuarial weight
        # (1.0 fully observed, 0.5 partially observed), so the Poisson
        # rate mu = p * exposure directly, with no additional segment-
        # width multiplication (that was the earlier bug).
        p = pm.Deterministic("p", pm.math.invlogit(logit_p), dims="obs")

        mu = p * (exposure + 1e-8)
        pm.Poisson("events_obs", mu=mu, observed=events)

        print("Sampling posterior (discrete-time hazard model)...")
        trace = pm.sample(
            draws=1500,
            tune=1500,
            chains=4,
            cores=1,
            target_accept=0.95,
            random_seed=RANDOM_SEED,
            progressbar=True,
        )

    return model, trace


def reconstruct_u5mr_from_hazards(trace, grid: pd.DataFrame) -> pd.DataFrame:
    """
    For each posterior sample, reconstruct district-level U5MR from the
    fitted segment-specific death PROBABILITIES (already on the correct
    scale -- see module docstring) via the same actuarial chaining
    formula used in the direct estimator:
        U5MR = 1 - PROD_segments(1 - p_s)

    CRITICAL: takes `grid` (the actual DataFrame used to build the
    model's `obs` arrays) rather than an independently-derived
    alphabetically-sorted district list. An earlier version of this
    function reshaped the `p` posterior using
    `districts.cat.categories.tolist()` (alphabetical order) while the
    underlying `obs` dimension in the trace is actually ordered by
    `grid`'s row order (district-major in FIRST-APPEARANCE order from
    the cross-join, e.g. Bannu, Lakki Marwat, Dera Ismail Khan... --
    NOT alphabetical). This mismatch silently scrambled which posterior
    samples were attributed to which district, producing a national
    aggregate of ~149-150/1,000 (vs. the correct ~75/1,000) even though
    every individual model component (data construction, priors,
    convergence) was correct in isolation. Caught via the mandatory
    aggregate consistency check in main() and fixed by deriving the
    district order directly from `grid.index`, which is exactly how
    PyMC ordered the `obs` coordinate during model construction.

    This is done PER POSTERIOR SAMPLE so the resulting U5MR credible
    interval correctly reflects full model uncertainty.
    """
    p_posterior = trace.posterior["p"]
    p_flat = p_posterior.stack(sample=("chain", "draw"))  # dims: obs, sample

    # grid_order preserves EXACTLY the row order used to build district_idx
    # and segment_idx when the model was constructed (see fit_hazard_model).
    grid_ordered = grid.reset_index(drop=True)
    district_order = grid_ordered["district_key"].values
    segment_order = grid_ordered["segment_idx"].values

    p_vals = p_flat.values  # shape: (n_obs, n_samples), n_obs == len(grid)
    p_vals = np.clip(p_vals, 0, 1)
    n_samples = p_vals.shape[-1]

    unique_districts = pd.unique(district_order)
    n_segments = len(AGE_SEGMENTS)

    results = []
    for district in unique_districts:
        mask = district_order == district
        # mask selects this district's 8 rows in whatever order they
        # appear in grid_ordered; sort by segment_idx to guarantee
        # correct chaining order regardless of row order
        district_rows = np.where(mask)[0]
        seg_ids_here = segment_order[district_rows]
        sort_order = np.argsort(seg_ids_here)
        ordered_rows = district_rows[sort_order]

        survival = np.ones(n_samples)
        for row in ordered_rows:
            survival *= (1 - p_vals[row, :])
        samples = (1 - survival) * 1000

        results.append(
            {
                "district_key": district,
                "u5mr_posterior_mean": samples.mean(),
                "u5mr_ci_lower95": np.percentile(samples, 2.5),
                "u5mr_ci_upper95": np.percentile(samples, 97.5),
                "u5mr_posterior_sd": samples.std(),
            }
        )
    return pd.DataFrame(results)


def main():
    print("Building district x segment grid (including zero-data districts)...")
    grid = build_district_segment_grid()
    print(f"  {grid['district_key'].nunique()} districts, {len(grid)} district-segment rows")
    n_with_data = grid.groupby('district_key')['had_direct_data'].first().sum()
    print(f"  {n_with_data} districts with direct DHS data")

    if n_with_data == 0:
        existing_path = OUT_DIR / "hierarchical_hazard_sae_results.csv"
        if existing_path.exists():
            existing = pd.read_csv(existing_path)
            if (
                "run_mode" in existing.columns
                and (existing["run_mode"] == "normal").any()
                and "--force-no-dhs" not in sys.argv
            ):
                print(
                    "\n############################################################\n"
                    "# REFUSING TO OVERWRITE a real (DHS-anchored) result with   #\n"
                    "# a degenerate no-DHS prior-only result.                    #\n"
                    f"# {existing_path} already contains         #\n"
                    "# real DHS-anchored estimates (run_mode='normal'), but      #\n"
                    "# person_segment_records.csv is currently missing -- which  #\n"
                    "# would produce a much weaker prior-only result that would  #\n"
                    "# silently replace your real analysis.                     #\n"
                    "# If intentional, rerun with --force-no-dhs. Otherwise,     #\n"
                    "# restore your real DHS data first (see docs/DATA_SOURCES.md).\n"
                    "############################################################\n"
                )
                sys.exit(1)
        print(
            "\n############################################################\n"
            "# ALL 135 DISTRICTS ARE RUNNING WITHOUT DHS DATA.           #\n"
            "# The results below are NOT a meaningful mortality estimate #\n"
            "# for any real-world use -- they reflect only the model's   #\n"
            "# weakly-informative PRIOR, not evidence from any survey.   #\n"
            "# This mode exists solely so scripts/run_pipeline.sh        #\n"
            "# --no-dhs does not crash for readers without DHS access.   #\n"
            "# Obtain real PDHS BR data (see docs/DATA_SOURCES.md) for   #\n"
            "# any actual analysis.                                     #\n"
            "############################################################\n"
        )

    for c in COVARIATES:
        grid[f"{c}_z"] = (grid[c] - grid[c].mean()) / grid[c].std()

    print(f"\nFitting discrete-time hazard hierarchical model (covariates: {COVARIATES})...")
    model, trace = fit_hazard_model(grid)

    print("\nChecking convergence diagnostics...")
    summary = az.summary(
        trace, var_names=["mu_national", "sigma_province", "sigma_district", "beta", "alpha_segment"]
    )
    print(summary)
    max_rhat = float(summary["r_hat"].astype(float).max())
    min_ess = float(summary["ess_bulk"].astype(float).min())
    n_divergences = int(trace.sample_stats.diverging.sum().values)
    print(f"\nMax R-hat: {max_rhat:.3f} (should be < 1.01)")
    print(f"Min ESS (bulk): {min_ess:.0f} (should be > 400)")
    print(f"Divergent transitions: {n_divergences} (should be 0 or very few)")
    if max_rhat > 1.01 or n_divergences > 50:
        print("  WARNING: convergence issue detected -- results should be treated cautiously.")

    print("\nReconstructing district-level U5MR from fitted segment hazards...")
    u5mr_results = reconstruct_u5mr_from_hazards(trace, grid)

    had_data_map = grid.groupby("district_key")["had_direct_data"].first()
    n_births_map = grid.groupby("district_key")["raw_births_in_segment"].sum()
    province_map = grid.drop_duplicates("district_key").set_index("district_key")["province"]

    u5mr_results["province"] = u5mr_results["district_key"].map(province_map)
    u5mr_results["had_direct_data"] = u5mr_results["district_key"].map(had_data_map)
    u5mr_results["n_births_direct"] = u5mr_results["district_key"].map(n_births_map)
    u5mr_results["ci_width"] = (
        u5mr_results["u5mr_ci_upper95"] - u5mr_results["u5mr_ci_lower95"]
    )
    u5mr_results["run_mode"] = "normal" if n_with_data > 0 else "no_dhs_prior_only"
    u5mr_results["model_version"] = "hazard_v1_censoring_corrected"

    out_path = OUT_DIR / "hierarchical_hazard_sae_results.csv"
    u5mr_results.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    trace_path = MODELS_DIR / "hierarchical_hazard_sae_trace.pkl"
    with open(trace_path, "wb") as f:
        import pickle
        pickle.dump(trace, f)
    print(f"Wrote: {trace_path}")

    print("\n--- Sanity checks ---")
    print("Posterior mean U5MR summary:")
    print(u5mr_results["u5mr_posterior_mean"].describe())

    print("\nCI width: districts WITH vs WITHOUT direct data")
    print(u5mr_results.groupby("had_direct_data")["ci_width"].describe())

    print("\nTop 10 highest posterior mean U5MR:")
    print(
        u5mr_results.nlargest(10, "u5mr_posterior_mean")[
            ["district_key", "province", "had_direct_data", "n_births_direct",
             "u5mr_posterior_mean", "u5mr_ci_lower95", "u5mr_ci_upper95"]
        ].to_string(index=False)
    )

    feat = pd.read_csv(FEATURES_PATH)[["district_key", "population_2017"]]
    check = u5mr_results.merge(feat, on="district_key")
    national_weighted = np.average(
        check["u5mr_posterior_mean"], weights=check["population_2017"]
    )
    print(f"\nNational population-weighted U5MR (hazard model): {national_weighted:.1f} per 1,000")
    print(
        "This is an internal AGGREGATE CONSISTENCY CHECK against the "
        "published national figure (74.9/1,000), NOT a validation of "
        "district-level accuracy -- see docs/LIMITATIONS.md."
    )

    # MANDATORY GATE: if this check fails badly IN NORMAL (DHS-anchored)
    # MODE, something is structurally wrong with the model (a real
    # historical example: a district-ordering mismatch between the
    # model's `obs` array and the reconstruction step's assumed district
    # order silently inflated this to ~149-150/1,000 during development
    # -- see reconstruct_u5mr_from_hazards()'s docstring). A model that
    # fails this basic sanity check in normal mode should not be used
    # for any downstream decision-making, so this is a hard failure.
    #
    # In the intentional --force-no-dhs degenerate mode, this check is
    # EXPECTED to fail (there is no data to anchor the estimate, so the
    # prior alone can produce implausible values) -- that is not a bug,
    # it is the correct behavior of a model with zero informative data,
    # and main() has already printed a loud warning about this mode
    # before reaching here. We downgrade to a warning rather than a
    # hard crash in that specific, already-acknowledged case.
    PLAUSIBLE_RANGE = (40, 120)  # generous band around the known ~75/1,000
                                   # national figure, wide enough to allow
                                   # for genuine hierarchical-model shrinkage
                                   # without masking a real structural bug
    within_range = PLAUSIBLE_RANGE[0] <= national_weighted <= PLAUSIBLE_RANGE[1]
    is_degenerate_mode = check["n_births_direct"].sum() == 0 if "n_births_direct" in check.columns else False

    if not within_range and not is_degenerate_mode:
        raise ValueError(
            f"AGGREGATE CONSISTENCY CHECK FAILED: national population-"
            f"weighted U5MR ({national_weighted:.1f}/1,000) is outside "
            f"the plausible range {PLAUSIBLE_RANGE} around the known "
            f"published national figure (74.9/1,000). This almost "
            f"certainly indicates a structural bug (e.g. an index/order "
            f"mismatch between the model's internal array layout and the "
            f"reconstruction step) rather than genuine model uncertainty. "
            f"DO NOT use these results. See "
            f"reconstruct_u5mr_from_hazards()'s docstring for a real "
            f"historical example of this exact failure mode."
        )
    elif not within_range and is_degenerate_mode:
        print(
            f"  Consistency check outside {PLAUSIBLE_RANGE} as EXPECTED "
            f"in --force-no-dhs prior-only mode (no data to anchor the "
            f"estimate) -- not treated as a structural bug in this "
            f"specific, already-acknowledged degenerate mode."
        )
    else:
        print(f"  PASSED aggregate consistency check (within {PLAUSIBLE_RANGE}).")


if __name__ == "__main__":
    main()
