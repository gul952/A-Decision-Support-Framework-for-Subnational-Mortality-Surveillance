"""
03_clean_dhs_cluster_geography.py

Layer 1 (Data Engineering) -- DHS cluster-to-district spatial join.

*** DHS COMPLIANCE BOUNDARY ***
This script reads raw DHS GPS microdata from data/raw/dhs/ (gitignored,
never committed/redistributed) and writes ONLY a district-level cluster
COUNT summary to data/processed/. No individual cluster coordinates,
no cluster IDs linkable to identifiable communities, and no
household/individual-level data cross the boundary out of this script.
This satisfies the DHS terms of use: microdata is used only to derive
non-identifying, aggregated district statistics.

GPS displacement note (per DHS's own GPS_Displacement_README.txt):
urban clusters are displaced up to 2km, rural up to 5km (1% up to
10km), restricted to stay within the second administrative level
where possible. This means a cluster's assigned district is generally
reliable, but a cluster very close to a district border could in
principle be displaced across it. We do not attempt to correct for
this (no correction is possible without re-identifying true locations,
which would itself violate DHS terms) -- it is a small, acknowledged
source of noise in the district assignment, noted in docs/LIMITATIONS.md.

Input:
    data/raw/dhs/2017-18_DHS_GPS/PKGE71FL/PKGE71FL.shp  (561 cluster points)
    data/processed/geography/districts.geojson           (135 district polygons)

Output:
    data/processed/dhs_derived/cluster_district_lookup.csv
        (DHSCLUST -> district_key mapping; cluster IDs are not
         individually identifying -- they're a survey design index,
         not a household/respondent identifier -- so this crosswalk
         is safe to keep in data/processed/, but note it is still
         DERIVED from restricted data and should not be published
         verbatim in the dashboard or paper; use only the resulting
         aggregate counts/estimates.)
    data/processed/dhs_derived/district_cluster_counts.csv
        (district_key, n_clusters_total, n_clusters_urban, n_clusters_rural
         -- this is the coverage diagnostic that justifies the SAE
         approach: districts with 0 clusters have zero direct DHS
         information and must borrow strength via the hierarchical model.)
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_RAW, DATA_PROCESSED, CRS_WGS84

DHS_GPS_PATH = DATA_RAW / "dhs" / "2017-18_DHS_GPS" / "PKGE71FL" / "PKGE71FL.shp"
DISTRICTS_PATH = DATA_PROCESSED / "geography" / "districts.geojson"
OUT_DIR = DATA_PROCESSED / "dhs_derived"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("Loading DHS GPS clusters (raw, will not leave this script)...")
    clusters = gpd.read_file(DHS_GPS_PATH).to_crs(CRS_WGS84)
    print(f"  {len(clusters)} clusters loaded")

    n_masked = ((clusters["LATNUM"] == 0) & (clusters["LONGNUM"] == 0)).sum()
    if n_masked:
        print(f"  Dropping {n_masked} cluster(s) with masked (0,0) coordinates")
        clusters = clusters[~((clusters["LATNUM"] == 0) & (clusters["LONGNUM"] == 0))]

    print(f"\nLoading district polygons from {DISTRICTS_PATH}...")
    districts = gpd.read_file(DISTRICTS_PATH)
    print(f"  {len(districts)} districts")

    print("\nSpatial join (cluster point -> containing district)...")
    joined = gpd.sjoin(
        clusters[["DHSCLUST", "ADM1NAME", "URBAN_RURA", "geometry"]],
        districts[["district_key", "province", "geometry"]],
        how="left",
        predicate="within",
    )

    n_unmatched = joined["district_key"].isna().sum()
    print(f"  {len(joined) - n_unmatched} / {len(joined)} clusters matched to a district")
    if n_unmatched:
        unmatched = joined[joined["district_key"].isna()].copy()
        matched = joined[joined["district_key"].notna()].copy()

        # Most unmatched clusters are in Azad Jammu & Kashmir / Gilgit-
        # Baltistan -- regions genuinely absent from the reconciled
        # 135-district geometry (see scripts/cleaning/01_clean_geography.py;
        # these regions were not part of the 2017 PBS district-level
        # census release we're using). These are NOT displacement noise
        # and are correctly excluded, not force-matched to a nearby
        # Pakistani-province district.
        clusters_full = clusters[["DHSCLUST", "ADM1NAME", "URBAN_RURA", "geometry"]]
        unmatched_adm1 = clusters_full[
            clusters_full["DHSCLUST"].isin(unmatched["DHSCLUST"])
        ]["ADM1NAME"].value_counts()
        print(f"  Unmatched cluster breakdown by DHS-reported region:\n{unmatched_adm1}")

        out_of_scope_regions = {"AZAD JAMMU AND KASHMIR", "GILGIT BALTISTAN"}
        genuinely_stray = unmatched[
            ~clusters_full.set_index("DHSCLUST")
            .loc[unmatched["DHSCLUST"], "ADM1NAME"]
            .isin(out_of_scope_regions)
            .values
        ]

        if len(genuinely_stray):
            print(
                f"  {len(genuinely_stray)} cluster(s) are in-scope provinces but "
                "fell just outside district polygons (likely GPS displacement "
                "at a border, up to 2-5km per DHS policy). Assigning via "
                "nearest-polygon fallback in a projected CRS..."
            )
            stray_pts = clusters_full[
                clusters_full["DHSCLUST"].isin(genuinely_stray["DHSCLUST"])
            ].to_crs("EPSG:24313")
            districts_proj = districts.to_crs("EPSG:24313")
            nearest = gpd.sjoin_nearest(
                stray_pts,
                districts_proj[["district_key", "province", "geometry"]],
                how="left",
            ).to_crs(CRS_WGS84)
            joined = pd.concat([matched, nearest], ignore_index=True)

        n_excluded = len(unmatched) - len(genuinely_stray)
        print(
            f"  Excluding {n_excluded} cluster(s) in AJK/Gilgit-Baltistan "
            "(outside this project's 135-district scope) from the "
            "district-level lookup."
        )
        joined = joined[joined["district_key"].notna()]

    # --- Output 1: cluster -> district lookup (derived, not raw survey data) ---
    lookup = joined[["DHSCLUST", "URBAN_RURA", "district_key", "province"]].drop_duplicates(
        subset="DHSCLUST"
    )
    lookup_path = OUT_DIR / "cluster_district_lookup.csv"
    lookup.to_csv(lookup_path, index=False)
    print(f"\nWrote: {lookup_path}")

    # --- Output 2: district-level cluster COUNT summary (aggregate only) ---
    counts = (
        lookup.groupby("district_key")
        .agg(
            n_clusters_total=("DHSCLUST", "count"),
            n_clusters_urban=("URBAN_RURA", lambda x: (x == "U").sum()),
            n_clusters_rural=("URBAN_RURA", lambda x: (x == "R").sum()),
        )
        .reset_index()
    )

    # merge onto full district list so zero-cluster districts are explicit,
    # not just absent rows
    all_districts = districts[["district_key", "province"]].copy()
    coverage = all_districts.merge(counts, on="district_key", how="left")
    for col in ["n_clusters_total", "n_clusters_urban", "n_clusters_rural"]:
        coverage[col] = coverage[col].fillna(0).astype(int)

    coverage_path = OUT_DIR / "district_cluster_counts.csv"
    coverage.to_csv(coverage_path, index=False)
    print(f"Wrote: {coverage_path}")

    n_zero = (coverage["n_clusters_total"] == 0).sum()
    print(
        f"\n{n_zero} / {len(coverage)} districts have ZERO sampled DHS clusters "
        "-- these have no direct survey information and depend entirely on "
        "small-area estimation (hierarchical borrowing across province) for "
        "any mortality estimate. This is precisely the coverage gap this "
        "project's SAE approach exists to address."
    )
    print("\nCluster count distribution:")
    print(coverage["n_clusters_total"].describe())


if __name__ == "__main__":
    main()
