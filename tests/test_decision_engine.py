"""
Tests for the decision engine (Layer 4) -- priority score computation
logic, isolated from file I/O so it can run without the full pipeline's
processed data present.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "decision"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "prioritization_engine",
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "decision"
    / "01_prioritization_engine.py",
)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)


@pytest.fixture
def toy_df():
    return pd.DataFrame(
        {
            "district_key": ["A DISTRICT", "B DISTRICT", "C DISTRICT"],
            "province": ["X", "X", "Y"],
            "had_direct_data": [True, False, True],
            "u5mr_posterior_mean": [50.0, 100.0, 75.0],
            "ci_width": [20.0, 80.0, 40.0],
            "remoteness_proxy": [0.1, 0.9, 0.5],
            "population_2017": [1_000_000, 200_000, 500_000],
        }
    )


def test_weights_must_sum_to_one(toy_df):
    bad_weights = {
        "mortality_risk": 0.5, "uncertainty": 0.5,
        "geographic_accessibility_proxy": 0.5, "population": 0.5,
    }
    with pytest.raises(AssertionError):
        pe.compute_priority_scores(toy_df, bad_weights)


def test_highest_mortality_ranks_first_under_mortality_only_weights(toy_df):
    weights = {
        "mortality_risk": 1.0, "uncertainty": 0.0,
        "geographic_accessibility_proxy": 0.0, "population": 0.0,
    }
    result = pe.compute_priority_scores(toy_df, weights)
    assert result.iloc[0]["district_key"] == "B DISTRICT"  # highest u5mr


def test_rank_1_is_top_priority_score(toy_df):
    result = pe.compute_priority_scores(toy_df, pe.DEFAULT_WEIGHTS)
    top = result[result["rank"] == 1].iloc[0]
    assert top["priority_score"] == result["priority_score"].max()


def test_minmax_normalize_degenerate_case():
    constant = pd.Series([5.0, 5.0, 5.0])
    result = pe.minmax_normalize(constant)
    assert (result == 0.5).all()  # no crash, sensible default


def test_recommend_for_budget_returns_correct_count(toy_df):
    scored = pe.compute_priority_scores(toy_df, pe.DEFAULT_WEIGHTS)
    top2 = pe.recommend_for_budget(scored, 2)
    assert len(top2) == 2
