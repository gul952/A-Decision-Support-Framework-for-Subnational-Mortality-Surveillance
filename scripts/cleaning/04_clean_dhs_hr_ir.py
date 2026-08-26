"""
04_clean_dhs_hr_ir.py

Layer 1 (Data Engineering) -- district-aggregated DHS Household (HR) and
Individual/Women's (IR) recode indicators, to REPLACE the census-derived
literacy/WASH proxies used in Layer 2 with richer, individual-level DHS
measures wherever DHS coverage allows.

*** DHS COMPLIANCE BOUNDARY ***
Reads raw HR/IR microdata from data/raw/dhs/ (gitignored, never
committed/redistributed). Writes ONLY district-aggregated, weighted
summary statistics to data/processed/ -- no household or individual
records leave this script.

WHY THIS MATTERS (addresses a real reviewer question): the original
Layer 2 composite indices (deprivation_index, wash_index) were built
from PBS 2017 CENSUS variables -- binary "improved water: yes/no" at
household level, literacy as a simple percentage. DHS's Household and
Individual recodes carry substantially richer measures for the same
underlying constructs:
    - hv271 (wealth index factor score): a continuous asset-based wealth
      measure (PCA over ~30 household assets/characteristics), the
      standard DHS/World Bank socioeconomic measure used throughout the
      global child-mortality literature -- more granular than a binary
      "improved water" indicator.
    - v133 (education in single years): continuous years of schooling
      per woman, vs. census's simple literacy percentage.
    - m14_1 (antenatal care visits): a direct health-service-utilization
      indicator with no PBS census equivalent at all -- this is new
      information, not a refinement of an existing indicator.

This script produces a SEPARATE district-level file
(district_dhs_socioeconomic.csv) rather than overwriting the census-
based file, so both are preserved and comparable -- see
scripts/features/01_build_composite_indices.py for how the two are
combined (DHS-derived indicators used preferentially where a district
has adequate DHS coverage, falling back to census indicators elsewhere).

Output:
    data/processed/dhs_derived/district_dhs_socioeconomic.csv
        columns: district_key, n_households_hr, mean_wealth_score,
                 pct_lowest_wealth_quintile, n_women_ir,
                 mean_years_education, pct_no_education,
                 mean_anc_visits, pct_zero_anc_visits
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_RAW, DATA_PROCESSED

HR_PATH = DATA_RAW / "dhs" / "2017-18_DHS_GPS" / "PKHR71DT" / "PKHR71FL.DTA"
IR_PATH = DATA_RAW / "dhs" / "2017-18_DHS_GPS" / "PKIR71DT" / "PKIR71FL.DTA"
CLUSTER_LOOKUP_PATH = DATA_PROCESSED / "dhs_derived" / "cluster_district_lookup.csv"
OUT_DIR = DATA_PROCESSED / "dhs_derived"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_RECORDS_FOR_DISTRICT_ESTIMATE = 30  # below this, district-level DHS
                                          # mean is considered unstable and
                                          # flagged (same convention as
                                          # low_direct_coverage in
                                          # 02b_estimate_u5mr_from_dhs.py)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna()
    if mask.sum() == 0:
        return np.nan
    return np.average(values[mask], weights=weights[mask])


def clean_hr_wealth(lookup: pd.DataFrame) -> pd.DataFrame:
    print(f"Loading HR file from {HR_PATH}...")
    hr = pd.read_stata(HR_PATH, convert_categoricals=False)
    print(f"  {len(hr)} households")

    hr = hr.copy()
    hr["weight"] = hr["hv005"] / 1_000_000.0
    hr["wealth_score"] = hr["hv271"] / 100_000.0  # DHS standard rescale
    hr["is_lowest_quintile"] = (hr["hv270"] == 1).astype(float)

    hr = hr.merge(
        lookup[["DHSCLUST", "district_key"]],
        left_on="hv001",
        right_on="DHSCLUST",
        how="left",
    )
    n_unmatched = hr["district_key"].isna().sum()
    if n_unmatched:
        print(
            f"  {n_unmatched} households in out-of-scope clusters "
            "(AJK/Gilgit-Baltistan) excluded."
        )
        hr = hr[hr["district_key"].notna()]

    print("Aggregating wealth indicators by district...")
    rows = []
    for district, group in hr.groupby("district_key"):
        rows.append(
            {
                "district_key": district,
                "n_households_hr": len(group),
                "mean_wealth_score": weighted_mean(group["wealth_score"], group["weight"]),
                "pct_lowest_wealth_quintile": 100
                * weighted_mean(group["is_lowest_quintile"], group["weight"]),
            }
        )
    return pd.DataFrame(rows)


def clean_ir_education_anc(lookup: pd.DataFrame) -> pd.DataFrame:
    print(f"\nLoading IR file from {IR_PATH}...")
    ir = pd.read_stata(IR_PATH, convert_categoricals=False)
    print(f"  {len(ir)} women")

    ir["weight"] = ir["v005"] / 1_000_000.0
    ir["years_education"] = ir["v133"].where(ir["v133"] < 90)  # drop DHS
                                                                  # missing codes
    ir["no_education"] = (ir["v106"] == 0).astype(float)

    # m14_1: antenatal visits for most recent birth in the 5yr reference
    # window. 98 = "don't know" (DHS missing code), NaN = no birth in
    # window to ask about -- both correctly excluded from the mean, but
    # kept distinct from "0 visits" (a real, meaningful value).
    ir["anc_visits"] = ir["m14_1"].where(ir["m14_1"] < 90)
    ir["zero_anc"] = (ir["anc_visits"] == 0).astype(float)

    ir = ir.merge(
        lookup[["DHSCLUST", "district_key"]],
        left_on="v001",
        right_on="DHSCLUST",
        how="left",
    )
    n_unmatched = ir["district_key"].isna().sum()
    if n_unmatched:
        print(
            f"  {n_unmatched} women in out-of-scope clusters "
            "(AJK/Gilgit-Baltistan) excluded."
        )
        ir = ir[ir["district_key"].notna()]

    print("Aggregating education/ANC indicators by district...")
    rows = []
    for district, group in ir.groupby("district_key"):
        rows.append(
            {
                "district_key": district,
                "n_women_ir": len(group),
                "mean_years_education": weighted_mean(group["years_education"], group["weight"]),
                "pct_no_education": 100 * weighted_mean(group["no_education"], group["weight"]),
                "n_women_with_recent_birth": group["anc_visits"].notna().sum(),
                "mean_anc_visits": weighted_mean(group["anc_visits"], group["weight"]),
                "pct_zero_anc_visits": 100 * weighted_mean(group["zero_anc"], group["weight"]),
            }
        )
    return pd.DataFrame(rows)


def main():
    print(f"Loading cluster->district lookup from {CLUSTER_LOOKUP_PATH}...")
    lookup = pd.read_csv(CLUSTER_LOOKUP_PATH)

    wealth = clean_hr_wealth(lookup)
    educ_anc = clean_ir_education_anc(lookup)

    merged = wealth.merge(educ_anc, on="district_key", how="outer")

    merged["low_dhs_hr_coverage"] = (
        merged["n_households_hr"].fillna(0) < MIN_RECORDS_FOR_DISTRICT_ESTIMATE
    )
    merged["low_dhs_ir_coverage"] = (
        merged["n_women_ir"].fillna(0) < MIN_RECORDS_FOR_DISTRICT_ESTIMATE
    )
    merged["low_dhs_anc_coverage"] = (
        merged["n_women_with_recent_birth"].fillna(0) < MIN_RECORDS_FOR_DISTRICT_ESTIMATE
    )

    out_path = OUT_DIR / "district_dhs_socioeconomic.csv"
    merged.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")
    print(f"Districts with any DHS HR/IR data: {len(merged)}")
    print(f"Districts with low HR coverage (<{MIN_RECORDS_FOR_DISTRICT_ESTIMATE} hh): {merged['low_dhs_hr_coverage'].sum()}")
    print(f"Districts with low IR coverage (<{MIN_RECORDS_FOR_DISTRICT_ESTIMATE} women): {merged['low_dhs_ir_coverage'].sum()}")
    print(f"Districts with low ANC coverage (<{MIN_RECORDS_FOR_DISTRICT_ESTIMATE} recent births): {merged['low_dhs_anc_coverage'].sum()}")

    print("\nSanity check -- national aggregates:")
    print(f"  Mean years of education (unweighted district avg): {merged['mean_years_education'].mean():.2f}")
    print(f"  Mean ANC visits (unweighted district avg): {merged['mean_anc_visits'].mean():.2f}")
    print(f"  Mean % lowest wealth quintile (unweighted district avg): {merged['pct_lowest_wealth_quintile'].mean():.1f}%")


if __name__ == "__main__":
    main()
