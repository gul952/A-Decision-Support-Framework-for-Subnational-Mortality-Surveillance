"""
01_clean_geography.py

Layer 1 (Data Engineering): standardize the district boundary shapefile,
reconcile its naming against the PBS 2017 census district list, and emit
a clean GeoJSON + a district master key used to join every other dataset.

Input:
    data/raw/pbs2017-main/data/00_shapefiles/District_Boundary.shp
    data/raw/pbs2017-main/data/01/01_district_aggregated.csv  (census district list)

Output:
    data/processed/geography/districts.geojson
    data/processed/geography/district_master_key.csv
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import (
    SHAPEFILE_DIR,
    PBS2017_DIR,
    DATA_PROCESSED,
    CRS_WGS84,
    standardize_district_name,
)

OUT_DIR = DATA_PROCESSED / "geography"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Known naming divergences between the shapefile's DISTRICT field and the
# PBS census `district` column, found by inspection of the unmatched-district
# diagnostic log (data/processed/geography/unmatched_districts_log.csv).
# Left side = shapefile name (upper, no "DISTRICT" suffix as it appears in
# the raw shapefile), right side = canonical census key.
SHAPEFILE_TO_CENSUS_OVERRIDES = {
    "SHAHEED BENAZIRABAD": "SHAHEED BENAZIRABAD DISTRICT",
    "NAWABSHAH": "SHAHEED BENAZIRABAD DISTRICT",
    "S. BENAZIRABAD": "SHAHEED BENAZIRABAD DISTRICT",
    "D G KHAN": "DERA GHAZI KHAN DISTRICT",
    "D.G. KHAN": "DERA GHAZI KHAN DISTRICT",
    "D I KHAN": "DERA ISMAIL KHAN DISTRICT",
    "D.I. KHAN": "DERA ISMAIL KHAN DISTRICT",
    "MUZAFARGARH": "MUZAFFARGARH DISTRICT",
    "MIRPURKHAS": "MIRPUR KHAS DISTRICT",
    "SHAHDAD KOT": "KAMBAR SHAHDAD KOT DISTRICT",
    "SHIKARPHUR": "SHIKARPUR DISTRICT",
    "MUSA KHEL": "MUSAKHEL DISTRICT",
    "SHEERANI": "SHERANI DISTRICT",
    "N. WAZIRASTAN": "NORTH WAZIRISTAN AGENCY DISTRICT",
    "S. WAZIRASTAN": "SOUTH WAZIRISTAN A DISTRICT",
    "NANKANA SAHIB": "NANKANA SAHIB DISTRICT",
    "NAUSHAHRO FEROZ": "NAUSHAHRO FEROZE DISTRICT",
    "R Y KHAN": "RAHIM YAR KHAN DISTRICT",
    "SUJJAWAL": "SUJAWAL DISTRICT",
    "T. AYAR": "TANDO ALLAHYAR DISTRICT",
    "T. M KHAN": "TANDO MUHAMMAD KHAN DISTRICT",
    "T. T SINGH": "TOBA TEK SINGH DISTRICT",
    "TORDHER": "TORGHAR DISTRICT",
    "UMERKOT": "UMER KOT DISTRICT",
    "LOWER KOHISTAN": "KOHISTAN DISTRICT",
    "UPPER KOHISTAN": "KOHISTAN DISTRICT",
    # Districts genuinely absent from the 2017 PBS district-level table
    # (AJK / Gilgit-Baltistan were enumerated but not all released at
    # district level in this table; cantonments are sub-district military
    # areas folded into their parent district by census convention) are
    # intentionally left unmapped -- they surface in the unmatched log
    # rather than being silently merged into an unrelated district.
}

# The digitized PBS census CSV has two data-entry typos in the `district`
# column itself (trailing "DISTRIC" instead of "DISTRICT", which then gets
# double-suffixed by standardize_district_name). Fixed at source so the
# canonical key is clean and matches the shapefile-side overrides above.
CENSUS_RAW_TYPO_FIXES = {
    "NANKANA SAHIB DISTRIC": "NANKANA SAHIB",
    "TANDO MUHAMMAD KHAN DISTRIC": "TANDO MUHAMMAD KHAN",
}


def load_shapefile() -> gpd.GeoDataFrame:
    """
    Load the raw district boundary shapefile. Note: this source
    includes polygons and PROVINCE labels outside this project's
    census-defined 135-district scope (Azad Kashmir, Gilgit-Baltistan,
    and one polygon labeled "Indian Occupied Kashmir" in the raw
    source file). These labels are inherited verbatim from the
    third-party shapefile and are not authored or endorsed by this
    project. All such out-of-scope polygons are excluded from the
    reconciled output below via the inner join against the census
    district list -- not because of their labels, but because they are
    outside the PBS 2017 census release this project's district list is
    built from. See docs/LIMITATIONS.md #1 for the full explanation.
    """
    gdf = gpd.read_file(SHAPEFILE_DIR / "District_Boundary.shp")
    gdf = gdf.to_crs(CRS_WGS84)
    gdf["district_key"] = gdf["DISTRICT"].apply(
        lambda x: SHAPEFILE_TO_CENSUS_OVERRIDES.get(
            str(x).strip().upper(), standardize_district_name(x)
        )
    )
    gdf["province"] = gdf["PROVINCE"].str.strip().str.title()
    return gdf


def load_census_district_list() -> pd.DataFrame:
    df = pd.read_csv(PBS2017_DIR / "01" / "01_district_aggregated.csv")
    df["district_raw_fixed"] = df["district"].str.strip().replace(
        CENSUS_RAW_TYPO_FIXES
    )
    df["district_key"] = df["district_raw_fixed"].apply(standardize_district_name)
    return df[["district_key", "area_sqkm", "all_sex"]].rename(
        columns={"all_sex": "census_population_2017"}
    )


def reconcile(gdf: gpd.GeoDataFrame, census: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Dissolve shapefile polygons to one row per canonical district_key
    (handles cases where a district was split post-2010 shapefile vintage,
    or where the shapefile has duplicate/sub-unit polygons for one census
    district), then flag any districts present in one source but not
    the other for manual review rather than silently dropping them.
    """
    gdf_dissolved = gdf.dissolve(
        by="district_key", as_index=False, aggfunc={"province": "first"}
    )
    gdf_dissolved = gdf_dissolved[["district_key", "province", "geometry"]]

    shp_keys = set(gdf_dissolved["district_key"])
    census_keys = set(census["district_key"])

    only_in_shapefile = sorted(shp_keys - census_keys)
    only_in_census = sorted(census_keys - shp_keys)

    print(f"Districts in shapefile only (no census match): {len(only_in_shapefile)}")
    for d in only_in_shapefile:
        print(f"  - {d}")
    print(f"\nDistricts in census only (no shapefile match): {len(only_in_census)}")
    for d in only_in_census:
        print(f"  - {d}")

    merged = gdf_dissolved.merge(census, on="district_key", how="inner")
    print(f"\nFinal reconciled districts (matched in both): {len(merged)}")

    n_invalid = (~merged.geometry.is_valid).sum()
    if n_invalid:
        print(f"Repairing {n_invalid} invalid geometries via buffer(0)...")
        merged["geometry"] = merged.geometry.buffer(0)

    unmatched_log = pd.DataFrame(
        {
            "district_key": only_in_shapefile + only_in_census,
            "source": (["shapefile_only"] * len(only_in_shapefile))
            + (["census_only"] * len(only_in_census)),
        }
    )
    unmatched_log.to_csv(OUT_DIR / "unmatched_districts_log.csv", index=False)

    return merged


def main():
    print("Loading shapefile...")
    gdf = load_shapefile()
    print(f"  {len(gdf)} raw polygon features, {gdf['district_key'].nunique()} unique keys")

    print("\nLoading census district list...")
    census = load_census_district_list()
    print(f"  {len(census)} census districts")

    print("\nReconciling...")
    merged = reconcile(gdf, census)

    merged = merged.set_geometry("geometry")
    merged.to_file(OUT_DIR / "districts.geojson", driver="GeoJSON")

    master_key = merged.drop(columns="geometry")
    master_key.to_csv(OUT_DIR / "district_master_key.csv", index=False)

    print(f"\nWrote: {OUT_DIR / 'districts.geojson'}")
    print(f"Wrote: {OUT_DIR / 'district_master_key.csv'}")
    print(f"Wrote: {OUT_DIR / 'unmatched_districts_log.csv'}")


if __name__ == "__main__":
    main()
