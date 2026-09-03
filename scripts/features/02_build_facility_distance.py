"""
02_build_facility_distance.py

Layer 2 (Feature Engineering) addition -- builds `facility_distance_km`,
a real geographic accessibility covariate computed from actual health
facility locations, to compare against (not silently replace)
`remoteness_proxy` (the population-density-inverse stopgap; see
docs/LIMITATIONS.md Sec 5).

*** DATA SOURCE ***
Pakistan health facility points, exported from OpenStreetMap via the
HOTOSM Raw Data API on 2026-05-06. Source file:
data/raw/health_facilities/hotosm_pak_health_facilities_points_geojson.geojson
License: Open Database License (ODbL) 1.0 -- see accompanying
HDX_Readme.txt. This is real, openly-licensed, community-mapped data,
not a synthetic or estimated substitute.

*** METHOD ***
1. Filter to facility types offering plausible clinical maternal/child
   care: OSM `amenity` in {hospital, clinic, doctors} OR `healthcare`
   in {hospital, clinic, doctor, centre}. Excludes pharmacies, dentists,
   and standalone labs, which are not proxies for delivery/inpatient/
   emergency child-health access.
2. Spatially join each retained facility point to its containing
   district polygon (data/processed/geography/districts.geojson).
3. Compute the district's population-weighted centroid is NOT used here
   (no sub-district population raster available); instead each
   district's geometric centroid is used as the reference point,
   projected to EPSG:24313 (Pakistan equal-area grid) for a valid
   planar distance in km. This is a real limitation, not hidden --
   see the docstring note on centroid choice below.
4. `facility_distance_km` = distance from the district centroid to the
   nearest facility point IN ANY district (not restricted to
   within-district facilities), since real patients cross district
   lines for care and a same-district facility right at the border is
   not meaningfully different from a neighboring-district facility
   just across it.
5. `facility_count_in_district` = raw count of retained facilities
   whose point falls within the district polygon (diagnostic only,
   not part of the covariate itself, since raw counts do not adjust
   for district area or population).

*** THE OSM COVERAGE BIAS PROBLEM (real finding, not swept under) ***
OpenStreetMap contributor density is itself geographically uneven and
strongly urban-biased. In this export:
    - 4,376 total facility points nationally.
    - 3,116 retained after the clinical-relevance filter.
    - Karachi's four districts alone account for ~1,100 of them.
    - 35 of Pakistan's 135 districts (26%) contain ZERO retained
      facility points -- overwhelmingly rural Balochistan districts
      (Awaran, Barkhan, Dera Bugti, Kalat, Kech, Kharan, Khuzdar,
      Kohlu, Mastung, ...) and former FATA agencies (the FR-prefixed
      districts).
A naive nearest-facility distance for these 35 districts would show
them as extremely remote -- but this is very likely a "not yet mapped
on OSM" artifact, not evidence that zero clinics exist there. Treating
that as a genuine, trustworthy extreme accessibility deficit would be
a real and serious bias: it would make the covariate MOST unreliable
in precisely the low-connectivity districts this project's decision
engine is trying to correctly prioritize.

*** HANDLING (explicit, not silent) ***
Every district gets a `low_osm_facility_coverage` boolean flag (true
if zero retained facilities fall within its polygon). For those
districts, `facility_distance_km` is still computed and reported (the
nearest facility may genuinely be in a neighboring district, which is
informative), but the flag must travel with the number everywhere it
is used -- in the model, in any figure, and in the paper -- so a
reader can distinguish "genuinely far from any mapped facility" from
"this area is under-mapped and the true distance is unknown, possibly
much shorter." This mirrors the existing `low_direct_coverage` /
`low_dhs_hr_coverage` pattern already used elsewhere in this pipeline
for DHS sample-size thresholds -- same philosophy, applied to a new
data source with its own, different coverage problem.

*** WHY THIS IS ADDED ALONGSIDE, NOT INSTEAD OF, remoteness_proxy ***
Per docs/LIMITATIONS.md Sec 5's documented next-step plan: add as a
new feature, then let the existing sensitivity-analysis framework
(scripts/decision/02_sensitivity_analysis.py) compare the two
empirically before any decision to swap the decision engine over to
this one. Given the coverage bias above, that comparison -- and
whether facility_distance_km should be trusted over remoteness_proxy
specifically in the 35 low-coverage districts -- is itself a finding
worth reporting, not a foregone conclusion.

Output: data/processed/features/facility_distance.csv
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pkmortality.config import DATA_PROCESSED, DATA_RAW, CRS_WGS84, CRS_PAKISTAN_EQUAL_AREA

FACILITY_GEOJSON = (
    DATA_RAW / "health_facilities" / "hotosm_pak_health_facilities_points_geojson.geojson"
)
DISTRICTS_GEOJSON = DATA_PROCESSED / "geography" / "districts.geojson"
OUT_PATH = DATA_PROCESSED / "features" / "facility_distance.csv"

# OSM tag values considered plausible maternal/child clinical care sites.
# Excludes pharmacy, dentist, laboratory (standalone), and other non-
# clinical-care tags present in the raw export -- see module docstring.
KEEP_AMENITY = {"hospital", "clinic", "doctors"}
KEEP_HEALTHCARE = {"hospital", "clinic", "doctor", "centre"}


def load_facilities() -> gpd.GeoDataFrame:
    """Load and filter the OSM facility export to clinically relevant types."""
    import json

    with open(FACILITY_GEOJSON) as f:
        raw = json.load(f)

    n_total = len(raw["features"])
    kept = []
    for feat in raw["features"]:
        p = feat["properties"]
        amenity = p.get("amenity")
        healthcare = p.get("healthcare")
        if amenity in KEEP_AMENITY or healthcare in KEEP_HEALTHCARE:
            kept.append(
                {
                    "geometry": shape(feat["geometry"]),
                    "name": p.get("name"),
                    "amenity": amenity,
                    "healthcare": healthcare,
                    "osm_id": p.get("osm_id"),
                }
            )

    gdf = gpd.GeoDataFrame(kept, crs=CRS_WGS84)
    print(f"Loaded {n_total} total OSM points; retained {len(gdf)} after "
          f"clinical-relevance filter.")
    return gdf


def compute_facility_distance(
    districts: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame
) -> pd.DataFrame:
    """
    For each district, compute:
      - facility_count_in_district: count of retained facilities within its polygon
      - facility_distance_km: distance from district CENTROID to nearest
        facility anywhere in the country (not restricted to same district)
      - low_osm_facility_coverage: True if facility_count_in_district == 0

    NOTE on centroid choice: this uses each district's GEOMETRIC centroid
    (polygon centroid), not a population-weighted centroid, because no
    sub-district population raster is available in this pipeline. For
    large, unevenly-populated districts (again, disproportionately in
    Balochistan) the geometric centroid may sit far from where most
    people actually live, which could bias the distance estimate in
    either direction. This is a real, acknowledged limitation of this
    specific implementation, not a claim of precision the data doesn't
    support -- flagged here and carried into docs/LIMITATIONS.md.
    """
    # Project to equal-area CRS for valid planar distance in meters
    districts_proj = districts.to_crs(CRS_PAKISTAN_EQUAL_AREA)
    facilities_proj = facilities.to_crs(CRS_PAKISTAN_EQUAL_AREA)

    # Count facilities within each district polygon
    joined = gpd.sjoin(facilities_proj, districts_proj, how="left", predicate="within")
    counts = joined.groupby("district_key").size()

    centroids = districts_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid

    facility_union_points = facilities_proj.geometry.values

    records = []
    for _, row in centroids.iterrows():
        dk = row["district_key"]
        centroid_pt = row["geometry"]
        # Distance to every facility point nationally; take the minimum.
        dists_m = facilities_proj.geometry.distance(centroid_pt)
        min_dist_km = float(dists_m.min()) / 1000.0
        n_in_district = int(counts.get(dk, 0))
        records.append(
            {
                "district_key": dk,
                "facility_count_in_district": n_in_district,
                "facility_distance_km": round(min_dist_km, 2),
                "low_osm_facility_coverage": n_in_district == 0,
            }
        )

    return pd.DataFrame(records)


def main():
    districts = gpd.read_file(DISTRICTS_GEOJSON)
    facilities = load_facilities()

    result = compute_facility_distance(districts, facilities)

    n_low_coverage = result["low_osm_facility_coverage"].sum()
    print(f"\n{n_low_coverage} of {len(result)} districts flagged "
          f"low_osm_facility_coverage (zero retained facilities mapped).")
    print("\nfacility_distance_km summary:")
    print(result["facility_distance_km"].describe())
    print("\nfacility_distance_km summary, low-coverage districts only "
          "(interpret with caution -- see module docstring):")
    print(result.loc[result["low_osm_facility_coverage"], "facility_distance_km"].describe())
    print("\nfacility_distance_km summary, adequately-covered districts:")
    print(result.loc[~result["low_osm_facility_coverage"], "facility_distance_km"].describe())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
