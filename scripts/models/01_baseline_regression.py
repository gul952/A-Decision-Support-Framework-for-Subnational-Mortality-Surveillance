"""
01_baseline_regression.py

Layer 3 (Small Area Estimation) -- Stage 1: baseline model.

Fits an OLS regression of the mortality risk proxy on district
covariates, with bootstrap resampling for uncertainty quantification
and leave-one-province-out cross-validation for honest out-of-sample
performance reporting (not just in-sample R^2).

This is intentionally the SIMPLEST model in the SAE progression. Its
job is to establish a defensible floor: if the hierarchical/Bayesian
model in 02_hierarchical_bayesian_sae.py cannot beat this baseline,
that is itself a real finding worth reporting, not something to hide.

NOTE: because the outcome variable is currently the deprivation-based
proxy (see scripts/models/02_build_mortality_risk_proxy.py), and two of
the covariates below are themselves components of that same proxy
(literacy, WASH), in-sample fit will look artificially strong. This is
flagged explicitly in the output and must be re-evaluated once a real
DHS-derived outcome replaces the proxy -- at that point this
circularity disappears and the covariates become genuine independent
predictors.

Output:
    data/processed/models/baseline_regression_results.csv (district-level predictions + CI)
    data/processed/models/baseline_regression_cv_metrics.csv (leave-one-province-out CV)
    models/baseline_regression_model.pkl
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED, MODELS_DIR, RANDOM_SEED, N_BOOTSTRAP

warnings.filterwarnings("ignore", category=FutureWarning)

FEATURES_PATH = DATA_PROCESSED / "features" / "district_features.csv"
MORTALITY_PATH = DATA_PROCESSED / "mortality" / "district_mortality_estimate.csv"
OUT_DIR = DATA_PROCESSED / "models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Covariates chosen to reflect the project's stated feature-engineering
# layer: literacy (education), WASH index, household pressure (crowding),
# urbanization, remoteness proxy. Population density excluded directly
# (colinear with remoteness_proxy by construction).
COVARIATES = [
    "literacy_rate_pct",
    "wash_index",
    "household_pressure_index",
    "urban_pct",
    "remoteness_proxy",
    "under5_share_pct",
]
OUTCOME = "mortality_estimate_per1000"


def load_data() -> pd.DataFrame:
    feat = pd.read_csv(FEATURES_PATH).drop(columns=["province"], errors="ignore")
    mort = pd.read_csv(MORTALITY_PATH)[
        ["district_key", "province", OUTCOME, "mortality_lower95", "mortality_upper95"]
    ]
    df = feat.merge(mort, on="district_key", how="inner")
    return df


def fit_ols(df: pd.DataFrame):
    X = sm.add_constant(df[COVARIATES])
    y = df[OUTCOME]
    model = sm.OLS(y, X).fit()
    return model


def bootstrap_prediction_intervals(
    df: pd.DataFrame, n_boot: int = N_BOOTSTRAP, seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """
    Non-parametric case resampling bootstrap: refit OLS on resampled
    districts, predict for all districts each time, and take the 2.5/97.5
    percentiles of the resulting prediction distribution as the interval.
    This captures parameter/model uncertainty; it does NOT capture the
    proxy-outcome's own uncertainty (mortality_lower95/upper95 from the
    calibration step), which is a separate, additive source of
    uncertainty reported alongside it.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    X_full = sm.add_constant(df[COVARIATES])

    boot_preds = np.zeros((n_boot, n))
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_df = df.iloc[idx]
        X_boot = sm.add_constant(boot_df[COVARIATES])
        y_boot = boot_df[OUTCOME]
        try:
            model_b = sm.OLS(y_boot, X_boot).fit()
            boot_preds[b, :] = model_b.predict(X_full)
        except Exception:
            boot_preds[b, :] = np.nan

    lower = np.nanpercentile(boot_preds, 2.5, axis=0)
    upper = np.nanpercentile(boot_preds, 97.5, axis=0)
    point = np.nanmean(boot_preds, axis=0)

    return pd.DataFrame(
        {
            "district_key": df["district_key"].values,
            "model_pred": point,
            "model_ci_lower": lower,
            "model_ci_upper": upper,
        }
    )


