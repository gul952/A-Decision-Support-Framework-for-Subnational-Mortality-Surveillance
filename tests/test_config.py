"""Tests for pkmortality.config -- naming standardization and paths."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pkmortality.config import standardize_district_name, prettify_district_name


def test_standardize_adds_district_suffix():
    assert standardize_district_name("Abbottabad") == "ABBOTTABAD DISTRICT"


def test_standardize_idempotent_on_existing_suffix():
    assert standardize_district_name("Bannu District") == "BANNU DISTRICT"


def test_standardize_handles_whitespace():
    assert standardize_district_name("  Lahore   ") == "LAHORE DISTRICT"


def test_standardize_known_override():
    assert standardize_district_name("D.G. Khan District") == "DERA GHAZI KHAN DISTRICT"


def test_standardize_none_passthrough():
    assert standardize_district_name(None) is None


def test_prettify_roundtrip():
    key = standardize_district_name("Karachi")
    assert prettify_district_name(key) == "Karachi"


def test_prettify_multiword():
    assert prettify_district_name("DERA GHAZI KHAN DISTRICT") == "Dera Ghazi Khan"
