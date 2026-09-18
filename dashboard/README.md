# Dashboard

## Just want to see it? Open `index.html`.

Double-click `dashboard/index.html`, or drag it into a browser tab. That's it --
no install, no build step, no terminal. It's a single self-contained file
(React loaded from a CDN, all data included) implementing Layer 5
(Interactive Platform) of the project: a choropleth map of Pakistan's 135
districts, adjustable priority-score weight sliders, a top-N surveillance
budget selector, and a per-district "why this rank" explainability panel.

Requires an internet connection on first load (to fetch React/Babel from
a CDN) but no other setup.

## For developers integrating this into a larger app

`dashboard.jsx` + `districtsData.js` are the same component split into a
normal importable React module + data file, for anyone building this
into an existing React project (Vite, Next.js, etc.) rather than viewing
it standalone.

```bash
# from a fresh Vite React app:
npm create vite@latest my-dashboard -- --template react
cd my-dashboard
cp path/to/dashboard.jsx path/to/districtsData.js src/
# then import and render <MortalitySurveillanceDashboard /> from src/dashboard.jsx
npm install
npm run dev
```

## Updating the dashboard's data

The dashboard's data is a **snapshot** of the pipeline's outputs at the
time it was built. To refresh it after re-running the pipeline (e.g.
after uploading full DHS HR/IR data, adding WHO/IHME layers, or
adjusting the SAE model):

```bash
python3 scripts/build_dashboard_data.py
```

This regenerates:
- `dashboard/data/districts_full.geojson` -- full GeoJSON (135 features),
  useful for GIS tools (QGIS, geopandas, etc.)
- `dashboard/data/districts_compact.json` -- compact flat JSON structure
  (kept for reference/debugging)
- `dashboard/districtsData.js` -- the file `dashboard.jsx` actually
  imports (`import { DISTRICTS_DATA } from './districtsData'`)
- `dashboard/index.html` -- the standalone file, rebuilt fresh each time
  from the current `dashboard.jsx` + `districtsData.js`

That's it -- **no manual copy-paste step**. Both `dashboard.jsx` and
`index.html` pick up the new data automatically. Splitting the data out
of `dashboard.jsx` also keeps that file small (~21KB instead of the
~220KB it would be with data embedded), so it opens and edits quickly;
`index.html` is the one file that's meant to be opened directly and
does embed everything, by design, so it works standalone.

`districtsData.js` and `index.html` are both auto-generated -- don't hand-edit them. If you're
publishing an updated public-facing version, it's still good practice
to review the data diff (`git diff dashboard/districtsData.js`) before
committing, the same as you would for any generated file.

## Data provenance and compliance note

All data embedded in this dashboard is **district-level aggregated
statistics only** -- no individual, household, or DHS-cluster-level
records. This is a hard requirement (see `docs/DATA_SOURCES.md`,
DHS terms of use) enforced at the `build_dashboard_data.py` step, which
only reads from `data/processed/` (never `data/raw/dhs/`).

The dashboard footer also carries third-party attribution (ALHASAN
Systems district boundaries, OpenStreetMap/HOTOSM facility data, IHME
GBD, PBS census) — see `THIRD_PARTY_DATA_LICENSES.md` for what each of
those terms actually requires. If you edit the footer text, edit it in
`dashboard.jsx` (the attribution paragraph right after "Footer
disclaimer") — `build_dashboard_data.py` re-embeds that file's content
into `index.html` on every run, so editing `index.html` directly will
be overwritten the next time the dashboard data is regenerated.