def leave_one_province_out_cv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Leave-one-province-out cross-validation: for each province, fit the
    model on all OTHER provinces' districts and predict the held-out
    province. This is the honest test the project spec calls for --
    much stricter than random k-fold, since it tests whether the model
    generalizes to an entirely unseen region rather than just unseen
    districts within provinces it has already learned from.
    """
    results = []
    provinces = df["province"].dropna().unique()

    for prov in provinces:
        train = df[df["province"] != prov]
        test = df[df["province"] == prov]

        if len(test) < 3 or len(train) < len(COVARIATES) + 2:
            # Provinces with <3 districts (e.g. Federal Capital Territory,
            # n=1) produce degenerate/unstable held-out error metrics and
            # are excluded from LOPO-CV; noted here rather than silently
            # dropped without explanation.
            print(
                f"  Skipping LOPO-CV for {prov}: only {len(test)} district(s), "
                "too few for a stable held-out error estimate."
            )
            continue

        X_train = sm.add_constant(train[COVARIATES])
        y_train = train[OUTCOME]
        X_test = sm.add_constant(test[COVARIATES], has_constant="add")
        # ensure column order/presence matches
        X_test = X_test.reindex(columns=X_train.columns, fill_value=0)

        model = sm.OLS(y_train, X_train).fit()
        preds = model.predict(X_test)

        mae = mean_absolute_error(test[OUTCOME], preds)
        rmse = np.sqrt(mean_squared_error(test[OUTCOME], preds))
        bias = np.mean(preds - test[OUTCOME])

        results.append(
            {
                "held_out_province": prov,
                "n_districts": len(test),
                "mae": mae,
                "rmse": rmse,
                "bias": bias,
            }
        )

    return pd.DataFrame(results)


def main():
    print("Loading data...")
    df = load_data()
    print(f"  {len(df)} districts with complete covariates + outcome")

    missing = df[COVARIATES + [OUTCOME]].isna().sum()
    if missing.sum() > 0:
        print(f"  WARNING: missing values found:\n{missing[missing > 0]}")
        df = df.dropna(subset=COVARIATES + [OUTCOME])
        print(f"  {len(df)} districts remain after dropping incomplete rows")

    print("\nFitting baseline OLS...")
    model = fit_ols(df)
    print(model.summary())

    print(f"\nIn-sample R^2: {model.rsquared:.3f}")
    print(
        "NOTE: R^2 is inflated because two covariates (literacy_rate_pct, "
        "wash_index) are direct inputs to the deprivation_index that the "
        "current proxy outcome is calibrated from. This circularity "
        "resolves once real PDHS-derived mortality replaces the proxy."
    )

    print(f"\nRunning bootstrap ({N_BOOTSTRAP} resamples) for prediction intervals...")
    boot_results = bootstrap_prediction_intervals(df)

    print("\nRunning leave-one-province-out cross-validation...")
    cv_results = leave_one_province_out_cv(df)
    print(cv_results.to_string(index=False))
    print(f"\nMean LOPO-CV MAE: {cv_results['mae'].mean():.2f} per 1,000 live births")
    print(f"Mean LOPO-CV RMSE: {cv_results['rmse'].mean():.2f} per 1,000 live births")

    # Merge everything into final output
    out = df[["district_key", "province", OUTCOME, "mortality_lower95", "mortality_upper95"]].merge(
        boot_results, on="district_key", how="left"
    )
    out_path = OUT_DIR / "baseline_regression_results.csv"
    out.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")

    cv_path = OUT_DIR / "baseline_regression_cv_metrics.csv"
    cv_results.to_csv(cv_path, index=False)
    print(f"Wrote: {cv_path}")

    import pickle

    with open(MODELS_DIR / "baseline_regression_model.pkl", "wb") as f:
        pickle.dump(model, f)
    print(f"Wrote: {MODELS_DIR / 'baseline_regression_model.pkl'}")


if __name__ == "__main__":
    main()
