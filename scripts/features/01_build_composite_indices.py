"""
01_build_composite_indices.py

Layer 2 (Feature Engineering): turn raw cleaned indicators into the
composite, interpretable district-level indices the SAE model and
decision engine consume.

Design principle: every composite index here is constructed from
components that are transparently documented in
docs/VARIABLE_DICTIONARY.md, using a defensible statistical method
(min-max normalization + equal or literature-informed weighting) --
not an opaque combination. This matters for the "Explainability" and
"Scientific Honesty" requirements of the project: any policymaker
reading a district's score should be able to trace exactly which
inputs drove it.

DHS-PREFERRED, CENSUS-FALLBACK DESIGN:
Two independent socioeconomic data sources exist per district:
    - PBS 2017 Census: literacy_rate_pct, improved_water_pct,
      improved_sanitation_pct (binary "improved" indicators, full
      135-district coverage)
    - PDHS 2017-18 HR/IR (via scripts/cleaning/04_clean_dhs_hr_ir.py):
      mean_wealth_score (continuous asset-based PCA index),
      mean_years_education (continuous), mean_anc_visits (health-
      service utilization, NO census equivalent at all), but only
      122/135 districts, and only ~103-113 of those with adequate
      within-district sample size (>=30 records) for a stable estimate.

Rather than silently pick one source, this script uses DHS indicators
PREFERENTIALLY where a district has adequate DHS coverage
(NOT low_dhs_*_coverage), falling back to the census-derived indicator
otherwise. Every district's `deprivation_index` carries a companion
`deprivation_data_source` field recording exactly which inputs were
used, so this is traceable rather than opaque -- addressing the
reviewer-facing question of "why census when richer DHS variables were
available" head-on: DHS variables ARE used, wherever they're reliable
enough to trust; census remains the honest fallback where DHS sampling
was too thin.

Indices built:
    deprivation_index       -- composite socioeconomic deprivation
                                (inverse of education/wealth, WASH,
                                 crowding -- higher = more deprived)
    wash_index               -- water/sanitation/hygiene sub-composite
    household_pressure_index -- crowding + household size sub-composite
    anc_deficit_index         -- antenatal care under-utilization
                                 (DHS-only, no census fallback exists --
                                 districts without DHS ANC data get this
                                 imputed to the median, flagged)
    remoteness_proxy          -- population density inverse (proxy for
                                 physical accessibility until real
                                 travel-time data is sourced -- see
                                 docs/LIMITATIONS.md)

Input:
    data/processed/demographics/district_demographics_socioeconomic.csv
    data/processed/dhs_derived/district_dhs_socioeconomic.csv

Output:
    data/processed/features/district_features.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_PROCESSED

IN_PATH = DATA_PROCESSED / "demographics" / "district_demographics_socioeconomic.csv"
DHS_SOCIOECONOMIC_PATH = DATA_PROCESSED / "dhs_derived" / "district_dhs_socioeconomic.csv"
GEO_KEY_PATH = DATA_PROCESSED / "geography" / "district_master_key.csv"
OUT_DIR = DATA_PROCESSED / "features"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def minmax_normalize(s: pd.Series) -> pd.Series:
    """
    Scale to [0, 1]. If the series has zero variance (all values
    identical), returns 0.5 for every entry rather than NaN (0/0) --
    matching the same degenerate-case handling used in the decision
    engine's minmax_normalize (scripts/decision/01_prioritization_engine.py).
    This was a real bug found via tests/test_feature_engineering.py: an
    earlier version of this function had no such guard and silently
    produced NaN for any constant-valued input, which has not yet
    occurred with real project data (no composite index component has
    had zero variance across all 135 districts) but would have
    propagated silently if it ever did.
    """
    rng = s.max() - s.min()
    if rng == 0:
        return pd.Series(0.5, index=s.index)
    return (s - s.min()) / rng


def impute_with_flag(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Median-impute a column and add a companion `<col>_imputed` boolean
    flag, so imputation is traceable rather than silent. Median chosen
    over mean for robustness to the skewed distributions typical of
    these indicators (e.g. population density).
    """
    flag_col = f"{col}_imputed"
    df[flag_col] = df[col].isna()
    df[col] = df[col].fillna(df[col].median())
    return df


def build_wash_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Water, Sanitation, and Hygiene sub-index. Higher = better WASH
    access. Equal-weighted average of two normalized components
    (water access, sanitation access) -- both are WHO/UNICEF JMP-style
    "improved" indicators already expressed as district percentages.
    """
    df = impute_with_flag(df, "improved_water_pct")
    df = impute_with_flag(df, "improved_sanitation_pct")

    water_norm = minmax_normalize(df["improved_water_pct"])
    sani_norm = minmax_normalize(df["improved_sanitation_pct"])

    df["wash_index"] = 0.5 * water_norm + 0.5 * sani_norm
    return df


def build_household_pressure_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crowding sub-index. Higher = more household pressure (a known
    correlate of infectious disease transmission and child health
    risk). Combines mean persons-per-room and average household size,
    both normalized and equal-weighted.
    """
    df = impute_with_flag(df, "mean_persons_per_room")

    ppr_norm = minmax_normalize(df["mean_persons_per_room"])
    hhsize_norm = minmax_normalize(df["avg_household_size"])

    df["household_pressure_index"] = 0.5 * ppr_norm + 0.5 * hhsize_norm
    return df


