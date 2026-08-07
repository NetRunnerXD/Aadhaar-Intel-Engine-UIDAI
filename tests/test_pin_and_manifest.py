from src.config import GEO_RULE_PACK_VERSION, CACHE_SCHEMA_VERSION
from src.geo.eval_cleaning import load_rules_manifest


def test_manifest_version_aligned():
    m = load_rules_manifest()
    assert m.get("rule_pack_version") == GEO_RULE_PACK_VERSION
    assert m.get("schema_version") == CACHE_SCHEMA_VERSION
