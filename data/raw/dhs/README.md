# data/raw/dhs/ — restricted, local-only

**This directory is empty in the public repository and is `.gitignore`d.
Nothing here is ever committed or redistributed.**

This is where you place your own authorized PDHS 2017-18 microdata after
obtaining it directly from The DHS Program. This repository does not, and
cannot, provide these files for you.

## What goes here

| File | DHS name | Expected local path |
|---|---|---|
| Births Recode | PKBR71DT / PKBR71FL.DTA | `data/raw/dhs/2017-18_DHS_GPS/PKBR71DT/PKBR71FL.DTA` |
| Household Recode | PKHR71DT | `data/raw/dhs/2017-18_DHS_GPS/PKHR71DT/PKHR71FL.DTA` |
| Individual/Women's Recode | PKIR71DT | `data/raw/dhs/2017-18_DHS_GPS/PKIR71DT/PKIR71FL.DTA` |
| Children's Recode | PKKR71FL | `data/raw/dhs/2017-18_DHS_GPS/PKKR71FL/PKKR71FL.DTA` |
| GPS/Geographic Data | PKGE71FL | `data/raw/dhs/2017-18_DHS_GPS/PKGE71FL/PKGE71FL.shp` (+ associated .shx/.dbf/.prj) |

See `../../../DATA_ACCESS.md` for how to request these from DHS, and
`../../../docs/DATA_SOURCES.md` for what each file is used for in this
pipeline.

## Why this boundary exists

Every script that reads from this directory is annotated with a
`*** DHS COMPLIANCE BOUNDARY ***` docstring explaining exactly what
leaves the script (always: district-aggregated, non-identifying
statistics only) and what never does (individual/household/cluster-level
records, exact GPS coordinates). See `COMPLIANCE.md` for the
project's overall data-handling policy, and
https://dhsprogram.com/Data/terms-of-use.cfm for DHS's own terms, which
govern your use of anything you place here.
