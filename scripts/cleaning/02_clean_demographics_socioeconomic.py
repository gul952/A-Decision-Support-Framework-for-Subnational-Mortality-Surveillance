"""
02_clean_demographics_socioeconomic.py

Layer 1 (Data Engineering): clean and district-aggregate PBS 2017 census
tables covering population/density/urbanization, age structure (for
under-5 population), literacy, household crowding, water source, and
sanitation. Each sub-cleaner is independent and testable; main() joins
them into one district-level demographic/socioeconomic panel.

Inputs (data/raw/pbs2017-main/data/):
    01/01_district_aggregated.csv         -- population, area, density, urban%
    08/08_district_disaggregated.csv      -- age structure (for u5 pop)
    12/12_tehsil_disaggregated.csv        -- literacy (aggregated up to district)
    29/19_district_aggregated.csv         -- household crowding (rooms per hh)
    35/35_district_disaggregated.csv      -- water source, cooking fuel, lighting
    37/37_district_aggregated.csv         -- kitchen/bathroom/latrine facilities

Output:
    data/processed/demographics/district_demographics_socioeconomic.csv
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import PBS2017_DIR, DATA_PROCESSED, standardize_district_name

OUT_DIR = DATA_PROCESSED / "demographics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same typo fixes as the geography script -- kept in sync so district_key
# values match district_master_key.csv exactly.
CENSUS_RAW_TYPO_FIXES = {
    "NANKANA SAHIB DISTRIC": "NANKANA SAHIB",
    "TANDO MUHAMMAD KHAN DISTRIC": "TANDO MUHAMMAD KHAN",
}


def _std_key(series: pd.Series) -> pd.Series:
    fixed = series.str.strip().replace(CENSUS_RAW_TYPO_FIXES)
    return fixed.apply(standardize_district_name)


def clean_population_table() -> pd.DataFrame:
    """Table 1: population, area, density, urban proportion, sex ratio."""
    df = pd.read_csv(PBS2017_DIR / "01" / "01_district_aggregated.csv")
    df["district_key"] = _std_key(df["district"])
    df = df.rename(
        columns={
            "all_sex": "population_2017",
            "pop_density_sqkm": "pop_density_per_sqkm",
            "urban_proportion": "urban_pct",
            "avg_hhsize": "avg_household_size",
            "pop_growth_avg_1998_2017": "pop_growth_rate_pct",
        }
    )
    keep = [
        "district_key",
        "area_sqkm",
        "population_2017",
        "male",
        "female",
        "sex_ratio",
        "pop_density_per_sqkm",
        "urban_pct",
        "avg_household_size",
        "pop_growth_rate_pct",
    ]
    return df[keep].drop_duplicates(subset="district_key")


def clean_under5_population() -> pd.DataFrame:
    """Table 8: extract 00-04 age band population as U5 pop denominator."""
    df = pd.read_csv(PBS2017_DIR / "08" / "08_district_disaggregated.csv")
    df = df[df["age_group"].str.strip() == "00 - 04"].copy()
    df["district_key"] = _std_key(df["district"])
    # sum across locale (Rural/Urban) and sex to get total U5 pop per district
    agg = df.groupby("district_key", as_index=False)["total_pop"].sum()
    agg = agg.rename(columns={"total_pop": "population_under5"})
    return agg


def clean_literacy() -> pd.DataFrame:
    """
    Table 12: only available at tehsil level in this source. Aggregate
    up to district by summing total_pop and literate_total across all
    tehsils/locales/sexes/age-groups, then recompute the ratio -- this is
    a proper weighted aggregation, not an average of pre-computed ratios
    (which would misweight small tehsils).
    """
    df = pd.read_csv(PBS2017_DIR / "12" / "12_tehsil_disaggregated.csv")
    df["district_key"] = _std_key(df["district"])
    agg = df.groupby("district_key", as_index=False)[
        ["total_pop", "literate_total"]
    ].sum()
    agg["literacy_rate_pct"] = (
        100 * agg["literate_total"] / agg["total_pop"].replace(0, pd.NA)
    )
    return agg[["district_key", "literacy_rate_pct"]]


def clean_household_crowding() -> pd.DataFrame:
    """
    Table 29: household counts by household size x number of rooms.
    Derive mean persons-per-room as a crowding indicator (a known
    correlate of infectious disease transmission risk).
    """
    df = pd.read_csv(PBS2017_DIR / "29" / "19_district_aggregated.csv")
    df["district_key"] = _std_key(df["district"])

    room_cols = [c for c in df.columns if c.startswith("room_in_house_")]
    # household size is encoded as a categorical string e.g. "1 PERSON",
    # "10 PERSONS AND ABOVE" -- extract the leading integer, capping the
    # open-ended top category at 10 for a conservative crowding estimate.
    df["hhsize_n"] = (
        df["hhsize"].str.extract(r"(\d+)").astype(float)
    )

    rows = []
    for _, row in df.iterrows():
        hhsize = row["hhsize_n"]
        for col in room_cols:
            n_rooms = int(col.split("_")[-1])
            n_households = row[col]
            if pd.isna(n_households) or n_households == 0:
                continue
            rows.append(
                {
                    "district_key": row["district_key"],
                    "households": n_households,
                    "persons_per_room": hhsize / n_rooms,
                }
            )
    long = pd.DataFrame(rows)
    long["weighted_ppr"] = long["persons_per_room"] * long["households"]
    agg = long.groupby("district_key", as_index=False).agg(
        total_households=("households", "sum"),
        weighted_ppr_sum=("weighted_ppr", "sum"),
    )
    agg["mean_persons_per_room"] = agg["weighted_ppr_sum"] / agg["total_households"]
    return agg[["district_key", "mean_persons_per_room"]]


def clean_water_source() -> pd.DataFrame:
    """
    Table 35: % of households with piped/improved drinking water inside
    the home. "Improved" here = Tap or Electric/Hand Pump, Inside --
    a standard WASH-indicator simplification.
    """
    df = pd.read_csv(PBS2017_DIR / "35" / "35_district_disaggregated.csv")
    df = df[
        (df["localities"] == "All") & (df["head"] == "Source Of Drinking Water")
    ].copy()
    df["district_key"] = _std_key(df["district"])

    improved_mask = (df["water_type"] == "Inside") & (
        df["source"].isin(["Tap", "Electric/Hand Pump"])
    )
    totals = df.groupby("district_key", as_index=False)["total"].sum().rename(
        columns={"total": "total_households_water"}
    )
    improved = (
        df[improved_mask]
        .groupby("district_key", as_index=False)["total"]
        .sum()
        .rename(columns={"total": "improved_water_households"})
    )
    merged = totals.merge(improved, on="district_key", how="left")
    merged["improved_water_households"] = merged["improved_water_households"].fillna(0)
    merged["improved_water_pct"] = (
        100 * merged["improved_water_households"] / merged["total_households_water"]
    )
    return merged[["district_key", "improved_water_pct"]]


def clean_sanitation() -> pd.DataFrame:
    """
    Table 37: % of households with a latrine connected to sewerage or
    septic tank (improved sanitation, WASH-indicator convention).
    """
    df = pd.read_csv(PBS2017_DIR / "37" / "37_district_aggregated.csv")
    df = df[(df["localities"] == "All") & (df["facility"] == "Latrine")].copy()
    df["district_key"] = _std_key(df["district"])

    improved_mask = df["type"].isin(
        ["Connected With Sewerage", "Connected With Septic Tank"]
    )
    totals = df.groupby("district_key", as_index=False)["total"].sum().rename(
        columns={"total": "total_households_sanitation"}
    )
    improved = (
        df[improved_mask]
        .groupby("district_key", as_index=False)["total"]
        .sum()
        .rename(columns={"total": "improved_sanitation_households"})
    )
    merged = totals.merge(improved, on="district_key", how="left")
    merged["improved_sanitation_households"] = merged[
        "improved_sanitation_households"
    ].fillna(0)
    merged["improved_sanitation_pct"] = (
        100
        * merged["improved_sanitation_households"]
        / merged["total_households_sanitation"]
    )
    return merged[["district_key", "improved_sanitation_pct"]]


def main():
    print("Cleaning Table 01 (population)...")
    pop = clean_population_table()
    print(f"  {len(pop)} districts")

    print("Cleaning Table 08 (under-5 population)...")
    u5 = clean_under5_population()
    print(f"  {len(u5)} districts")

    print("Cleaning Table 12 (literacy, tehsil->district aggregated)...")
    lit = clean_literacy()
    print(f"  {len(lit)} districts")

    print("Cleaning Table 29 (household crowding)...")
    crowd = clean_household_crowding()
    print(f"  {len(crowd)} districts")

    print("Cleaning Table 35 (improved water source)...")
    water = clean_water_source()
    print(f"  {len(water)} districts")

    print("Cleaning Table 37 (improved sanitation)...")
    sani = clean_sanitation()
    print(f"  {len(sani)} districts")

    print("\nJoining on district_key (outer join, tracking coverage)...")
    panel = pop
    for name, df in [
        ("u5_population", u5),
        ("literacy", lit),
        ("crowding", crowd),
        ("water", water),
        ("sanitation", sani),
    ]:
        before = len(panel)
        panel = panel.merge(df, on="district_key", how="left")
        n_missing = panel[df.columns[-1]].isna().sum()
        print(f"  after {name}: {len(panel)} rows, {n_missing} missing values introduced")

    # urban_pct is genuinely undefined (not missing-at-random) for districts
    # with zero census-designated urban localities -- almost entirely former
    # FATA agencies/Frontier Regions and a handful of remote KP districts.
    # True urbanization there is 0%, so we impute 0 rather than leave NaN
    # (which would otherwise propagate as a silent dropped row downstream).
    zero_urban_before = panel["urban_pct"].isna().sum()
    panel["urban_pct"] = panel["urban_pct"].fillna(0.0)
    print(
        f"\nImputed urban_pct=0 for {zero_urban_before} districts with no "
        "census-designated urban localities (mostly former FATA agencies)."
    )

    out_path = OUT_DIR / "district_demographics_socioeconomic.csv"
    panel.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")
    print(f"Final shape: {panel.shape}")
    print("\nMissingness summary:")
    print(panel.isna().sum())


if __name__ == "__main__":
    main()