def build_remoteness_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """
    STOPGAP proxy for physical/geographic accessibility until real
    facility-location and travel-time data is sourced (see
    docs/LIMITATIONS.md, Layer 1 stretch goals). Uses inverse log
    population density: sparse districts are treated as more remote.
    This is a weak proxy -- a low-density district near a highway is
    very different from a low-density district in mountainous terrain
    -- and is flagged as such everywhere it's used downstream.
    """
    log_density = np.log1p(df["pop_density_per_sqkm"])
    # invert: low density -> high remoteness
    df["remoteness_proxy"] = 1 - minmax_normalize(log_density)
    return df


def build_education_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """
    DHS-preferred, census-fallback education indicator. Where a district
    has adequate DHS IR coverage (>=30 sampled women), use the richer
    DHS `mean_years_education` (continuous years of schooling). Otherwise
    fall back to the census `literacy_rate_pct` (binary literate/not).
    Both are converted to a common normalized "education adequacy" scale
    [0,1] (higher = more educated) before blending, since they are on
    different raw scales (years vs. percentage) and cannot be compared
    directly.

    KNOWN EDGE CASE: Kohistan District has neither adequate DHS IR
    coverage NOR a usable census literacy figure (it is absent from the
    PBS Table 12 tehsil-level literacy source entirely -- see
    docs/LIMITATIONS.md #11 for why). It is the one district that falls
    through both the DHS-preferred and census-fallback paths and lands
    in the median-imputation branch below. This is logged explicitly by
    name here rather than silently absorbed, since a single median-
    imputed district in the education channel is a real, reportable
    data gap for a methods paper, not something to discover by
    inspecting a CSV.
    """
    has_dhs = (
        df["mean_years_education"].notna()
        & (~df["low_dhs_ir_coverage"].fillna(True))
    )

    educ_norm_dhs = minmax_normalize(df["mean_years_education"])
    educ_norm_census = minmax_normalize(df["literacy_rate_pct"])

    df["education_adequacy"] = np.where(has_dhs, educ_norm_dhs, educ_norm_census)
    df["education_data_source"] = np.where(has_dhs, "dhs", "census")

    still_missing = df["education_adequacy"].isna()
    if still_missing.any():
        missing_districts = df.loc[still_missing, "district_key"].tolist()
        print(
            f"  WARNING: {still_missing.sum()} district(s) have NEITHER "
            f"adequate DHS education data NOR a usable census literacy "
            f"figure, and are median-imputed as a last resort: "
            f"{missing_districts}. See docs/LIMITATIONS.md #11."
        )
        df.loc[still_missing, "education_adequacy"] = df["education_adequacy"].median()
        df.loc[still_missing, "education_data_source"] = "imputed_median"

    return df


def build_wealth_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """
    DHS-preferred, census-proxy-fallback wealth indicator. Where a
    district has adequate DHS HR coverage, use the continuous
    asset-based `mean_wealth_score` (DHS's standard PCA wealth index --
    the measure used throughout the global child-mortality literature).
    Otherwise fall back to the census WASH index as a rough proxy (WASH
    access correlates with wealth but is not the same construct -- this
    fallback is a real simplification, flagged via wealth_data_source).
    """
    has_dhs = (
        df["mean_wealth_score"].notna()
        & (~df["low_dhs_hr_coverage"].fillna(True))
    )

    wealth_norm_dhs = minmax_normalize(df["mean_wealth_score"])
    wash_as_wealth_proxy = df["wash_index"]  # already normalized [0,1]

    df["wealth_adequacy"] = np.where(has_dhs, wealth_norm_dhs, wash_as_wealth_proxy)
    df["wealth_data_source"] = np.where(has_dhs, "dhs", "census_wash_proxy")

    return df


