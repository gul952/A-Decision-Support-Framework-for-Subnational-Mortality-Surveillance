"""
build_dashboard_data.py

Layer 5 (Interactive Platform) -- regenerates the district data bundle
that the dashboard consumes, in three forms:
    - dashboard/districtsData.js  (importable JS module, for dashboard.jsx
      / integration into a larger React app)
    - dashboard/index.html         (standalone, double-click-to-open file
      with data + component + React/Babel-from-CDN all in one place --
      this is the file most people should actually open)
    - dashboard/data/*.json, *.geojson  (raw exports, for reference / GIS
      tools)

Run this AFTER the main pipeline (scripts/run_pipeline.sh) to refresh the
dashboard's data whenever upstream layers change (new DHS data, adjusted
weights, re-fit SAE model, etc). Running this script is the ONLY step
needed -- no manual copy-paste into any file.

This script only merges and formats already-processed, non-identifying
district-aggregated data (geography + priority scores + demographic
indicators) -- no raw DHS microdata is touched here, consistent with the
DHS compliance boundary maintained throughout data/raw/dhs/.

Input:
    data/processed/geography/districts.geojson
    data/processed/decision/district_priority_scores.csv
    data/processed/demographics/district_demographics_socioeconomic.csv
    data/processed/features/district_features.csv

Output:
    dashboard/data/districts_compact.json   (compact JS-embeddable data)
    dashboard/data/districts_full.geojson   (full GeoJSON, for GIS tools)
    dashboard/districtsData.js              (importable JS module)
    dashboard/index.html                    (standalone, open-directly file)
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pkmortality.config import DATA_PROCESSED, ROOT

DASHBOARD_DATA_DIR = ROOT / "dashboard" / "data"
DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)

SIMPLIFY_TOLERANCE = 0.015  # degrees; keeps the embedded payload small
                              # while preserving recognizable district
                              # shapes at dashboard map scale


def main():
    print("Loading processed layers...")
    geo = gpd.read_file(DATA_PROCESSED / "geography" / "districts.geojson")
    priority = pd.read_csv(DATA_PROCESSED / "decision" / "district_priority_scores.csv")
    demo = pd.read_csv(
        DATA_PROCESSED / "demographics" / "district_demographics_socioeconomic.csv"
    )
    feat = pd.read_csv(DATA_PROCESSED / "features" / "district_features.csv")

    geo = geo.drop(columns=["province"], errors="ignore")
    merged = geo.merge(priority, on="district_key", how="left")
    merged = merged.merge(
        demo[
            [
                "district_key",
                "literacy_rate_pct",
                "improved_water_pct",
                "improved_sanitation_pct",
            ]
        ],
        on="district_key",
        how="left",
    )
    merged = merged.merge(
        feat[["district_key", "deprivation_index", "under5_share_pct"]],
        on="district_key",
        how="left",
    )

    n_missing_priority = merged["priority_score"].isna().sum()
    if n_missing_priority:
        print(
            f"WARNING: {n_missing_priority} districts missing priority score "
            "-- check that scripts/decision/01_prioritization_engine.py ran "
            "successfully before this script."
        )

    merged["geometry"] = merged["geometry"].simplify(
        SIMPLIFY_TOLERANCE, preserve_topology=True
    )
    numeric_cols = merged.select_dtypes(include="number").columns
    for c in numeric_cols:
        merged[c] = merged[c].round(3)
    merged["display_name"] = merged["district_key"].str.replace(" DISTRICT", "").str.title()

    full_geojson_path = DASHBOARD_DATA_DIR / "districts_full.geojson"
    merged.to_file(full_geojson_path, driver="GeoJSON")
    print(f"Wrote: {full_geojson_path}")

    compact_features = []
    for _, p in merged.iterrows():
        geom = json.loads(gpd.GeoSeries([p["geometry"]]).to_json())["features"][0]["geometry"]
        compact_features.append(
            {
                "k": p["district_key"],
                "n": p["display_name"],
                "prov": p["province"],
                "pop": int(p["population_2017"]) if pd.notna(p["population_2017"]) else None,
                "u5mr": p["u5mr_posterior_mean"],
                "u5mr_lo": p["u5mr_ci_lower95"],
                "u5mr_hi": p["u5mr_ci_upper95"],
                "ci_w": p["ci_width"],
                "access": p["remoteness_proxy"],
                "lit": p["literacy_rate_pct"],
                "water": p["improved_water_pct"],
                "sani": p["improved_sanitation_pct"],
                "dep": p["deprivation_index"],
                "u5share": p["under5_share_pct"],
                "had_data": bool(p["had_direct_data"]) if pd.notna(p["had_direct_data"]) else False,
                "n_births": int(p["n_births_direct"]) if pd.notna(p["n_births_direct"]) else 0,
                "geom": geom,
            }
        )

    compact_path = DASHBOARD_DATA_DIR / "districts_compact.json"
    with open(compact_path, "w") as f:
        json.dump({"features": compact_features}, f, separators=(",", ":"))
    print(f"Wrote: {compact_path}")

    # Write directly as the dashboard's importable JS data module -- no
    # manual copy-paste step required. dashboard/dashboard.jsx imports
    # this file with a normal `import { DISTRICTS_DATA } from
    # './districtsData'` statement, so re-running this script is the
    # ONLY step needed to refresh the dashboard after a pipeline update.
    js_data_path = ROOT / "dashboard" / "districtsData.js"
    with open(js_data_path, "w") as f:
        f.write("// Auto-generated by scripts/build_dashboard_data.py -- do not hand-edit.\n")
        f.write("export const DISTRICTS_DATA = ")
        json.dump({"features": compact_features}, f, separators=(",", ":"))
        f.write(";\n")
    print(f"Wrote: {js_data_path}")

    rebuild_standalone_html()
    print(f"Wrote: {ROOT / 'dashboard' / 'index.html'} (standalone, double-click to open)")

    size_kb = compact_path.stat().st_size / 1024
    print(f"\nCompact payload size: {size_kb:.1f} KB")
    print(
        "\nDashboard data refreshed -- dashboard/index.html is the file to "
        "open (double-click or drag into a browser tab). dashboard.jsx + "
        "districtsData.js are also refreshed for anyone integrating this "
        "into a larger React app instead."
    )


def rebuild_standalone_html():
    """
    Rebuilds dashboard/index.html -- a single self-contained file (React
    + Babel loaded from CDN, component code and data inlined) that opens
    directly in any browser with no build step, no npm install, and no
    manual copy-paste. This is regenerated automatically every time this
    script runs, from the current dashboard.jsx + districtsData.js, so
    it never goes stale relative to the two source files.
    """
    dashboard_dir = ROOT / "dashboard"
    component_code = (dashboard_dir / "dashboard.jsx").read_text()
    data_code = (dashboard_dir / "districtsData.js").read_text()

    component_code = component_code.replace(
        "import React, { useState, useMemo, useCallback } from 'react';\n", ""
    )
    component_code = component_code.replace(
        "import { DISTRICTS_DATA } from './districtsData';\n", ""
    )
    component_code = component_code.replace(
        "export default function MortalitySurveillanceDashboard()",
        "function MortalitySurveillanceDashboard()",
    )
    data_code = data_code.replace(
        "export const DISTRICTS_DATA = ", "const DISTRICTS_DATA = "
    )
    hooks_shim = "const { useState, useMemo, useCallback } = React;\n\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Pakistan Subnational Mortality Surveillance — Decision Support Dashboard</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #12181f; }}
  * {{ box-sizing: border-box; }}
</style>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body>
<div id="root"></div>

<script type="text/babel" data-presets="react">
{hooks_shim}
// ---------------------------------------------------------------------
// District data (auto-generated by scripts/build_dashboard_data.py)
// ---------------------------------------------------------------------
{data_code}

// ---------------------------------------------------------------------
// Dashboard component
// ---------------------------------------------------------------------
{component_code}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<MortalitySurveillanceDashboard />);
</script>
</body>
</html>
"""
    (dashboard_dir / "index.html").write_text(html)


if __name__ == "__main__":
    main()
