"""
*** DEPRECATED -- DO NOT USE FOR ANY ANALYSIS ***
This script is SUPERSEDED by scripts/models/04_hierarchical_hazard_sae.py
and is kept in the repository ONLY as a documented historical artifact
of a real methodological flaw found during external review, and as the
"before" half of a before/after comparison that itself became evidence
supporting the corrected model (see docs/GBD_VALIDATION_FINDINGS.md and
docs/LIMITATIONS.md for the full account). It is NOT called anywhere in
scripts/run_pipeline.sh and should not be re-run for any real purpose.

THE FLAW: this script models `deaths ~ Binomial(births, p)` using
already-aggregated birth/death counts per district. This implicitly
assumes every birth in the 5-year reference window had a FULL 5-year
follow-up before being at risk of death, which is incorrect --
children born recently before the survey interview have only been
observed (and only could have died) for a few months, not five years.
This is a real right-censoring handling error, identified via external
methodological review.

CONCRETE IMPACT: under this flawed model, this project's Balochistan
province estimate diverged from an independent external benchmark
(IHME GBD 2023) by 56% (79/1,000 vs. 51/1,000), with province-level
rank correlation of only 0.50. After correcting the censoring handling
in 04_hierarchical_hazard_sae.py, that divergence dropped to ~15% and
rank correlation rose to 0.90 -- strong evidence the flaw in THIS
script was materially distorting estimates, especially for small-
sample, high-volatility provinces exactly like Balochistan.

03_hierarchical_bayesian_sae.py

Layer 3 (Small Area Estimation) -- the scientific centerpiece.

Fits a Bayesian hierarchical (partial pooling) model for district-level
U5MR, combining:
    - REAL direct DHS estimates (data/processed/mortality/
      district_u5mr_direct_dhs.csv) where available (122/135 districts,
      of varying sample sizes / precision)
    - Covariate information (deprivation_index, literacy, WASH,
      household pressure, urbanization, remoteness) that predicts
      mortality risk even where direct DHS data is thin or absent
    - Province-level random effects, so districts with NO direct DHS
      clusters (13/135) borrow strength from their province and
      covariates rather than being left unestimated

MODEL STRUCTURE (binomial-normal hierarchical model on log-U5MR scale):

    For districts WITH direct DHS data (n_births > 0):
        deaths_d ~ Binomial(n_births_d, p_d)
        logit(p_d) = mu_province[province_d] + beta * X_d + eps_d
        eps_d ~ Normal(0, sigma_district)   # district-level random effect

    mu_province[p] ~ Normal(mu_national, sigma_province)  # province RE
    mu_national ~ Normal(logit(0.075), 1)   # weakly informative, centered
                                              # near national U5MR ~75/1000
    beta ~ Normal(0, 1)                      # covariate effects
    sigma_province, sigma_district ~ HalfNormal(1)

    For districts WITHOUT direct DHS data, the model still produces a
    posterior predictive U5MR from mu_province + beta*X (no likelihood
    contribution from that district, since it has no data) -- this IS
    the small-area estimation "borrowing strength" mechanism.

This directly implements the project's stated Layer 3 requirements:
hierarchical model, Bayesian estimation, bootstrapped/posterior
uncertainty, and province-level calibration.

KNOWN LIMITATION -- covariate significance: the three fixed-effect
covariates below are substantially correlated with each other
(deprivation_index-remoteness_proxy r=0.70; deprivation_index-urban_pct
r=-0.66; urban_pct-remoteness_proxy r=-0.54), and none has a 95%
posterior credible interval excluding zero. The model's real
information content comes primarily from each district's own direct
DHS data (where available) and province-level pooling, not from these
covariates individually predicting risk in a statistically decisive
way. See docs/LIMITATIONS.md #9 for full discussion -- this is stated
here so the limitation is visible to anyone reading the model code
directly, not only in the separate docs file.

Output:
    data/processed/models/hierarchical_sae_results.csv
        (district_key, province, u5mr_posterior_mean, u5mr_ci_lower95,
         u5mr_ci_upper95, had_direct_data, n_births_direct)
    models/hierarchical_sae_trace.nc   (full posterior trace, for
        further diagnostics/reproducibility)
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

FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
DHS_DIRECT_PATH = DATA_PROCESSED / "mortality" / "district_u5mr_direct_dhs.csv"
OUT_DIR = DATA_PROCESSED / "models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

COVARIATES = [
    "deprivation_index",
    "urban_pct",
    "remoteness_proxy",
]  # kept parsimonious for a stable hierarchical fit; deprivation_index
   # already summarizes literacy/WASH/crowding (see Layer 2), avoiding
   # collinearity from including its raw components separately here.


def load_and_merge() -> pd.DataFrame:
    feat = pd.read_csv(FEATURES_PATH)

    if DHS_DIRECT_PATH.exists():
        dhs = pd.read_csv(DHS_DIRECT_PATH)[
            ["district_key", "n_births_5yr", "n_deaths_u5_5yr", "low_direct_coverage"]
        ]
        df = feat.merge(dhs, on="district_key", how="left")
    else:
        # No DHS BR data available at all (e.g. reproducing this project
        # via `scripts/run_pipeline.sh --no-dhs`, without your own DHS
        # access). Rather than crash, fall back to a well-defined,
        # honestly-labeled degenerate case: every district gets
        # n_births_5yr = 0, so the Binomial likelihood contributes
        # nothing anywhere and the model runs as PURE prior/covariate-
        # based small-area prediction (mu_province + beta*X only, no
        # data anchoring at all). This is a real, legitimate model to
        # fit -- just a much weaker one, and this is stated loudly in
        # the console output and again in the output CSV below.
        print(
            "\n*** WARNING: district_u5mr_direct_dhs.csv not found. ***\n"
            "*** Running with ZERO DHS birth data for ALL 135      ***\n"
            "*** districts -- every posterior estimate below comes ***\n"
            "*** purely from province + covariate priors, with NO  ***\n"
            "*** survey data anchoring any district whatsoever.    ***\n"
            "*** This is a legitimate but much weaker analysis --  ***\n"
            "*** see docs/LIMITATIONS.md. Re-run with real PDHS    ***\n"
            "*** BR data for the full analysis this project is     ***\n"
            "*** designed to produce.\n"
        )
        df = feat.copy()
        df["n_births_5yr"] = 0
        df["n_deaths_u5_5yr"] = 0
        df["low_direct_coverage"] = True

    # districts with zero DHS clusters won't appear in the DHS file at all
    # (03_clean_dhs_cluster_geography.py's coverage output showed 13 such
    # districts) -- treat their n_births/n_deaths as 0, not NaN
    df["n_births_5yr"] = df["n_births_5yr"].fillna(0).astype(int)
    df["n_deaths_u5_5yr"] = df["n_deaths_u5_5yr"].fillna(0).astype(int)
    df["had_direct_data"] = df["n_births_5yr"] > 0

    # standardize covariates for stable MCMC sampling
    for c in COVARIATES:
        df[f"{c}_z"] = (df[c] - df[c].mean()) / df[c].std()

    return df


def fit_hierarchical_model(df: pd.DataFrame):
    provinces = df["province"].astype("category")
    province_idx = provinces.cat.codes.values
    n_provinces = len(provinces.cat.categories)

    n_births = df["n_births_5yr"].values
    n_deaths = df["n_deaths_u5_5yr"].values
    X = df[[f"{c}_z" for c in COVARIATES]].values
    n_districts = len(df)

    # National U5MR ~75/1000 -> logit(0.075) as the prior center
    national_logit_prior = float(np.log(0.075 / (1 - 0.075)))

    coords = {
        "province": provinces.cat.categories.tolist(),
        "covariate": COVARIATES,
        "district": df["district_key"].tolist(),
    }

    with pm.Model(coords=coords) as model:
        mu_national = pm.Normal("mu_national", mu=national_logit_prior, sigma=1.0)
        sigma_province = pm.HalfNormal("sigma_province", sigma=1.0)
        sigma_district = pm.HalfNormal("sigma_district", sigma=0.5)

        # province-level random effect (non-centered parameterization for
        # better MCMC geometry)
        z_province = pm.Normal("z_province", mu=0, sigma=1, dims="province")
        mu_province = pm.Deterministic(
            "mu_province", mu_national + z_province * sigma_province, dims="province"
        )

        beta = pm.Normal("beta", mu=0, sigma=1, dims="covariate")

        # district-level random effect (non-centered)
        z_district = pm.Normal("z_district", mu=0, sigma=1, dims="district")
        eps_district = z_district * sigma_district

        logit_p = (
            mu_province[province_idx]
            + pm.math.dot(X, beta)
            + eps_district
        )
        p = pm.Deterministic("p", pm.math.invlogit(logit_p), dims="district")

        # Likelihood only informs districts with n_births > 0; PyMC handles
        # n=0 gracefully (Binomial(0, p) contributes 0 to the log-likelihood
        # regardless of p), so zero-data districts are automatically
        # "predict only" without special-casing.
        pm.Binomial("deaths_obs", n=n_births, p=p, observed=n_deaths)

        print("Sampling posterior (this may take a minute)...")
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


def main():
    print("Loading and merging feature + DHS direct estimate data...")
    df = load_and_merge()
    print(f"  {len(df)} districts total")
    print(f"  {df['had_direct_data'].sum()} with direct DHS birth data")
    print(f"  {(~df['had_direct_data']).sum()} with zero DHS clusters (pure model-based)")

    if df["had_direct_data"].sum() == 0:
        existing_path = OUT_DIR / "hierarchical_sae_results.csv"
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
                    "#                                                            #\n"
                    f"# {existing_path} already contains         #\n"
                    "# real DHS-anchored estimates (run_mode='normal'), but      #\n"
                    "# district_u5mr_direct_dhs.csv is currently missing --      #\n"
                    "# which would produce a much weaker prior-only result that  #\n"
                    "# would silently replace your real analysis.                #\n"
                    "#                                                            #\n"
                    "# If this is intentional (e.g. deliberately reproducing the #\n"
                    "# --no-dhs pathway for testing), rerun with the             #\n"
                    "# --force-no-dhs flag. Otherwise, restore your real         #\n"
                    "# district_u5mr_direct_dhs.csv first (see                   #\n"
                    "# docs/DATA_SOURCES.md) and re-run normally.                #\n"
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

    print(f"\nFitting hierarchical Bayesian model (covariates: {COVARIATES})...")
    model, trace = fit_hierarchical_model(df)

    print("\nChecking convergence diagnostics...")
    summary = az.summary(trace, var_names=["mu_national", "sigma_province", "sigma_district", "beta"])
    print(summary)
    max_rhat = float(summary["r_hat"].astype(float).max())
    min_ess = float(summary["ess_bulk"].astype(float).min())
    print(f"\nMax R-hat: {max_rhat:.3f} (should be < 1.01)")
    print(f"Min ESS (bulk): {min_ess:.0f} (should be > 400)")
    if max_rhat > 1.01:
        print("  WARNING: convergence issue detected (R-hat > 1.01) -- results below should be treated cautiously.")

    print("\nCovariate significance check (95% credible intervals)...")
    beta_posterior = trace.posterior["beta"]
    for cov in beta_posterior.coords["covariate"].values:
        vals = beta_posterior.sel(covariate=cov).values.flatten()
        lo, hi = np.percentile(vals, [2.5, 97.5])
        crosses_zero = lo < 0 < hi
        flag = " (crosses zero -- not statistically significant)" if crosses_zero else ""
        print(f"  {cov}: mean={vals.mean():.3f}, 95% CI=[{lo:.3f}, {hi:.3f}]{flag}")
    print(
        "  NOTE: covariates in this model are substantially correlated with "
        "each other (see docs/LIMITATIONS.md #9) -- individual coefficients "
        "not being significant does not mean the model is uninformative, "
        "only that it cannot cleanly attribute risk to one specific "
        "covariate over the others."
    )

    # extract posterior for district-level p (probability of death, i.e. U5MR/1000)
    p_posterior = trace.posterior["p"]  # dims: chain, draw, district
    p_flat = p_posterior.stack(sample=("chain", "draw"))

    u5mr_mean = p_flat.mean(dim="sample").values * 1000
    u5mr_lower = p_flat.quantile(0.025, dim="sample").values * 1000
    u5mr_upper = p_flat.quantile(0.975, dim="sample").values * 1000

    results = pd.DataFrame(
        {
            "district_key": df["district_key"].values,
            "province": df["province"].values,
            "had_direct_data": df["had_direct_data"].values,
            "n_births_direct": df["n_births_5yr"].values,
            "run_mode": (
                "no_dhs_prior_only" if df["had_direct_data"].sum() == 0 else "normal"
            ),
            "u5mr_posterior_mean": u5mr_mean,
            "u5mr_ci_lower95": u5mr_lower,
            "u5mr_ci_upper95": u5mr_upper,
        }
    )
    results["ci_width"] = results["u5mr_ci_upper95"] - results["u5mr_ci_lower95"]

    out_path = OUT_DIR / "hierarchical_sae_results.csv"
    results.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    trace_path = MODELS_DIR / "hierarchical_sae_trace.pkl"
    with open(trace_path, "wb") as f:
        import pickle
        pickle.dump(trace, f)
    print(f"Wrote: {trace_path}")

    print("\n--- Sanity checks ---")
    print("Posterior mean U5MR summary:")
    print(results["u5mr_posterior_mean"].describe())

    print("\nCI width comparison: districts WITH vs WITHOUT direct data")
    print(results.groupby("had_direct_data")["ci_width"].describe())
    print(
        "\n(Districts without direct data should show WIDER credible "
        "intervals, reflecting greater uncertainty when relying purely on "
        "province + covariate borrowing rather than local survey evidence "
        "-- this is the expected and desired behavior of a hierarchical "
        "SAE model.)"
    )

    print("\nTop 10 highest posterior mean U5MR:")
    print(
        results.nlargest(10, "u5mr_posterior_mean")[
            ["district_key", "province", "had_direct_data", "n_births_direct", "u5mr_posterior_mean", "u5mr_ci_lower95", "u5mr_ci_upper95"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
