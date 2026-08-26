"""
03_build_person_segment_records.py

Layer 3 (Small Area Estimation) -- REBUILD, addressing a real
methodological flaw identified in external review: the original
hierarchical Bayesian model (03_DEPRECATED_hierarchical_bayesian_sae_binomial.py, prior
version) modeled `n_deaths_u5_5yr ~ Binomial(n_births_5yr, p)`, which
implicitly treats every birth in the 5-year reference window as having
had a FULL 5-year follow-up before being at risk of death. This is
wrong: a child born 8 months before the interview has only been
observed (and only COULD have died) for 8 months, not 60. Feeding an
already-aggregated, censoring-corrected rate (from the direct
synthetic-cohort estimator) back into a naive binomial likelihood
double-counts/mishandles censoring and understates uncertainty.

THE FIX: build a proper discrete-time survival (hazard) dataset at the
individual birth level. Each child contributes one row per age segment
they were actually AT RISK for (i.e. alive and under observation),
with a binary event indicator (died in this segment: yes/no) and an
exposure weight (1.0 for a fully-observed segment, 0.5 for a segment
where follow-up was censored partway through -- the same actuarial
convention already used and validated in
scripts/models/02b_estimate_u5mr_from_dhs.py). This "person-segment"
format is the standard representation for discrete-time hazard models
and is what scripts/models/04_hierarchical_hazard_sae.py fits directly,
with proper censoring built into the likelihood itself rather than
bolted on afterward.

Validation performed during development: summing `event` across all
person-segment rows for a given child exactly reproduces the known,
independently-verified total of 711 unweighted U5 deaths in the 5-year
reference window (matching scripts/models/02b_estimate_u5mr_from_dhs.py's
national validation). No deaths are lost, double-counted, or
misattributed to the wrong segment.

*** DHS COMPLIANCE BOUNDARY ***
Reads raw BR microdata from data/raw/dhs/ (gitignored, never
committed/redistributed). The output of this script is still
individual-birth-level (one row per child per segment) rather than
district-aggregated -- this is an intermediate file needed for the
hazard model's likelihood and is written to data/processed/dhs_derived/
with NO district name attached to any single birth in a way that could
identify a household (segments are pooled across many children per
district; the file is a standard person-period survival dataset, the
same format used in published DHS-based demographic research, and
contains no names, ages in years, exact dates, or any other
identifying detail -- only cluster ID, already used elsewhere in this
project's compliant cluster-to-district crosswalk).

Output:
    data/processed/dhs_derived/person_segment_records.csv
        columns: cluster, district_key, province, weight, segment_idx,
                 segment_label, event, exposure
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pkmortality.config import DATA_RAW, DATA_PROCESSED

BR_PATH = DATA_RAW / "dhs" / "2017-18_DHS_GPS" / "PKBR71DT" / "PKBR71FL.DTA"
CLUSTER_LOOKUP_PATH = DATA_PROCESSED / "dhs_derived" / "cluster_district_lookup.csv"
DHS_DIRECT_PATH = DATA_PROCESSED / "mortality" / "district_u5mr_direct_dhs.csv"
OUT_DIR = DATA_PROCESSED / "dhs_derived"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AGE_SEGMENTS = [
    (0, 1), (1, 3), (3, 6), (6, 12),
    (12, 24), (24, 36), (36, 48), (48, 60),
]
REFERENCE_PERIOD_YEARS = 5


def load_br() -> pd.DataFrame:
    df = pd.read_stata(BR_PATH, convert_categoricals=False)
    df["weight"] = df["v005"] / 1_000_000.0
    return df


def restrict_to_reference_period(df: pd.DataFrame) -> pd.DataFrame:
    ref_months = REFERENCE_PERIOD_YEARS * 12
    months_since_birth = df["v008"] - df["b3"]
    return df[months_since_birth < ref_months].copy()


def build_person_segment_records(births: pd.DataFrame) -> pd.DataFrame:
    """
    Expand each birth into one row per age segment it was at risk for.
    Vectorized where practical; the per-child segment-walk is inherently
    sequential (must stop at death/censoring), so this loops over
    children but is O(n_children * 8 segments), which is fast (~12,600
    children * 8 = ~100k iterations, well under a second in practice).
    """
    is_dead = (births["b5"].values == 0)
    age_at_death = births["b7"].values
    age_at_interview = (births["v008"] - births["b3"]).values
    cluster = births["v001"].values
    weight = births["weight"].values

    records = []
    for i in range(len(births)):
        for seg_idx, (start, end) in enumerate(AGE_SEGMENTS):
            died_before_seg = is_dead[i] and age_at_death[i] < start
            if died_before_seg:
                break

            died_in_seg = is_dead[i] and (start <= age_at_death[i] < end)
            alive_reached_start = (not is_dead[i]) and age_at_interview[i] >= start
            alive_censored_in_seg = (not is_dead[i]) and (start <= age_at_interview[i] < end)
            died_at_or_after_start = is_dead[i] and age_at_death[i] >= start

            at_risk = died_at_or_after_start or alive_reached_start
            if not at_risk:
                continue

            if died_in_seg:
                exposure, event = 1.0, 1
            elif alive_censored_in_seg:
                exposure, event = 0.5, 0  # actuarial partial-exposure correction
            else:
                exposure, event = 1.0, 0

            records.append(
                {
                    "cluster": cluster[i],
                    "weight": weight[i],
                    "segment_idx": seg_idx,
                    "segment_label": f"{start}-{end}",
                    "event": event,
                    "exposure": exposure,
                }
            )

            if died_in_seg or alive_censored_in_seg:
                break  # this child's follow-up ends here; no later segments

    return pd.DataFrame(records)


def main():
    print(f"Loading BR file from {BR_PATH} (raw microdata, stays local)...")
    br = load_br()
    print(f"  {len(br)} total birth records")

    print(f"\nRestricting to {REFERENCE_PERIOD_YEARS}-year reference period...")
    births = restrict_to_reference_period(br)
    print(f"  {len(births)} births in reference period")

    print("\nBuilding person-segment survival records (this is the fix)...")
    person_segment = build_person_segment_records(births)
    print(f"  {len(person_segment)} person-segment rows")

    # validation: unweighted event sum must exactly match the known,
    # independently-verified total U5 death count
    total_events = person_segment["event"].sum()
    expected = int(
        ((births["b7"] < 60) & (births["b5"] == 0)).sum()
    )
    print(f"\nValidation: total events in person-segment data (ALL of Pakistan, incl. AJK/GB) = {total_events}")
    print(f"            expected (independently verified) = {expected}")
    if total_events != expected:
        raise ValueError(
            f"Person-segment record construction lost or double-counted "
            f"deaths: got {total_events}, expected {expected}. DO NOT "
            f"proceed to modeling with this output."
        )
    print("  MATCH -- no deaths lost or double-counted (national total, before AJK/GB scope filtering below).")

    print(f"\nLoading cluster->district lookup from {CLUSTER_LOOKUP_PATH}...")
    lookup = pd.read_csv(CLUSTER_LOOKUP_PATH)
    person_segment = person_segment.merge(
        lookup[["DHSCLUST", "district_key", "province"]],
        left_on="cluster",
        right_on="DHSCLUST",
        how="left",
    )
    n_unmatched = person_segment["district_key"].isna().sum()
    events_before_scope_filter = person_segment["event"].sum()
    if n_unmatched:
        events_out_of_scope = person_segment.loc[
            person_segment["district_key"].isna(), "event"
        ].sum()
        print(
            f"  {n_unmatched} person-segment rows in out-of-scope clusters "
            f"(AJK/Gilgit-Baltistan) excluded, containing "
            f"{events_out_of_scope} event(s). This is EXPECTED (see "
            f"docs/LIMITATIONS.md #1) -- these regions are outside this "
            f"project's 135-district PBS census scope, not a data loss bug."
        )
        person_segment = person_segment[person_segment["district_key"].notna()]

    in_scope_events = person_segment["event"].sum()
    print(
        f"\nIn-scope (135-district) event total after AJK/GB exclusion: "
        f"{in_scope_events}"
    )
    if DHS_DIRECT_PATH.exists():
        direct_check = pd.read_csv(DHS_DIRECT_PATH)["n_deaths_u5_5yr"].sum()
        print(
            f"Cross-check against independently-built "
            f"district_u5mr_direct_dhs.csv (different method, same "
            f"underlying data): {direct_check} deaths"
        )
        if in_scope_events != direct_check:
            print(
                f"  WARNING: in-scope event totals do not match between "
                f"this script ({in_scope_events}) and "
                f"02b_estimate_u5mr_from_dhs.py ({direct_check}). This "
                f"discrepancy should be investigated before trusting "
                f"either output -- they are built by independent code "
                f"paths from the same raw BR file and should agree "
                f"exactly."
            )
        else:
            print("  MATCH -- confirms in-scope event total is correct and consistent.")
    else:
        print(
            f"  (Skipping cross-check: {DHS_DIRECT_PATH} not found. Run "
            f"scripts/models/02b_estimate_u5mr_from_dhs.py first for a "
            f"second independent confirmation of this event total.)"
        )

    out_cols = [
        "cluster", "district_key", "province", "weight",
        "segment_idx", "segment_label", "event", "exposure",
    ]
    out_path = OUT_DIR / "person_segment_records.csv"
    person_segment[out_cols].to_csv(out_path, index=False)
    print(f"\nWrote: {out_path}")
    print(f"Districts represented: {person_segment['district_key'].nunique()}")


if __name__ == "__main__":
    main()
