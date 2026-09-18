# data/external/gbd/ — raw IHME files are local-only

**`IHME-GBD_2023_DATA-*.csv` are `.gitignore`d and not committed.**
`citation.txt` and `citation_province_2017_2018.txt` (citation text
only, no data values) remain committed.

## Why

The IHME Free-of-Charge Non-Commercial User Agreement states:

> "User may not without written permission from UW provide to third
> parties the ability to download IHME Data Sets from User-provided
> hosting facilities; User may publish links to IHME's hosting and
> downloading facilities."

Committing the raw downloaded CSVs to a public GitHub repository is
exactly "provid[ing] to third parties the ability to download IHME
Data Sets from User-provided hosting facilities" — so, on a plain
reading of that clause, this project should not (and now does not) do
that. See `THIRD_PARTY_DATA_LICENSES.md` §3 and `COMPLIANCE.md` for
the full record of this finding, including that this specific
restriction was not identified until after the files had already been
committed (see the historical Git scan note in `COMPLIANCE.md`).

## What's still committed and why that's fine

`data/processed/models/gbd_validation_comparison.csv` — this project's
own comparison table (this project's model estimates vs. GBD's,
Spearman rank correlations, etc.) — is unaffected. The same agreement
explicitly permits creating and publishing "Results" (analyses using
IHME data, for Publication) containing "only such portions of the IHME
Data and Data Sets as are necessary" for that purpose; a small derived
comparison table is squarely the kind of thing that clause is meant to
allow, unlike re-hosting the full raw download for others to fetch.

## Getting the raw files yourself

1. Create a free IHME/GHDx account.
2. Use the GBD Results Tool (https://vizhub.healthdata.org/gbd-results/)
   to download province-level 5q0 estimates for Pakistan, 2017-2019.
3. Place the downloaded file(s) in this directory to re-run
   `scripts/models/06_validate_against_gbd.py` locally.

See `DATA_ACCESS.md` for the full manifest entry.
