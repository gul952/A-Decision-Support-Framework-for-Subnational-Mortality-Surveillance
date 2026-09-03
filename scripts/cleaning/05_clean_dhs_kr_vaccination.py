"""
05_clean_dhs_kr_vaccination.py

Layer 1 (Data Engineering) -- district-aggregated DHS Children's Recode
(KR) vaccination coverage, added as a SECOND, INDEPENDENT external
validation axis for this project's mortality small-area estimates,
distinct from the existing IHME GBD comparison
(scripts/models/06_validate_against_gbd.py).

*** WHY THIS MATTERS ***
The project's only external validation so far compares this project's
own mortality ESTIMATES against another mortality estimate (GBD) --
useful, but both are estimates of the same underlying quantity via
related demographic methods. Vaccination coverage is a genuinely
different kind of evidence: a directly-measured health-system output
(reported by mothers / vaccination cards), causally upstream of child
mortality, collected in the same PDHS 2017-18 survey round (so no new
compliance registration or cluster-geography mismatch). If districts
this project's model flags as high-priority also show low vaccination
coverage, that is a genuinely independent corroboration -- a different
mechanism, a different respondent-reported measure, not just another
statistical estimate of the same target quantity.

*** DHS COMPLIANCE BOUNDARY ***
Reads raw KR microdata from data/raw/dhs/2017-18_DHS_KR/ (gitignored,
never committed/redistributed). Writes ONLY district-aggregated,
sample-weighted summary statistics to data/processed/ -- no
individual child records leave this script. Same boundary pattern as
scripts/cleaning/04_clean_dhs_hr_ir.py.

*** VACCINE SCHEDULE NOTE (survey-round specific) ***
Pakistan's 2017-18 PDHS uses PENTAVALENT (h51/h52/h53), not standalone
DPT, as its 3-dose combination vaccine -- DPT variables (h3/h5/h7) exist
in the file but are "na" for this round (later schedule change, not a
data-quality gap). "Fully vaccinated" here therefore follows the DHS
Program's own standard 2017-18-round definition:
    BCG + Pentavalent(1,2,3) + Polio(1,2,3) + Measles(1)
This mirrors the DHS Program's own published methodology for this
survey round exactly, not an ad-hoc redefinition. Valid "received"
codes per DHS standard coding are {1, 2, 3} (vaccination date on card;
reported by mother; marked on card without date); {0, 8} (no;
don't know) do not count as received.

*** COHORT DEFINITION ***
Following standard international reporting convention (and the DHS
Program's own final reports), vaccination coverage is computed among
children currently aged 12-23 months (b19) who are alive (b5==1) at
time of interview -- the standard reference cohort, since this is the
first age by which a child should have completed the full schedule
under Pakistan's EPI timeline, while recall/card availability is still
reasonably fresh. This means the vaccination-coverage sample is a
DIFFERENT (smaller, age-restricted) subset of KR records than the
full birth-history sample used for the direct U5MR estimate in
02b_estimate_u5mr_from_dhs.py -- both are standard, just answering
different questions (current coverage among a recent birth cohort,
vs. historical death rates over a 5-year window).

Output:
    data/processed/dhs_derived/district_vaccination_coverage.csv
        columns: district_key, n_children_12_23mo, pct_fully_vaccinated,
                 pct_bcg, pct_measles1, pct_penta3, pct_zero_dose,
                 low_vaccination_sample
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_RAW, DATA_PROCESSED

KR_PATH = DATA_RAW / "dhs" / "2017-18_DHS_KR" / "PKKR71FL.DTA"
CLUSTER_LOOKUP_PATH = DATA_PROCESSED / "dhs_derived" / "cluster_district_lookup.csv"
OUT_DIR = DATA_PROCESSED / "dhs_derived"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# DHS standard "received" codes: 1=date on card, 2=reported by mother,
# 3=marked on card without date. 0=no, 8=don't know -- NOT counted as received.
RECEIVED_CODES = {1, 2, 3}

# The 8 antigens/doses that make up "fully vaccinated" for this survey round.
VACCINE_VARS = {
    "bcg": "h2",
    "penta1": "h51",
    "penta2": "h52",
    "penta3": "h53",
    "polio1": "h4",
    "polio2": "h6",
    "polio3": "h8",
    "measles1": "h9",
}

MIN_RECORDS_FOR_DISTRICT_ESTIMATE = 25  # smaller than the HR/IR threshold (30)
                                          # because the 12-23mo cohort is
                                          # itself a small slice of the full
                                          # KR file -- flagged, not hidden,
                                          # same philosophy as elsewhere.


def received(series: pd.Series) -> pd.Series:
    """True/False for whether this vaccination was received, per DHS
    standard coding. NaN/other codes treated as not received (matches
    DHS's own published coverage-rate denominator convention: the
    denominator is all eligible children, not just those with a
    valid non-missing response)."""
    return series.isin(RECEIVED_CODES)


def weighted_pct(flags: pd.Series, weights: pd.Series) -> float:
    mask = flags.notna() & weights.notna()
    if mask.sum() == 0:
        return np.nan
    return 100.0 * np.average(flags[mask].astype(float), weights=weights[mask])


def main():
    print(f"Loading KR file from {KR_PATH}...")
    kr = pd.read_stata(
        KR_PATH,
        convert_categoricals=False,
        columns=["v001", "v005", "v024", "b5", "b19"] + list(VACCINE_VARS.values()),
    )
    print(f"  {len(kr)} birth records (all children ever born, full KR file)")

    # Restrict to the standard reference cohort: alive, aged 12-23 months
    cohort = kr[(kr["b5"] == 1) & (kr["b19"].between(12, 23))].copy()
    print(f"  {len(cohort)} children aged 12-23 months and alive "
          f"(standard vaccination-coverage reference cohort)")

    for name, var in VACCINE_VARS.items():
        cohort[f"received_{name}"] = received(cohort[var])

    cohort["fully_vaccinated"] = cohort[[f"received_{n}" for n in VACCINE_VARS]].all(axis=1)
    cohort["zero_dose"] = ~cohort[[f"received_{n}" for n in VACCINE_VARS]].any(axis=1)

    print("\nLoading cluster-district lookup...")
    lookup = pd.read_csv(CLUSTER_LOOKUP_PATH)
    lookup["DHSCLUST"] = lookup["DHSCLUST"].astype(float).astype(int)
    cohort["v001"] = cohort["v001"].astype(int)
    cohort = cohort.merge(
        lookup[["DHSCLUST", "district_key"]],
        left_on="v001", right_on="DHSCLUST", how="left",
    )
    n_unmatched = cohort["district_key"].isna().sum()
    print(f"  {len(cohort) - n_unmatched}/{len(cohort)} cohort children matched to a "
          f"135-district-scope district (unmatched = AJK/Gilgit-Baltistan "
          f"clusters, same exclusion as the rest of this pipeline)")
    cohort = cohort.dropna(subset=["district_key"])

    records = []
    for dk, grp in cohort.groupby("district_key"):
        n = len(grp)
        w = grp["v005"]
        rec = {
            "district_key": dk,
            "n_children_12_23mo": n,
            "pct_fully_vaccinated": round(weighted_pct(grp["fully_vaccinated"], w), 1),
            "pct_zero_dose": round(weighted_pct(grp["zero_dose"], w), 1),
            "pct_bcg": round(weighted_pct(grp["received_bcg"], w), 1),
            "pct_measles1": round(weighted_pct(grp["received_measles1"], w), 1),
            "pct_penta3": round(weighted_pct(grp["received_penta3"], w), 1),
            "low_vaccination_sample": n < MIN_RECORDS_FOR_DISTRICT_ESTIMATE,
        }
        records.append(rec)

    result = pd.DataFrame(records)
    print(f"\n{len(result)}/135 districts have at least 1 sampled 12-23mo child.")
    n_low = result["low_vaccination_sample"].sum()
    print(f"{int(n_low)}/{len(result)} of those are below the "
          f"{MIN_RECORDS_FOR_DISTRICT_ESTIMATE}-record stability threshold "
          f"(flagged, not excluded).")

    # National aggregate check against a known published benchmark
    national_fv = weighted_pct(cohort["fully_vaccinated"], cohort["v005"])
    print(f"\nNational aggregate (population-weighted, this reimplementation): "
          f"{national_fv:.1f}% fully vaccinated among children 12-23 months.")
    print("Compare to PDHS 2017-18 final report's own published full-"
          "immunization figure for external sanity-checking (not "
          "automatically fetched here -- see docs/DATA_SOURCES.md).")

    out_path = OUT_DIR / "district_vaccination_coverage.csv"
    result.to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
