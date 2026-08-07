"""Unit tests for geo cleaning rules + gold evaluation."""
import pandas as pd

from src.geo.eval_cleaning import evaluate_geo_cleaning, dry_run_repairs, load_rules_manifest
from src.geo.normalize import canonicalize_state
from src.geo.repair import full_geo_repair, apply_district_aliases
from src.geo.pin_map import state_from_pincode


def test_state_aliases():
    assert canonicalize_state("orissa") == "Odisha"
    assert canonicalize_state("Pondicherry") == "Puducherry"
    assert canonicalize_state("100000") == "Unknown"


def test_pin_prefix():
    assert state_from_pincode(560001) == "Karnataka"
    assert state_from_pincode(110001) == "Delhi"
    assert state_from_pincode(500001) == "Telangana"


def test_district_alias_bangalore():
    df = pd.DataFrame({"state": ["Karnataka"], "district": ["Bangalore"], "pincode": [560001]})
    out, n = apply_district_aliases(df)
    assert n == 1
    assert out.iloc[0]["district"] == "Bengaluru Urban"


def test_ap_to_telangana():
    df = pd.DataFrame(
        {
            "state": ["Andhra Pradesh", "Andhra Pradesh"],
            "district": ["Nalgonda", "Guntur"],
            "pincode": [508001, 522001],
        }
    )
    out, stats = full_geo_repair(df)
    assert stats["ap_to_telangana"] >= 1
    assert out.loc[out["district"] == "Nalgonda", "state"].iloc[0] == "Telangana"
    assert out.loc[out["district"] == "Guntur", "state"].iloc[0] == "Andhra Pradesh"


def test_gold_evaluation_high_accuracy():
    summary = evaluate_geo_cleaning()
    assert summary["n"] >= 10
    assert summary["state_accuracy"] >= 0.9
    assert summary["both_accuracy"] >= 0.9
    assert summary["rule_pack"] == load_rules_manifest().get("rule_pack_version")


def test_dry_run_report():
    df = pd.DataFrame(
        {
            "state": ["Andhra Pradesh", "Jaipur"],
            "district": ["Hyderabad", "Near hospital"],
            "pincode": [500001, 302016],
        }
    )
    rep = dry_run_repairs(df)
    assert rep["rows"] == 2
    assert "stats" in rep
