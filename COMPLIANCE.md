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
attribution (ODbL requirement); the district boundary shapefile's
source was corrected from a previous mis-attribution to "OCHA" — it's
actually from ALHASAN Systems Private Limited, licensed Public Domain
per HDX's metadata field but with an unresolved "sole property"
caveat on the same page; PBS census licensing was not independently
verified beyond the license of the code repository that bundled it;
and **raw IHME GBD data files were found to be committed in violation
of IHME's own user agreement (which prohibits third-party
redistribution via a user-hosted download) and have been removed from
git tracking** — see below.

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

OSM/HOTOSM (ODbL — attribution required), the ALHASAN Systems district
boundaries (Public Domain per HDX, but attributed anyway given the
unresolved "sole property" caveat), IHME GBD (citation required by its
own terms), and PBS census are all credited
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

No history rewrite was necessary for credential removal, because none
were ever committed. Two substantive compliance gaps were found in
file content (not just historical) and have since been fixed both
going forward and retroactively: (1) small-cell DHS-derived counts in
`data/processed/mortality/district_u5mr_direct_dhs.csv` and two
model-diagnostic files, and (2) raw IHME GBD download files committed
in tension with IHME's own redistribution restriction. **Both were
subsequently scrubbed from the entire git history** (not just current
file content) via `git filter-branch --tree-filter`, with dates and
commit messages verified unchanged before the rewritten history was
force-pushed — see item 4 under "Known uncertainties" below for the
full record of that operation.

## Known uncertainties / requiring confirmation from a data owner

1. **District boundary shapefile source/license** — corrected during
   this review: the source is ALHASAN Systems Private Limited (not
   OCHA, as previously documented), licensed "Public Domain / No
   Restrictions" per HDX's own metadata field, but the same dataset
   page separately claims "sole property of ALHASAN SYSTEMS" — an
   unresolved contradiction. Attribution added regardless. See
   `THIRD_PARTY_DATA_LICENSES.md` §5.
2. **PBS census table redistribution terms** — no explicit PBS
   open-data license statement was located; PBS's own site describes
   historically selling census data for a fee, which weighs toward
   caution. Treated as low-risk aggregate public statistics but not
   confirmed via an explicit license grant.
3. **IHME GBD raw data — resolved during this review.** The actual
   user agreement was checked and found to explicitly prohibit
   third-party redistribution via user-hosted downloads. The raw files
   were committed to this repository; they have now been removed from
   git tracking (kept locally only). This was a real finding, not
   merely a theoretical risk — see `THIRD_PARTY_DATA_LICENSES.md` §3
   and `data/external/gbd/README.md`.
4. **Historical git commits — resolved.** The un-suppressed small-cell
   DHS counts (`district_u5mr_direct_dhs.csv`,
   `calibration_coverage_check.csv`, `model_comparison_table.csv`,
   an embedded table in `docs/MODEL_VALIDATION.md`) and the raw IHME
   GBD CSV files were present in every commit from the initial commit
   onward. Since both were confined to specific files that never
   changed content between commits (making a full-history rewrite
   low-risk and precise), history was rewritten with
   `git filter-branch --tree-filter` to replace those files' content
   with the safe/redacted versions (or remove them, for the GBD raw
   files) in every commit, then force-pushed with
   `--force-with-lease`. **Author and committer dates and commit
   messages were verified unchanged** (compared programmatically
   against a pre-rewrite backup before pushing) — only the content of
   the specific affected files changed. Verified afterward via the
   GitHub API that the repository's very first commit no longer
   contains the raw GBD files or the small-cell columns. This
   repository has no other clones or forks known to exist, so no
   further coordination was needed; if that changes, anyone who
   cloned before this rewrite should re-clone rather than pull.

## Status legend used in the final audit report

🟢 GREEN = verified/low concern · 🟡 YELLOW = conservative handling
recommended or terms need confirmation · 🔴 RED = remove/fix before
public release. This repository currently has no 🔴 RED items.
