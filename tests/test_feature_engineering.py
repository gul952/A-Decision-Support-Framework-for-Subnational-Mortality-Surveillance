"""
Tests for Layer 2 feature engineering -- specifically the DHS-preferred,
census-fallback logic in build_education_indicator(), build_wealth_
indicator(), and build_anc_deficit_index(). This is the layer where a
real edge case (Kohistan District, both sources missing simultaneously)
was found during development -- see docs/LIMITATIONS.md #11 -- and
where no automated tests existed until now.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import importlib.util

spec = importlib.util.spec_from_file_location(
    "composite_indices",
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "features"
    / "01_build_composite_indices.py",
)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def make_df(rows):
    """Build a minimal DataFrame with the columns build_education_indicator
    and build_wealth_indicator expect, filling sensible defaults for
    anything not explicitly specified per row."""
    defaults = {
        "district_key": None,  # overwritten below with a unique value per row
        "mean_years_education": np.nan,
        "low_dhs_ir_coverage": True,
        "literacy_rate_pct": np.nan,
        "mean_wealth_score": np.nan,
        "low_dhs_hr_coverage": True,
        "wash_index": 0.5,
        "mean_anc_visits": np.nan,
        "low_dhs_anc_coverage": True,
    }
    out = []
    for i, r in enumerate(rows):
        row = {**defaults, **r}
        if row["district_key"] is None:
            row["district_key"] = f"TEST DISTRICT {i}"
        out.append(row)
    return pd.DataFrame(out)


class TestEducationIndicator:
    def test_uses_dhs_when_coverage_adequate(self):
        df = make_df(
            [
                {"mean_years_education": 8.0, "low_dhs_ir_coverage": False, "literacy_rate_pct": 40.0},
                {"mean_years_education": 2.0, "low_dhs_ir_coverage": False, "literacy_rate_pct": 60.0},
            ]
        )
        result = ci.build_education_indicator(df)
        assert (result["education_data_source"] == "dhs").all()
        # higher years of education -> higher adequacy, regardless of
        # what census literacy says (since DHS should be preferred here)
        assert result.loc[0, "education_adequacy"] > result.loc[1, "education_adequacy"]

    def test_falls_back_to_census_when_dhs_coverage_thin(self):
        df = make_df(
            [
                {"mean_years_education": 8.0, "low_dhs_ir_coverage": True, "literacy_rate_pct": 30.0},
                {"mean_years_education": 2.0, "low_dhs_ir_coverage": True, "literacy_rate_pct": 90.0},
            ]
        )
        result = ci.build_education_indicator(df)
        assert (result["education_data_source"] == "census").all()
        # census literacy should now drive the ordering, not DHS years
        assert result.loc[1, "education_adequacy"] > result.loc[0, "education_adequacy"]

    def test_falls_back_to_census_when_dhs_value_missing_even_if_flagged_adequate(self):
        """low_dhs_ir_coverage=False but mean_years_education is NaN
        (e.g. a data quality edge case) should still fall back safely,
        not propagate a NaN into education_adequacy."""
        df = make_df(
            [{"mean_years_education": np.nan, "low_dhs_ir_coverage": False, "literacy_rate_pct": 50.0}]
        )
        result = ci.build_education_indicator(df)
        assert result.loc[0, "education_data_source"] == "census"
        assert not pd.isna(result.loc[0, "education_adequacy"])

    def test_double_fallback_produces_median_imputation_not_nan(self):
        """The Kohistan case: neither DHS nor census data available at
        all. Must not crash, must not leave a NaN, must be flagged.
        Uses varying literacy values in the other rows so the census
        column has real variance (rng != 0) -- with a constant literacy
        column, minmax_normalize's zero-variance fallback (0.5 for
        every row, including the NaN one) would mask the double-
        fallback path entirely, since row 0 would never actually
        produce a NaN to trigger the imputed_median branch. This
        interaction was discovered while writing this test."""
        df = make_df(
            [
                {"mean_years_education": np.nan, "low_dhs_ir_coverage": True, "literacy_rate_pct": np.nan},
                {"mean_years_education": 6.0, "low_dhs_ir_coverage": False, "literacy_rate_pct": 30.0},
                {"mean_years_education": 4.0, "low_dhs_ir_coverage": False, "literacy_rate_pct": 70.0},
            ]
        )
        result = ci.build_education_indicator(df)
        assert result.loc[0, "education_data_source"] == "imputed_median"
        assert not pd.isna(result.loc[0, "education_adequacy"])
        # imputed value should be the median of the OTHER (valid) rows
        expected_median = result.loc[[1, 2], "education_adequacy"].median()
        assert result.loc[0, "education_adequacy"] == pytest.approx(expected_median)


class TestWealthIndicator:
    def test_uses_dhs_when_coverage_adequate(self):
        df = make_df(
            [
                {"mean_wealth_score": 2.0, "low_dhs_hr_coverage": False, "wash_index": 0.1},
                {"mean_wealth_score": -2.0, "low_dhs_hr_coverage": False, "wash_index": 0.9},
            ]
        )
        result = ci.build_wealth_indicator(df)
        assert (result["wealth_data_source"] == "dhs").all()
        assert result.loc[0, "wealth_adequacy"] > result.loc[1, "wealth_adequacy"]

    def test_falls_back_to_wash_proxy_when_dhs_thin(self):
        df = make_df(
            [
                {"mean_wealth_score": 2.0, "low_dhs_hr_coverage": True, "wash_index": 0.1},
                {"mean_wealth_score": -2.0, "low_dhs_hr_coverage": True, "wash_index": 0.9},
            ]
        )
        result = ci.build_wealth_indicator(df)
        assert (result["wealth_data_source"] == "census_wash_proxy").all()
        # wash_index should now drive it directly (wealth_adequacy ==
        # wash_index in the fallback branch, since it's used as-is)
        assert result.loc[1, "wealth_adequacy"] > result.loc[0, "wealth_adequacy"]

    def test_wealth_fallback_never_produces_nan(self):
        """Unlike education, wealth's fallback (wash_index) always has
        full coverage in the real pipeline, so this path should never
        produce a NaN even in a degenerate all-missing-DHS scenario."""
        df = make_df(
            [{"mean_wealth_score": np.nan, "low_dhs_hr_coverage": True, "wash_index": 0.42}]
        )
        result = ci.build_wealth_indicator(df)
        assert result.loc[0, "wealth_adequacy"] == 0.42
        assert result.loc[0, "wealth_data_source"] == "census_wash_proxy"


class TestAncDeficitIndex:
    def test_no_census_fallback_exists_missing_becomes_imputed(self):
        """ANC has no census equivalent at all -- unlike education/wealth,
        there is no intermediate fallback source, only DHS-or-imputed."""
        df = make_df(
            [
                {"mean_anc_visits": np.nan, "low_dhs_anc_coverage": True},
                {"mean_anc_visits": 4.0, "low_dhs_anc_coverage": False},
                {"mean_anc_visits": 8.0, "low_dhs_anc_coverage": False},
            ]
        )
        result = ci.build_anc_deficit_index(df)
        assert result.loc[0, "anc_data_source"] == "imputed_median"
        assert result.loc[1, "anc_data_source"] == "dhs"
        assert not pd.isna(result.loc[0, "anc_deficit_index"])

    def test_higher_visits_means_lower_deficit(self):
        df = make_df(
            [
                {"mean_anc_visits": 1.0, "low_dhs_anc_coverage": False},
                {"mean_anc_visits": 8.0, "low_dhs_anc_coverage": False},
            ]
        )
        result = ci.build_anc_deficit_index(df)
        assert result.loc[0, "anc_deficit_index"] > result.loc[1, "anc_deficit_index"]


class TestMinmaxNormalize:
    def test_degenerate_constant_series_returns_half(self):
        s = pd.Series([3.0, 3.0, 3.0])
        result = ci.minmax_normalize(s)
        assert (result == 0.5).all()

    def test_standard_range_maps_to_zero_one(self):
        s = pd.Series([0.0, 5.0, 10.0])
        result = ci.minmax_normalize(s)
        assert result.iloc[0] == 0.0
        assert result.iloc[2] == 1.0
        assert result.iloc[1] == pytest.approx(0.5)
