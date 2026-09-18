# Compliance Summary

This document summarizes how this project handles restricted and
third-party data. Throughout, it distinguishes:

- **REQUIREMENT FROM SOURCE TERMS** — something the data provider's own
  terms of use actually state.
- **CONSERVATIVE PROJECT POLICY** — a stricter rule this project
  chose to follow, which the source terms do not explicitly mandate.

Conflating these two would misrepresent what DHS (or any other source)
actually requires, so every policy below is labeled.

## DHS handling policy

| Rule | Type |
|---|---|
| Raw DHS microdata is never committed to git or redistributed | REQUIREMENT FROM SOURCE TERMS (https://dhsprogram.com/Data/terms-of-use.cfm) |
| Only district-level, non-identifying aggregates leave scripts that touch raw DHS data | REQUIREMENT FROM SOURCE TERMS (no re-identification / no microdata redistribution) |
| Raw small-cell counts (`n_births_5yr`, `n_deaths_u5_5yr`, `n_clusters`) are additionally suppressed even in the committed district-level file | CONSERVATIVE PROJECT POLICY — DHS's terms do not specify a numeric small-cell threshold for aggregate publication; this project chose to suppress exact counts below which a district's data could be traced to a single or very few sampled clusters |
| Districts with thin coverage are flagged (`low_direct_coverage`) rather than the estimate being withheld entirely | CONSERVATIVE PROJECT POLICY, informed by (not dictated by) DHS's own general small-area publication norms |
| Anyone reproducing this project needs their own DHS authorization covering this research purpose | REQUIREMENT FROM SOURCE TERMS |
| A copy of any resulting publication should be sent to references@dhsprogram.com | REQUIREMENT FROM SOURCE TERMS (per DHS's stated request) |

## Third-party licensing policy

See `THIRD_PARTY_DATA_LICENSES.md` for the full per-source breakdown.
Summary: OSM/HOTOSM data is redistributed only in aggregated form with
attribution (ODbL requirement); OCHA boundary and PBS census licensing
were **not** independently re-verified beyond the license of the code
repository that bundled them, and are flagged YELLOW rather than
claimed as MIT; IHME GBD data redistribution is assessed low-risk but
not independently confirmed permitted beyond citation.

## No-raw-data policy

**REQUIREMENT FROM SOURCE TERMS (DHS) + CONSERVATIVE PROJECT POLICY
(extended to other sources on principle):** no raw individual-level or
household-level survey data of any kind is committed to this
repository, regardless of source.

## Small-cell policy

**CONSERVATIVE PROJECT POLICY.** Applied specifically to
`data/processed/mortality/district_u5mr_direct_dhs.csv`: the committed
file contains only `u5mr_direct`, its CI, and the `low_direct_coverage`
flag — not the underlying `n_births_5yr`/`n_deaths_u5_5yr`/`n_clusters`
counts, which are kept in the gitignored
`data/processed/dhs_derived/district_u5mr_direct_dhs_full.csv` for
internal pipeline use only. Rationale: some districts have as few as 1
sampled DHS cluster or 0 recorded deaths in the reference window;
publishing those exact counts next to a named district creates a
disclosure risk (a reader could infer that a district's entire
estimate rests on a single small sample) that a suppressed-but-labeled
`low_direct_coverage` flag avoids while still being useful. **This is
not a DHS-mandated threshold** — DHS does not publish a specific
numeric small-cell suppression rule for this kind of derived aggregate,
and other reasonable choices (e.g. actually withholding low-coverage
districts entirely, or using a different count threshold) exist.

## GPS/geospatial policy

**REQUIREMENT FROM SOURCE TERMS + CONSERVATIVE PROJECT POLICY:** DHS
GPS cluster coordinates are used only for a one-time cluster→district
spatial join (`scripts/cleaning/03_clean_dhs_cluster_geography.py`);
no coordinate, displaced or otherwise, is ever written to a public
output. The resulting `cluster_district_lookup.csv` (cluster ID →
district only, no coordinates) is kept local
(`data/processed/dhs_derived/`, gitignored) rather than published,
even though cluster IDs alone are not individually identifying — this
extra caution is project policy, not a DHS requirement.

## Attribution policy

OSM/HOTOSM (ODbL — attribution required), OCHA boundaries (terms not
independently re-verified — attributed out of caution), IHME GBD
(citation required by its own terms), and PBS census are all credited
in the dashboard footer (`dashboard/index.html`, `dashboard/dashboard.jsx`)
and in `docs/DATA_SOURCES.md` / `THIRD_PARTY_DATA_LICENSES.md`.

## Publication/citation policy

Per DHS's own request, any resulting report or publication using DHS
data should be sent to references@dhsprogram.com. Per IHME/GBD's
terms, the exact citation text in `data/external/gbd/citation*.txt`
should accompany any use of that data. This project's own citation
format is left to the person publishing derived work from it.

## Historical Git scan result

A full scan of every file ever added across the entire git history
(`git log --all --diff-filter=A --name-only`) plus a content-level
search across all history diffs for credential-like strings (API
keys, tokens, passwords, private key headers) found:

- **No DHS microdata file extensions (`.dta`, `.sav`) were ever
  committed**, at any point in history.
- **No credentials, API keys, or private keys were found** in any
  historical commit.
- The only match for the search term "secret" was a business name in
  an OpenStreetMap health-facility record ("HEALTH SECRETS" clinic
  name) — not a credential.

No history rewrite was necessary for credential or raw-microdata
removal, because none was ever committed. The one substantive
compliance gap found — small-cell DHS-derived counts in
`data/processed/mortality/district_u5mr_direct_dhs.csv` — was present
in the current file content and has been fixed going forward (see
"Small-cell policy" above and `KNOWN_ISSUES` below for the historical
disclosure this leaves in older commits).

## Known uncertainties / requiring confirmation from a data owner

1. **OCHA boundary shapefile license** — bundled via an MIT-licensed
   code repo, but the boundary data's own license was not
   independently checked against the original HDX dataset page. See
   `THIRD_PARTY_DATA_LICENSES.md` §5 for how to resolve this.
2. **PBS census table redistribution terms** — no explicit PBS open-data
   license statement was located; treated as low-risk aggregate public
   statistics but not confirmed via an explicit license grant.
3. **IHME GBD redistribution of downloaded rows** — assessed low-risk
   (aggregate, non-identifying, citation followed) but not confirmed
   via a separate legal reading of the free-of-charge agreement beyond
   its citation requirement.
4. **Historical git commits still contain the un-suppressed small-cell
   counts** for `district_u5mr_direct_dhs.csv` (every commit from the
   initial commit onward, since this file existed from the start of
   the repository). Rewriting history to purge this is possible (as
   demonstrated earlier in this repository's history for commit
   messages) but was not performed as part of this pass, since it:
   (a) requires a force-push that invalidates any existing clones/forks,
   (b) is a bigger, higher-blast-radius operation than editing the
   current file content, and (c) the disclosure risk of small DHS
   sample-size counts is real but categorically less severe than, say,
   leaked credentials. **Recommendation:** if this repository has any
   forks, stars, or has been cloned by others, treat this as an
   open item and decide explicitly whether to rewrite history (see
   `docs/DATA_SOURCES.md` and `THIRD_PARTY_DATA_LICENSES.md` for
   context) — this document deliberately does not perform that rewrite
   silently.

## Status legend used in the final audit report

🟢 GREEN = verified/low concern · 🟡 YELLOW = conservative handling
recommended or terms need confirmation · 🔴 RED = remove/fix before
public release. This repository currently has no 🔴 RED items.
