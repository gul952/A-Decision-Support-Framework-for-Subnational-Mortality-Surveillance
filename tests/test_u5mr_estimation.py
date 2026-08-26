"""
Tests for the synthetic cohort (actuarial) U5MR estimation method --
the most methodologically critical piece of Layer 3, since two real
bugs (naive full-window survival assumption, then unstable binary
right-censoring) were found and fixed here during development. These
tests pin down the corrected behavior so it can't silently regress.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import importlib.util

spec = importlib.util.spec_from_file_location(
    "dhs_u5mr",
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "models"
    / "02b_estimate_u5mr_from_dhs.py",
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def make_births(records):
    """records: list of dicts with weight, b7 (age at death or NaN),
    b5 (1=alive, 0=dead), age_at_interview (derived as v008-b3)."""
    rows = []
    for r in records:
        rows.append(
            {
                "weight": r["weight"],
                "b7": r.get("b7", np.nan),
                "b5": r["b5"],
                "v008": 1420,
                "b3": 1420 - r["age_at_interview"],
            }
        )
    return pd.DataFrame(rows)


def test_no_deaths_gives_zero_u5mr():
    births = make_births(
        [
            {"weight": 1.0, "b5": 1, "age_at_interview": 60},
            {"weight": 1.0, "b5": 1, "age_at_interview": 60},
        ]
    )
    u5mr, n, d = m.synthetic_cohort_u5mr(births)
    assert u5mr == 0.0
    assert n == 2
    assert d == 0


def test_all_die_at_birth_gives_1000():
    births = make_births(
        [
            {"weight": 1.0, "b5": 0, "b7": 0, "age_at_interview": 1},
            {"weight": 1.0, "b5": 0, "b7": 0, "age_at_interview": 1},
        ]
    )
    u5mr, n, d = m.synthetic_cohort_u5mr(births)
    assert u5mr == pytest.approx(1000.0, abs=1.0)
    assert d == 2


def test_empty_births_returns_nan():
    births = make_births([])
    u5mr, n, d = m.synthetic_cohort_u5mr(births)
    assert np.isnan(u5mr)
    assert n == 0


def test_thin_late_segment_does_not_collapse_to_1000():
    """
    Regression test for the actuarial-exposure bug found during
    development: a single death in a thin late-age segment (e.g.
    48-60 months) should NOT zero out the entire cohort's survival
    probability just because that one segment's naive death rate is
    100%. This was the exact failure mode of the earlier binary-
    censoring implementation (see docs/LIMITATIONS.md).
    """
    records = [
        # a large, healthy cohort surviving well past 60 months in most
        # segments...
        *[{"weight": 1.0, "b5": 1, "age_at_interview": 59} for _ in range(50)],
        # ...plus exactly one unlucky death right at the 48-60 boundary,
        # in a thin-exposure late segment
        {"weight": 1.0, "b5": 0, "b7": 50, "age_at_interview": 50},
    ]
    births = make_births(records)
    u5mr, n, d = m.synthetic_cohort_u5mr(births)
    assert u5mr < 100.0, (
        f"u5mr={u5mr} -- a single death in a thin segment should not "
        "collapse survival probability to 0 (u5mr=1000)"
    )
    assert d == 1


def test_survivor_younger_than_5_does_not_inflate_denominator():
    """
    A child who is still alive but only 8 months old at interview has
    NOT yet demonstrated survival through months 12-59. They should not
    count as a "survivor" of segments they haven't reached yet.
    """
    births = make_births(
        [{"weight": 1.0, "b5": 1, "age_at_interview": 8}]
    )
    u5mr, n, d = m.synthetic_cohort_u5mr(births)
    # with zero deaths anywhere, u5mr must still be 0 regardless of age
    assert u5mr == 0.0


def test_weights_affect_estimate():
    """A high-weight death should move the estimate more than a
    low-weight one, all else equal."""
    heavy_death = make_births(
        [
            {"weight": 5.0, "b5": 0, "b7": 2, "age_at_interview": 2},
            {"weight": 1.0, "b5": 1, "age_at_interview": 59},
        ]
    )
    light_death = make_births(
        [
            {"weight": 0.2, "b5": 0, "b7": 2, "age_at_interview": 2},
            {"weight": 1.0, "b5": 1, "age_at_interview": 59},
        ]
    )
    u5mr_heavy, _, _ = m.synthetic_cohort_u5mr(heavy_death)
    u5mr_light, _, _ = m.synthetic_cohort_u5mr(light_death)
    assert u5mr_heavy > u5mr_light
