"""Structural validation and dependency rules for the eight foundation files.

The model-facing prompts describe rich JSON documents, while ``AuthObject`` is
only a generic envelope.  This module is the executable contract between those
two layers: a parseable JSON object is not considered usable unless its required
top-level sections and cross references are present.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

FOUNDATION_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "spec00": (
        "genre",
        "complexity_profile",
        "main_promise",
        "lens",
        "lens_climate",
        "type_contract",
        "taboo_words",
        "budget",
        "core_hook",
        "protagonist_core",
        "scale_budget",
        "breather_policy",
        "writing_dictionary",
        "forbidden_zones",
        "self_check",
    ),
    "world_a": (
        "world_feel",
        "conflict_sources",
        "meaning_system",
        "motif_seeds",
        "forbidden_zones_and_contrasts",
        "self_check",
    ),
    "world_b": (
        "geography",
        "factions",
        "ecology",
        "power_distribution",
        "zones",
        "transport_and_trade",
        "institution_framework",
        "self_check",
    ),
    "pow_l": (
        "core_law",
        "conservation_rule",
        "cost_principle",
        "counter_points",
        "forbidden_abilities",
        "power_ceiling",
        "laws",
        "cost_principles",
        "term_table",
        "self_check",
    ),
    "pow_s": (
        "source",
        "path",
        "valve",
        "carrier",
        "damage_model",
        "vulnerability_model",
        "capacity_growth",
        "structure_elements",
        "damage_repair_system",
        "growth_stages",
        "self_check",
    ),
    "pow_e": (
        "culture",
        "schools",
        "equipment_interface",
        "terminology",
        "region_and_school_interfaces",
        "term_table",
        "self_check",
    ),
    "opp_eco": (
        "tier1_boss",
        "tier2_factions",
        "tier3_mobs",
        "gray_forces",
        "evolution_mechanism",
        "oppression_spectrum",
        "self_check",
    ),
    "cast": (
        "characters",
        "relationships",
        "knowledge_boundaries",
        "ensemble_balance",
    ),
}


FOUNDATION_FIELD_TYPES: dict[str, dict[str, type]] = {
    "spec00": {
        "complexity_profile": dict,
        "lens_climate": dict,
        "type_contract": dict,
        "taboo_words": list,
        "budget": dict,
        "protagonist_core": dict,
        "scale_budget": dict,
        "breather_policy": dict,
        "writing_dictionary": dict,
        "forbidden_zones": list,
        "self_check": dict,
    },
    "world_a": {
        "conflict_sources": list,
        "meaning_system": dict,
        "motif_seeds": list,
        "forbidden_zones_and_contrasts": dict,
        "self_check": dict,
    },
    "world_b": {
        "geography": dict,
        "factions": list,
        "ecology": dict,
        "power_distribution": dict,
        "zones": list,
        "transport_and_trade": dict,
        "institution_framework": dict,
        "self_check": dict,
    },
    "pow_l": {
        "counter_points": list,
        "forbidden_abilities": list,
        "laws": list,
        "cost_principles": list,
        "term_table": list,
        "self_check": dict,
    },
    "pow_s": {
        "structure_elements": list,
        "damage_repair_system": dict,
        "growth_stages": list,
        "self_check": dict,
    },
    "pow_e": {
        "schools": list,
        "terminology": dict,
        "region_and_school_interfaces": list,
        "term_table": list,
        "self_check": dict,
    },
    "opp_eco": {
        "tier1_boss": dict,
        "tier2_factions": list,
        "tier3_mobs": dict,
        "gray_forces": list,
        "oppression_spectrum": list,
        "self_check": dict,
    },
    "cast": {
        "characters": list,
        "relationships": list,
        "knowledge_boundaries": list,
        "ensemble_balance": list,
    },
}


# Direct read dependencies used by Graph1.  Rewind computes the transitive
# downstream closure from this single map so regeneration cannot leave a stale
# child document active.
FOUNDATION_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "spec00": (),
    "world_a": ("spec00",),
    "world_b": ("spec00", "world_a"),
    "pow_l": ("spec00", "world_a"),
    "pow_s": ("spec00", "world_a", "world_b", "pow_l"),
    "pow_e": ("spec00", "world_a", "pow_l", "pow_s"),
    "opp_eco": ("spec00", "world_a", "world_b", "pow_l", "pow_s", "pow_e"),
    "cast": ("spec00", "world_b", "opp_eco"),
}


_ALLOW_EMPTY: set[tuple[str, str]] = {
    ("opp_eco", "gray_forces"),
}


_CHARACTER_REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "role",
    "identity",
    "background",
    "public_goal",
    "motivation",
    "inner_design",
    "ability",
    "relationship_to_protagonist",
    "known_facts",
    "unknown_facts",
    "performance_anchors",
    "scene_engine",
    "entry_stage",
)


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _missing_fields(content: dict[str, Any], fields: Iterable[str]) -> list[str]:
    return [field for field in fields if field not in content]


def validate_foundation_content(
    artifact_key: str,
    content: Any,
    *,
    complexity_level: str | None = None,
) -> list[str]:
    """Return human-readable structural errors for one foundation document."""
    if artifact_key not in FOUNDATION_REQUIRED_FIELDS:
        return [f"未知作品基座文件：{artifact_key}"]
    if not isinstance(content, dict):
        return ["顶层必须是 JSON 对象"]

    errors: list[str] = []
    required = FOUNDATION_REQUIRED_FIELDS[artifact_key]
    missing = _missing_fields(content, required)
    if missing:
        errors.append("缺少顶层字段：" + "、".join(missing))

    for field in required:
        if field not in content or (artifact_key, field) in _ALLOW_EMPTY:
            continue
        if not _has_content(content[field]):
            errors.append(f"字段 {field} 不能为空")

    for field, expected_type in FOUNDATION_FIELD_TYPES.get(artifact_key, {}).items():
        if field in content and not isinstance(content[field], expected_type):
            label = "数组" if expected_type is list else "对象"
            errors.append(f"字段 {field} 必须是 JSON {label}")

    if artifact_key == "spec00":
        profile = content.get("complexity_profile")
        if isinstance(profile, dict):
            level = str(profile.get("level") or "").lower()
            if level not in {"low", "medium", "high"}:
                errors.append("complexity_profile.level 必须是 low、medium 或 high")

    if artifact_key == "cast" and isinstance(content.get("characters"), list):
        errors.extend(_validate_cast(content, complexity_level=complexity_level))

    return errors


def _validate_cast(content: dict[str, Any], *, complexity_level: str | None) -> list[str]:
    errors: list[str] = []
    characters = content.get("characters") or []
    level = (complexity_level or "").lower()
    minimum = {"low": 4, "medium": 6, "high": 8}.get(level, 4)
    if len(characters) < minimum:
        errors.append(f"characters 至少需要 {minimum} 名核心角色（当前 {len(characters)} 名）")

    ids: list[str] = []
    for index, character in enumerate(characters, start=1):
        if not isinstance(character, dict):
            errors.append(f"characters[{index - 1}] 必须是对象")
            continue
        missing = _missing_fields(character, _CHARACTER_REQUIRED_FIELDS)
        if missing:
            errors.append(f"角色 {index} 缺少字段：" + "、".join(missing))
        char_id = str(character.get("id") or "").strip()
        if char_id:
            ids.append(char_id)
    if len(ids) != len(set(ids)):
        errors.append("characters 中存在重复 id")

    known_ids = set(ids)
    for index, relation in enumerate(content.get("relationships") or []):
        if not isinstance(relation, dict):
            errors.append(f"relationships[{index}] 必须是对象")
            continue
        for field in ("from_id", "to_id", "current_state", "tension", "forbidden_jump"):
            if not _has_content(relation.get(field)):
                errors.append(f"relationships[{index}] 缺少 {field}")
        for field in ("from_id", "to_id"):
            ref = str(relation.get(field) or "")
            if ref and ref not in known_ids:
                errors.append(f"relationships[{index}].{field} 引用了不存在的角色 {ref}")

    for index, boundary in enumerate(content.get("knowledge_boundaries") or []):
        if not isinstance(boundary, dict):
            errors.append(f"knowledge_boundaries[{index}] 必须是对象")
            continue
        for field in ("fact", "known_by", "unknown_to", "reveal_condition"):
            if field not in boundary:
                errors.append(f"knowledge_boundaries[{index}] 缺少 {field}")
        for field in ("known_by", "unknown_to"):
            refs = boundary.get(field)
            if isinstance(refs, list):
                unknown = [str(ref) for ref in refs if str(ref) not in known_ids]
                if unknown:
                    errors.append(
                        f"knowledge_boundaries[{index}].{field} 引用了不存在的角色："
                        + "、".join(unknown)
                    )

    balance_ids = {
        str(item.get("character_id") or "")
        for item in content.get("ensemble_balance") or []
        if isinstance(item, dict)
    }
    missing_balance = [char_id for char_id in ids if char_id not in balance_ids]
    if missing_balance:
        errors.append("ensemble_balance 缺少角色：" + "、".join(missing_balance))
    return errors


def validate_cast_roster(content: Any, complexity_level: str) -> list[str]:
    if not isinstance(content, dict):
        return ["阵容索引顶层必须是 JSON 对象"]
    roster = content.get("roster")
    if not isinstance(roster, list):
        return ["阵容索引缺少 roster 数组"]
    minimum = {"low": 4, "medium": 6, "high": 8}.get(complexity_level, 4)
    if len(roster) < minimum:
        return [f"roster 至少需要 {minimum} 名角色（当前 {len(roster)} 名）"]
    errors: list[str] = []
    ids: list[str] = []
    for index, item in enumerate(roster):
        if not isinstance(item, dict):
            errors.append(f"roster[{index}] 必须是对象")
            continue
        for field in ("id", "name", "role", "identity", "public_goal", "entry_stage"):
            if not _has_content(item.get(field)):
                errors.append(f"roster[{index}] 缺少 {field}")
        if item.get("id"):
            ids.append(str(item["id"]))
    if len(ids) != len(set(ids)):
        errors.append("roster 中存在重复 id")
    return errors


def validate_character_dossier(content: Any, expected_id: str) -> list[str]:
    if not isinstance(content, dict) or not isinstance(content.get("character"), dict):
        return ["单角色档案必须包含 character 对象"]
    character = content["character"]
    errors = [
        "单角色档案缺少字段：" + "、".join(missing)
        for missing in [_missing_fields(character, _CHARACTER_REQUIRED_FIELDS)]
        if missing
    ]
    actual_id = str(character.get("id") or "")
    if actual_id != expected_id:
        errors.append(f"角色 id 必须保持为 {expected_id}，实际为 {actual_id or '空'}")
    return errors


def validate_cast_relations(content: Any, character_ids: set[str]) -> list[str]:
    if not isinstance(content, dict):
        return ["关系输出顶层必须是 JSON 对象"]
    required = ("relationships", "knowledge_boundaries", "ensemble_balance")
    errors: list[str] = []
    missing = _missing_fields(content, required)
    if missing:
        errors.append("关系输出缺少字段：" + "、".join(missing))
    for field in required:
        if field in content and not isinstance(content[field], list):
            errors.append(f"关系输出字段 {field} 必须是数组")
    if errors:
        return errors
    assembled = {
        "characters": [
            {
                "id": char_id,
                **{field: "占位" for field in _CHARACTER_REQUIRED_FIELDS if field != "id"},
            }
            for char_id in character_ids
        ],
        **content,
    }
    # The assembled placeholders intentionally satisfy only character shape;
    # relation/reference validation is shared with the final cast validator.
    return [
        error
        for error in _validate_cast(assembled, complexity_level="low")
        if not error.startswith("角色 ")
    ]


def foundation_downstream_closure(step_key: str) -> list[str]:
    """Return the selected step plus every transitively dependent foundation file."""
    if step_key not in FOUNDATION_DEPENDENCIES:
        raise ValueError(f"未知作品基座步骤：{step_key}")
    invalidated = {step_key}
    changed = True
    while changed:
        changed = False
        for candidate, dependencies in FOUNDATION_DEPENDENCIES.items():
            if candidate not in invalidated and invalidated.intersection(dependencies):
                invalidated.add(candidate)
                changed = True
    return [key for key in FOUNDATION_DEPENDENCIES if key in invalidated]


def format_validation_errors(errors: list[str], *, limit: int = 4) -> str:
    if not errors:
        return ""
    shown = errors[:limit]
    suffix = f"；另有 {len(errors) - limit} 项" if len(errors) > limit else ""
    return "；".join(shown) + suffix
