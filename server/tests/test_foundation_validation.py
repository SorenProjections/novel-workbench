from novelwb.engine.foundation_validation import (
    foundation_downstream_closure,
    validate_foundation_content,
)


def test_partial_nested_foundation_fragments_are_rejected():
    world_b = {
        "macro_structure": "三域并立",
        "key_locations": ["宗门"],
        "resource_hotspots": ["矿脉"],
    }
    pow_s = {"外伤": "影响出力", "经脉损伤": "影响传导"}
    opp_eco = {
        "name": "天脉圣主",
        "identity": "圣地主人",
        "motivation": "突破",
        "power_ceiling": "神台境",
        "reveals": ["第一卷登场"],
    }

    assert "geography" in validate_foundation_content("world_b", world_b)[0]
    assert "damage_repair_system" in validate_foundation_content("pow_s", pow_s)[0]
    assert "tier1_boss" in validate_foundation_content("opp_eco", opp_eco)[0]


def test_foundation_downstream_closure_preserves_independent_power_law():
    assert foundation_downstream_closure("world_b") == [
        "world_b", "pow_s", "pow_e", "opp_eco", "cast",
    ]
    assert "pow_l" not in foundation_downstream_closure("world_b")
    assert foundation_downstream_closure("cast") == ["cast"]