def build_anc_deficit_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Antenatal care under-utilization. This has NO census equivalent --
    it is new information only available because DHS individual-level
    data was integrated. Higher = more deficit (fewer ANC visits).
    Districts without adequate DHS ANC coverage are median-imputed and
    flagged, since there is no fallback source for this indicator.
    """
    has_dhs = (
        df["mean_anc_visits"].notna()
        & (~df["low_dhs_anc_coverage"].fillna(True))
    )

    anc_norm = minmax_normalize(df["mean_anc_visits"])
    df["anc_deficit_index"] = np.where(has_dhs, 1 - anc_norm, np.nan)
    df["anc_data_source"] = np.where(has_dhs, "dhs", "missing")

    imputed = df["anc_deficit_index"].isna()
    df.loc[imputed, "anc_deficit_index"] = df["anc_deficit_index"].median()
    df.loc[imputed, "anc_data_source"] = "imputed_median"

    return df


def build_deprivation_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Composite socioeconomic deprivation index. Higher = more deprived.
    Literature-informed weighting (not equal weights), now built
    PREFERENTIALLY from DHS individual/household-level indicators
    (education_adequacy, wealth_adequacy) rather than pure census
    proxies, falling back to census only where DHS coverage is thin:

        35% inverse education adequacy  (DHS years-of-education where
                                          available, else census literacy;
                                          education is the single
                                          strongest socioeconomic
                                          predictor of child mortality
                                          in DHS-based LMIC studies)
        30% inverse wealth adequacy      (DHS asset-based wealth index
                                          where available, else census
                                          WASH proxy; wealth is the
                                          standard DHS/World Bank
                                          socioeconomic measure used
                                          throughout the child-mortality
                                          literature)
        20% inverse WASH index           (direct causal pathway:
                                          water/sanitation -> diarrheal
                                          disease -> child mortality;
                                          always census-derived, full
                                          coverage)
        15% household pressure           (crowding -> respiratory/
                                          infectious disease transmission;
                                          always census-derived)

    These weights are a starting assumption, not a fitted parameter --
    the decision engine's sensitivity analysis (Layer 4) lets a user
    perturb them and see how rankings change, which is the honest way
    to present an a-priori weighting scheme. Note ANC deficit is
    tracked as a SEPARATE index (anc_deficit_index) rather than folded
    into deprivation_index, since it measures health-service utilization
    rather than socioeconomic status -- a conceptually distinct
    construct worth keeping visible on its own.
    """
    df = build_education_indicator(df)
    df = build_wealth_indicator(df)

    inv_educ = 1 - df["education_adequacy"]
    inv_wealth = 1 - df["wealth_adequacy"]
    inv_wash = 1 - df["wash_index"]
    hh_pressure = df["household_pressure_index"]

    df["deprivation_index"] = (
        0.35 * inv_educ + 0.30 * inv_wealth + 0.20 * inv_wash + 0.15 * hh_pressure
    )

    # traceability: what mix of sources fed this district's index
    df["deprivation_data_source"] = (
        "education=" + df["education_data_source"] + ";wealth=" + df["wealth_data_source"]
    )
    return df


def build_under5_share(df: pd.DataFrame) -> pd.DataFrame:
    """% of population under 5 -- a standard demographic risk exposure
    indicator (higher child share = larger at-risk population, relevant
    for the decision engine's population-weighting component)."""
    df = impute_with_flag(df, "population_under5")
    df["under5_share_pct"] = 100 * df["population_under5"] / df["population_2017"]
    return df


def main():
    print(f"Loading {IN_PATH}...")
    df = pd.read_csv(IN_PATH)
    print(f"  {df.shape[0]} districts, {df.shape[1]} columns")

    print(f"Attaching province from {GEO_KEY_PATH}...")
    geo_key = pd.read_csv(GEO_KEY_PATH)[["district_key", "province"]]
    df = df.merge(geo_key, on="district_key", how="left")
    n_missing_province = df["province"].isna().sum()
    if n_missing_province:
        print(f"  WARNING: {n_missing_province} districts missing province after join")

    print(f"\nAttaching DHS-derived socioeconomic indicators from {DHS_SOCIOECONOMIC_PATH}...")
    if DHS_SOCIOECONOMIC_PATH.exists():
        dhs_socio = pd.read_csv(DHS_SOCIOECONOMIC_PATH)
        df = df.merge(dhs_socio, on="district_key", how="left")
        n_with_dhs = df["mean_wealth_score"].notna().sum()
        print(f"  {n_with_dhs}/{len(df)} districts have DHS HR/IR data available")
    else:
        print(
            "  WARNING: DHS socioeconomic file not found -- run "
            "scripts/cleaning/04_clean_dhs_hr_ir.py first. Proceeding with "
            "census-only indicators (all districts will fall back to census)."
        )
        for col in [
            "mean_wealth_score", "mean_years_education", "mean_anc_visits",
            "low_dhs_hr_coverage", "low_dhs_ir_coverage", "low_dhs_anc_coverage",
        ]:
            df[col] = np.nan

    print("\nBuilding WASH index...")
    df = build_wash_index(df)

    print("Building household pressure index...")
    df = build_household_pressure_index(df)

    print("Building remoteness proxy (STOPGAP -- see docstring)...")
    df = build_remoteness_proxy(df)

    print("Building under-5 population share...")
    df = build_under5_share(df)

    print("Building ANC deficit index (DHS-only, new indicator)...")
    df = build_anc_deficit_index(df)

    print("Building composite deprivation index (DHS-preferred, census-fallback)...")
    df = build_deprivation_index(df)

    out_path = OUT_DIR / "district_features.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")
    print(f"Final shape: {df.shape}")

    print("\nData source mix for deprivation_index:")
    print(df["education_data_source"].value_counts())
    print(df["wealth_data_source"].value_counts())

    print("\nTop 10 most deprived districts (by deprivation_index):")
    top = df.nlargest(10, "deprivation_index")[
        ["district_key", "deprivation_index", "deprivation_data_source", "anc_deficit_index"]
    ]
    print(top.to_string(index=False))

    print("\nImputation flags summary:")
    flag_cols = [c for c in df.columns if c.endswith("_imputed")]
    print(df[flag_cols].sum())


if __name__ == "__main__":
    main()
