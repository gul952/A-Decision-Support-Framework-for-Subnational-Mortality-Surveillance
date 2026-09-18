#!/usr/bin/env python3
"""
scripts/audit_public_release.py

Automated compliance/safety scanner. Run before publishing any change,
or as a GitHub Actions check on every push/PR (see
.github/workflows/audit_public_release.yml).

Checks the repository's TRACKED files (i.e. what git would actually
publish) for:
  - DHS microdata file extensions (.dta, .sav) and GPS/shapefile
    sidecars (.shp/.shx/.dbf/.prj)
  - likely DHS raw filenames (PKBR71, PKHR71, PKIR71, PKKR71, PKGE71
    and similar DHS recode-file naming patterns)
  - raw IHME GBD download files (IHME's user agreement prohibits
    third-party redistribution via a user-hosted download; this
    project's own small derived comparison table is unaffected)
  - credential-like filenames (.env, credentials.json, *.pem, *.key,
    etc.)
  - suspiciously large binary files (over a size threshold) that
    likely shouldn't be in git
  - the specific small-cell DHS columns this project has decided not
    to publish (n_births_5yr, n_deaths_u5_5yr, n_clusters) appearing in
    any file OUTSIDE the known local-only dhs_derived/ directory

This script deliberately does NOT flag ordinary prose references to
"DHS" in documentation/comments -- only filename patterns and, for the
small-cell check, actual CSV column headers. A false positive here
(blocking a release over a documentation sentence) is exactly the
failure mode Part 19 of the compliance brief warns against.

Exit code: 0 if clean, 1 if any RED-level issue found.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# File extensions that should never be tracked by git.
FORBIDDEN_EXTENSIONS = {
    ".dta", ".sav", ".DTA", ".SAV",
    ".shp", ".shx", ".dbf", ".prj", ".cpg",
    ".pem", ".key", ".p12", ".pfx",
}

# Filenames (exact or glob-ish substring match) that suggest credentials.
FORBIDDEN_FILENAME_SUBSTRINGS = [
    ".env", "credentials.json", "secrets.json", "secrets.yml",
    "secrets.yaml", ".netrc", "id_rsa", "id_ed25519",
]

# DHS raw recode-file naming patterns (case-insensitive substring match).
# These are DHS's own file-naming convention (country+recode+phase),
# not generic English words, so this should not produce false positives
# on ordinary prose mentioning "DHS".
DHS_FILENAME_PATTERNS = [
    "pkbr71", "pkhr71", "pkir71", "pkkr71", "pkge71", "pkgc72",
]

# Raw IHME GBD downloaded data files -- the IHME Free-of-Charge
# Non-Commercial User Agreement prohibits providing third parties the
# ability to download IHME Data Sets from user-hosted facilities. This
# project's own small derived comparison table
# (gbd_validation_comparison.csv) is fine and does not match this
# pattern; only IHME's own raw export filenames do.
GBD_RAW_FILENAME_PREFIX = "ihme-gbd_"

# Columns that reveal exact DHS small-cell counts; only permitted inside
# the designated local-only directory.
SMALL_CELL_COLUMNS = {"n_births_5yr", "n_deaths_u5_5yr", "n_clusters"}
SMALL_CELL_ALLOWED_DIR = "data/processed/dhs_derived/"

# Large-file threshold (bytes) -- flagged as a warning, not a hard failure,
# since a large committed model file (e.g. models/*.pkl) may be intentional.
LARGE_FILE_WARN_BYTES = 20 * 1024 * 1024


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / p for p in out.stdout.splitlines() if p.strip()]


def check_forbidden_extensions(files):
    problems = []
    for f in files:
        if f.suffix in FORBIDDEN_EXTENSIONS:
            problems.append(f"Forbidden file extension tracked: {f.relative_to(REPO_ROOT)}")
    return problems


def check_forbidden_filenames(files):
    problems = []
    for f in files:
        name_lower = f.name.lower()
        for pattern in FORBIDDEN_FILENAME_SUBSTRINGS:
            if pattern in name_lower:
                problems.append(f"Likely credential file tracked: {f.relative_to(REPO_ROOT)}")
                break
    return problems


def check_dhs_filenames(files):
    problems = []
    for f in files:
        name_lower = f.name.lower()
        for pattern in DHS_FILENAME_PATTERNS:
            if pattern in name_lower:
                problems.append(
                    f"Filename matches DHS raw recode-file pattern '{pattern}': "
                    f"{f.relative_to(REPO_ROOT)}"
                )
                break
    return problems


def check_gbd_raw_files(files):
    problems = []
    for f in files:
        if f.name.lower().startswith(GBD_RAW_FILENAME_PREFIX):
            problems.append(
                f"Raw IHME GBD download tracked (redistribution not permitted "
                f"without written permission -- see data/external/gbd/README.md): "
                f"{f.relative_to(REPO_ROOT)}"
            )
    return problems


def check_small_cell_columns(files):
    problems = []
    for f in files:
        if f.suffix.lower() != ".csv":
            continue
        rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel.startswith(SMALL_CELL_ALLOWED_DIR):
            continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                header = fh.readline().strip()
        except OSError:
            continue
        header_cols = {c.strip() for c in header.split(",")}
        hit = header_cols & SMALL_CELL_COLUMNS
        if hit:
            problems.append(
                f"Small-cell DHS column(s) {sorted(hit)} found outside "
                f"{SMALL_CELL_ALLOWED_DIR}: {rel}"
            )
    return problems


def check_large_files(files):
    warnings = []
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size > LARGE_FILE_WARN_BYTES:
            warnings.append(
                f"Large tracked file ({size / (1024*1024):.1f} MB): "
                f"{f.relative_to(REPO_ROOT)}"
            )
    return warnings


def main():
    files = tracked_files()

    red_problems = []
    red_problems += check_forbidden_extensions(files)
    red_problems += check_forbidden_filenames(files)
    red_problems += check_dhs_filenames(files)
    red_problems += check_gbd_raw_files(files)
    red_problems += check_small_cell_columns(files)

    warnings = check_large_files(files)

    print(f"Scanned {len(files)} tracked files.\n")

    if warnings:
        print("WARNINGS (not blocking):")
        for w in warnings:
            print(f"  - {w}")
        print()

    if red_problems:
        print("BLOCKING ISSUES FOUND:")
        for p in red_problems:
            print(f"  - {p}")
        print(f"\n{len(red_problems)} blocking issue(s). Exiting with status 1.")
        return 1

    print("No blocking issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
