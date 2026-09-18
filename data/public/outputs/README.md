# data/public/outputs/ — pointer, not a duplicate copy

This project's public, redistributable, district-level aggregate
outputs already live in a documented location and are **not
duplicated here**, to avoid two copies of the same data drifting out
of sync:

- `data/processed/geography/`, `data/processed/demographics/`,
  `data/processed/features/`, `data/processed/models/`,
  `data/processed/decision/`, and `data/processed/mortality/` — all
  final, district-level, non-identifying model/decision outputs.
  Committed to the repository.
- `data/external/gbd/` — third-party IHME GBD comparison data (with
  its own citation files).
- `dashboard/data/` — the aggregate data actually embedded in and
  served by the public dashboard.

Each of these is covered in `docs/DATA_SOURCES.md` (what it is and
where it came from) and `THIRD_PARTY_DATA_LICENSES.md` (what license
or terms apply to redistributing it). `COMPLIANCE.md` explains
the project's small-cell suppression policy for the DHS-derived files
specifically.

This `data/public/` directory exists so the repository's structure
matches the conceptual raw → restricted → processed → public pipeline
described in `REPRODUCIBILITY.md`; see `data/public/demo/` for the
dashboard's demonstration-mode data.
