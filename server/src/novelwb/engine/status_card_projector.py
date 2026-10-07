"""Build the initial, rebuildable status-card projection from authority artifacts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from novelwb.core.constants import AuthObjectType, StatusCardType
from novelwb.core.schemas.domain_models import AuthObject, SourceRef, StatusCard

_RULE_NAMES = {
    "pow_l": "力量定律",
    "pow_s": "力量结构",
    "pow_e": "力量表现",
}


def project_initial_status_cards(auth_objects: Iterable[AuthObject]) -> list[StatusCard]:
    """Project compact navigation cards without inventing facts outside authority data."""
    cards: dict[str, StatusCard] = {}
    for obj in auth_objects:
        content = obj.content if isinstance(obj.content, dict) else {}
        object_id = obj.object_id.lower()

        if obj.object_type == AuthObjectType.CONTRACT:
            _project_contract(cards, obj, content)
        if obj.object_type == AuthObjectType.BIBLE:
            _project_bible(cards, obj, content)
        if obj.object_type == AuthObjectType.CHAR:
            _project_char(cards, obj, content)
        if obj.object_type == AuthObjectType.REG:
            _project_reg(cards, obj, content, object_id)

    return sorted(cards.values(), key=lambda card: (card.card_type.value, card.card_id))


def _project_contract(
    cards: dict[str, StatusCard], obj: AuthObject, content: dict[str, Any]
) -> None:
    slots = content.get("event_slots")
    if isinstance(slots, list):
        title = str(content.get("title") or content.get("volume_id") or "当前卷")
        if content.get("volume_promise"):
            _put(
                cards,
                _card(
                    StatusCardType.PLOT,
                    f"卷主线：{title}",
                    content,
                    obj,
                    "volume_contract",
                    subject_id=str(content.get("volume_id") or obj.object_id),
                ),
            )
        for position, slot in enumerate(slots, start=1):
            if not isinstance(slot, dict):
                continue
            slot_id = str(slot.get("slot_id") or f"slot_{position:03d}")
            goal = str(slot.get("event_goal") or slot.get("title") or slot_id)
            _put(
                cards,
                _card(
                    StatusCardType.PLOT,
                    f"事件{position}：{_shorten(goal, 32)}",
                    slot,
                    obj,
                    f"event_slots[{position - 1}]",
                    subject_id=slot_id,
                    card_id=f"plot_{_slug(slot_id)}",
                ),
            )

    motifs = content.get("motif_arc")
    for position, motif in enumerate(motifs if isinstance(motifs, list) else [], start=1):
        if not isinstance(motif, dict):
            continue
        name = str(motif.get("motif") or motif.get("name") or f"核心意象{position}")
        _put(cards, _card(StatusCardType.ITEM, name, motif, obj, f"motif_arc[{position - 1}]"))

    story_room = content.get("story_room")
    if isinstance(story_room, dict):
        _project_story_room(
            cards,
            obj,
            story_room,
            volume_scope="volume_story_engine" in story_room,
        )


def _project_bible(cards: dict[str, StatusCard], obj: AuthObject, content: dict[str, Any]) -> None:
    protagonist = content.get("protagonist_core")
    if isinstance(protagonist, dict):
        main_promise = str(content.get("main_promise") or "")
        name = _protagonist_name(main_promise) or "主角"
        payload = {"main_promise": main_promise, **protagonist}
        _put(
            cards,
            _card(
                StatusCardType.CHARACTER,
                name,
                payload,
                obj,
                "protagonist_core",
                subject_id="protagonist",
                card_id=f"character_{_slug(name)}",
            ),
        )

        rules_payload = {
            "genre": content.get("genre"),
            "lens": content.get("lens"),
            "complexity_profile": content.get("complexity_profile"),
            "taboo_words": content.get("taboo_words"),
            "forbidden_zones": content.get("forbidden_zones"),
            "scale_budget": content.get("scale_budget"),
        }
        _put(
            cards,
            _card(
                StatusCardType.RULE,
                "创作规格与硬约束",
                rules_payload,
                obj,
                "spec00",
                card_id="rule_story_contract",
            ),
        )

    geography = content.get("geography")
    if isinstance(geography, dict):
        _project_named_list(
            cards,
            StatusCardType.SCENE,
            geography.get("key_locations"),
            obj,
            "geography.key_locations",
        )
    _project_named_list(cards, StatusCardType.SCENE, content.get("zones"), obj, "zones")
    _project_named_list(cards, StatusCardType.FACTION, content.get("factions"), obj, "factions")

    story_room = content.get("story_room")
    if isinstance(story_room, dict):
        _project_story_room(cards, obj, story_room, volume_scope=False)


def _project_story_room(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    story_room: dict[str, Any],
    *,
    volume_scope: bool,
) -> None:
    if volume_scope:
        engine = story_room.get("volume_story_engine")
        if isinstance(engine, dict):
            _put(
                cards,
                _card(
                    StatusCardType.PLOT,
                    "本卷故事引擎",
                    engine,
                    obj,
                    "story_room.volume_story_engine",
                    card_id="plot_volume_story_engine",
                ),
            )

        arcs = {
            str(item.get("character_id")): item
            for item in story_room.get("volume_character_arcs", [])
            if isinstance(item, dict) and item.get("character_id")
        }
        relationships = story_room.get("relationship_tracks", [])
        _project_relationship_cards(
            cards,
            obj,
            relationships,
            "story_room.relationship_tracks",
        )
        volume_cast = story_room.get("volume_cast_cards")
        for position, character in enumerate(volume_cast if isinstance(volume_cast, list) else []):
            if not isinstance(character, dict):
                continue
            character_id = str(character.get("character_id") or "").strip()
            name = str(character.get("name") or character_id).strip()
            if not character_id or not name:
                continue
            related = (
                [
                    item
                    for item in (relationships or [])
                    if isinstance(item, dict)
                    and character_id in {str(value) for value in item.get("character_ids", [])}
                ]
                if isinstance(relationships, list)
                else []
            )
            payload = {
                "volume_arc": arcs.get(character_id, {}),
                "relationship_tracks": related,
                **character,
            }
            _put(
                cards,
                _card(
                    StatusCardType.CHARACTER,
                    name,
                    payload,
                    obj,
                    f"story_room.volume_cast_cards[{position}]",
                    subject_id=character_id,
                    card_id=f"character_{_slug(character_id)}",
                ),
                replace=True,
            )

        _project_hook_cards(
            cards,
            obj,
            story_room.get("volume_foreshadowing"),
            "story_room.volume_foreshadowing",
        )
        map_system = story_room.get("volume_map_system")
        if isinstance(map_system, dict):
            _project_map_cards(
                cards,
                obj,
                map_system.get("locations"),
                "story_room.volume_map_system.locations",
                id_key="location_id",
                prefix="location",
            )
        _project_map_cards(
            cards,
            obj,
            story_room.get("scene_assets"),
            "story_room.scene_assets",
            id_key="scene_id",
            prefix="asset",
        )
        _project_lifecycle_cards(
            cards,
            obj,
            story_room.get("volume_line_ledger"),
            "story_room.volume_line_ledger",
            id_key="line_id",
            card_type=StatusCardType.PLOT,
            prefix="line",
        )
        _project_agenda_cards(cards, obj, story_room.get("entity_agendas"))
        _project_lifecycle_cards(
            cards,
            obj,
            story_room.get("key_item_tracks"),
            "story_room.key_item_tracks",
            id_key="item_id",
            card_type=StatusCardType.ITEM,
            prefix="track",
        )
        _project_lifecycle_cards(
            cards,
            obj,
            story_room.get("set_piece_plans"),
            "story_room.set_piece_plans",
            id_key="set_piece_id",
            card_type=StatusCardType.PLOT,
            prefix="set_piece",
        )
        _project_transient_cards(cards, obj, story_room.get("transient_assets"))
        return

    master = story_room.get("master_story_design")
    if isinstance(master, dict):
        _put(
            cards,
            _card(
                StatusCardType.PLOT,
                "全书总纲",
                master,
                obj,
                "story_room.master_story_design",
                card_id="plot_master_story_design",
            ),
        )
    _project_hook_cards(
        cards,
        obj,
        story_room.get("major_foreshadowing"),
        "story_room.major_foreshadowing",
    )
    _project_relationship_cards(
        cards,
        obj,
        story_room.get("ensemble_relationship_index"),
        "story_room.ensemble_relationship_index",
    )
    _project_relationship_cards(
        cards,
        obj,
        story_room.get("ensemble_relationship_arcs"),
        "story_room.ensemble_relationship_arcs",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("narrative_line_index"),
        "story_room.narrative_line_index",
        id_key="line_id",
        card_type=StatusCardType.PLOT,
        prefix="line",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("narrative_line_registry"),
        "story_room.narrative_line_registry",
        id_key="line_id",
        card_type=StatusCardType.PLOT,
        prefix="line",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("key_item_index"),
        "story_room.key_item_index",
        id_key="item_id",
        card_type=StatusCardType.ITEM,
        prefix="arc",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("key_item_arcs"),
        "story_room.key_item_arcs",
        id_key="item_id",
        card_type=StatusCardType.ITEM,
        prefix="arc",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("major_set_piece_index"),
        "story_room.major_set_piece_index",
        id_key="set_piece_id",
        card_type=StatusCardType.PLOT,
        prefix="set_piece",
    )
    _project_lifecycle_cards(
        cards,
        obj,
        story_room.get("major_set_piece_seeds"),
        "story_room.major_set_piece_seeds",
        id_key="set_piece_id",
        card_type=StatusCardType.PLOT,
        prefix="set_piece",
    )
    lifecycle_policy = story_room.get("asset_lifecycle_policy")
    if isinstance(lifecycle_policy, dict):
        _put(
            cards,
            _card(
                StatusCardType.RULE,
                "叙事资产生命周期",
                lifecycle_policy,
                obj,
                "story_room.asset_lifecycle_policy",
                card_id="rule_asset_lifecycle",
            ),
            replace=True,
        )
    growth_arcs = story_room.get("character_growth_arcs")
    for position, arc in enumerate(growth_arcs if isinstance(growth_arcs, list) else []):
        if not isinstance(arc, dict):
            continue
        character_id = str(arc.get("character_id") or "").strip()
        name = str(arc.get("name") or character_id).strip()
        if not character_id or not name:
            continue
        _put(
            cards,
            _card(
                StatusCardType.CHARACTER,
                f"成长线：{name}",
                arc,
                obj,
                f"story_room.character_growth_arcs[{position}]",
                subject_id=character_id,
                card_id=f"character_growth_{_slug(character_id)}",
            ),
        )
    map_system = story_room.get("major_map_system")
    if isinstance(map_system, dict):
        _project_map_cards(
            cards,
            obj,
            map_system.get("major_regions"),
            "story_room.major_map_system.major_regions",
            id_key="map_id",
            prefix="major_map",
        )


def _project_hook_cards(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    values: Any,
    path: str,
) -> None:
    for position, hook in enumerate(values if isinstance(values, list) else []):
        if not isinstance(hook, dict):
            continue
        hook_id = str(hook.get("hook_id") or f"hook_{position + 1:03d}")
        name = str(hook.get("name") or hook.get("purpose") or hook_id)
        _put(
            cards,
            _card(
                StatusCardType.PLOT,
                f"伏笔：{_shorten(name, 28)}",
                hook,
                obj,
                f"{path}[{position}]",
                subject_id=hook_id,
                card_id=f"plot_hook_{_slug(hook_id)}",
            ),
            replace=True,
        )


def _project_relationship_cards(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    values: Any,
    path: str,
) -> None:
    """Project one evolving card per stable relationship across book and volume layers."""
    for position, relationship in enumerate(values if isinstance(values, list) else []):
        if not isinstance(relationship, dict):
            continue
        relationship_id = str(relationship.get("relationship_id") or "").strip()
        if not relationship_id:
            continue
        character_ids = relationship.get("character_ids", [])
        fallback_name = (
            " ↔ ".join(map(str, character_ids))
            if isinstance(character_ids, list)
            else relationship_id
        )
        name = str(relationship.get("name") or fallback_name or relationship_id)
        _put(
            cards,
            _card(
                StatusCardType.PLOT,
                f"关系：{_shorten(name, 32)}",
                relationship,
                obj,
                f"{path}[{position}]",
                subject_id=relationship_id,
                card_id=f"plot_relationship_{_slug(relationship_id)}",
            ),
            replace=True,
        )


def _project_lifecycle_cards(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    values: Any,
    path: str,
    *,
    id_key: str,
    card_type: StatusCardType,
    prefix: str,
) -> None:
    for position, value in enumerate(values if isinstance(values, list) else []):
        if not isinstance(value, dict):
            continue
        subject_id = str(value.get(id_key) or "").strip()
        if not subject_id:
            continue
        name = str(value.get("name") or value.get("volume_goal") or subject_id)
        _put(
            cards,
            _card(
                card_type,
                name,
                value,
                obj,
                f"{path}[{position}]",
                subject_id=subject_id,
                card_id=f"{card_type.value}_{prefix}_{_slug(subject_id)}",
            ),
            replace=True,
        )


def _project_agenda_cards(cards: dict[str, StatusCard], obj: AuthObject, values: Any) -> None:
    type_map = {
        "character": StatusCardType.CHARACTER,
        "creature": StatusCardType.CHARACTER,
        "faction": StatusCardType.FACTION,
        "ecology": StatusCardType.SCENE,
    }
    for position, agenda in enumerate(values if isinstance(values, list) else []):
        if not isinstance(agenda, dict):
            continue
        agenda_id = str(agenda.get("agenda_id") or "").strip()
        subject_id = str(agenda.get("subject_id") or agenda_id).strip()
        if not agenda_id or not subject_id:
            continue
        card_type = type_map.get(str(agenda.get("subject_type") or ""), StatusCardType.PLOT)
        name = str(agenda.get("name") or agenda.get("independent_goal") or subject_id)
        _put(
            cards,
            _card(
                card_type,
                f"议程：{_shorten(name, 28)}",
                agenda,
                obj,
                f"story_room.entity_agendas[{position}]",
                subject_id=subject_id,
                card_id=f"{card_type.value}_agenda_{_slug(agenda_id)}",
            ),
            replace=True,
        )


def _project_transient_cards(cards: dict[str, StatusCard], obj: AuthObject, values: Any) -> None:
    type_map = {
        "character": StatusCardType.CHARACTER,
        "creature": StatusCardType.CHARACTER,
        "faction": StatusCardType.FACTION,
        "item": StatusCardType.ITEM,
        "scene": StatusCardType.SCENE,
        "ecology": StatusCardType.SCENE,
        "clue": StatusCardType.PLOT,
    }
    for position, asset in enumerate(values if isinstance(values, list) else []):
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_id:
            continue
        card_type = type_map.get(str(asset.get("asset_type") or ""), StatusCardType.PLOT)
        name = str(asset.get("name") or asset.get("purpose") or asset_id)
        _put(
            cards,
            _card(
                card_type,
                name,
                asset,
                obj,
                f"story_room.transient_assets[{position}]",
                subject_id=asset_id,
                card_id=f"{card_type.value}_transient_{_slug(asset_id)}",
            ),
            replace=True,
        )


def _project_map_cards(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    values: Any,
    path: str,
    *,
    id_key: str,
    prefix: str,
) -> None:
    faction_maps: dict[str, list[str]] = {}
    for position, location in enumerate(values if isinstance(values, list) else []):
        if not isinstance(location, dict):
            continue
        location_id = str(location.get(id_key) or "").strip()
        name = str(location.get("name") or location_id).strip()
        if not location_id or not name:
            continue
        _put(
            cards,
            _card(
                StatusCardType.SCENE,
                name,
                location,
                obj,
                f"{path}[{position}]",
                subject_id=location_id,
                card_id=f"scene_{prefix}_{_slug(location_id)}",
            ),
            replace=True,
        )
        faction_values = (
            location.get("controlling_faction_ids") or location.get("controlling_factions") or []
        )
        if isinstance(faction_values, list):
            for faction in faction_values:
                faction_id = str(faction).strip()
                if faction_id:
                    faction_maps.setdefault(faction_id, []).append(location_id)
    for faction_id, map_ids in faction_maps.items():
        _put(
            cards,
            _card(
                StatusCardType.FACTION,
                faction_id,
                {"faction_id": faction_id, "controlled_or_influenced_maps": map_ids},
                obj,
                path,
                subject_id=faction_id,
                card_id=f"faction_{_slug(faction_id)}",
            ),
        )


def _project_char(cards: dict[str, StatusCard], obj: AuthObject, content: dict[str, Any]) -> None:
    characters = content.get("characters")
    relationships = (
        content.get("relationships") if isinstance(content.get("relationships"), list) else []
    )
    knowledge = (
        content.get("knowledge_boundaries")
        if isinstance(content.get("knowledge_boundaries"), list)
        else []
    )
    if isinstance(characters, list):
        for position, character in enumerate(characters):
            if not isinstance(character, dict):
                continue
            name = str(character.get("name") or character.get("id") or "").strip()
            if not name:
                continue
            character_id = str(character.get("id") or _slug(name))
            related = [
                item
                for item in (relationships or [])
                if isinstance(item, dict)
                and character_id in {str(item.get("from_id")), str(item.get("to_id"))}
            ]
            bounded_facts = [
                item
                for item in (knowledge or [])
                if isinstance(item, dict)
                and character_id
                in {
                    *[str(value) for value in (item.get("known_by") or [])],
                    *[str(value) for value in (item.get("unknown_to") or [])],
                }
            ]
            payload = {**character, "relationships": related, "knowledge_boundaries": bounded_facts}
            _put(
                cards,
                _card(
                    StatusCardType.CHARACTER,
                    name,
                    payload,
                    obj,
                    f"characters[{position}]",
                    subject_id=character_id,
                    card_id=f"character_{_slug(character_id)}",
                ),
            )

    boss = content.get("tier1_boss")
    if isinstance(boss, dict):
        name = str(boss.get("name") or "主要对手")
        _put(cards, _card(StatusCardType.CHARACTER, name, boss, obj, "tier1_boss"))
    _project_named_list(
        cards, StatusCardType.FACTION, content.get("tier2_factions"), obj, "tier2_factions"
    )
    _project_named_list(
        cards, StatusCardType.FACTION, content.get("gray_forces"), obj, "gray_forces"
    )


def _project_reg(
    cards: dict[str, StatusCard],
    obj: AuthObject,
    content: dict[str, Any],
    object_id: str,
) -> None:
    label = next((name for suffix, name in _RULE_NAMES.items() if suffix in object_id), "规则体系")
    _put(
        cards,
        _card(
            StatusCardType.RULE,
            label,
            content,
            obj,
            "root",
            card_id=f"rule_{_slug(label)}",
        ),
    )

    equipment = content.get("equipment_interface")
    if equipment:
        if isinstance(equipment, list):
            _project_named_list(cards, StatusCardType.ITEM, equipment, obj, "equipment_interface")
        else:
            _put(
                cards,
                _card(
                    StatusCardType.ITEM,
                    "装备与道具体系",
                    equipment,
                    obj,
                    "equipment_interface",
                    card_id="item_equipment_interface",
                ),
            )


def _project_named_list(
    cards: dict[str, StatusCard],
    card_type: StatusCardType,
    values: Any,
    obj: AuthObject,
    path: str,
) -> None:
    if not isinstance(values, list):
        return
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            continue
        name = value.get("name") or value.get("title") or value.get("id")
        if not name:
            continue
        _put(cards, _card(card_type, str(name), value, obj, f"{path}[{position}]"))


def _card(
    card_type: StatusCardType,
    name: str,
    payload: Any,
    obj: AuthObject,
    path: str,
    *,
    subject_id: str | None = None,
    card_id: str | None = None,
) -> StatusCard:
    return StatusCard(
        card_id=card_id or f"{card_type.value}_{_slug(name)}",
        card_type=card_type,
        card_name=name,
        subject_id=subject_id or _slug(name),
        summary=_summary(payload),
        current_state=_compact(payload),
        constraints=_constraints(payload),
        source_refs=[
            SourceRef(
                authority=obj.object_type.value,
                object_id=obj.object_id,
                version=obj.version,
                path=path,
                evidence="初始化权威产物的可重建阅读投影",
            )
        ],
        source_version=max(1, obj.version),
    )


def _put(cards: dict[str, StatusCard], card: StatusCard, *, replace: bool = False) -> None:
    if replace or card.card_id not in cards:
        cards[card.card_id] = card


def _summary(value: Any) -> str:
    preferred = (
        "summary",
        "description",
        "event_goal",
        "volume_promise",
        "identity",
        "role",
        "ideology",
        "main_promise",
    )
    if isinstance(value, dict):
        parts = [str(value[key]).strip() for key in preferred if value.get(key)]
        if parts:
            return _shorten("；".join(parts[:2]), 180)
        for item in value.values():
            if isinstance(item, str) and item.strip():
                return _shorten(item.strip(), 180)
    return _shorten(str(value), 180)


def _constraints(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    result: list[str] = []
    for key in ("forbidden_changes", "forbidden_points", "forbidden_zones", "taboo_words"):
        items = value.get(key)
        if isinstance(items, list):
            result.extend(_shorten(str(item), 180) for item in items[:6])
    return result[:8]


def _compact(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _shorten(value, 260)
    if depth >= 3:
        if isinstance(value, (dict, list)):
            return _shorten(str(value), 260)
        return value
    if isinstance(value, dict):
        return {
            str(key): _compact(item, depth + 1)
            for key, item in list(value.items())[:8]
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_compact(item, depth + 1) for item in value[:6]]
    return value


def _protagonist_name(main_promise: str) -> str | None:
    match = re.search(
        r"(?:学生|少年|青年|主角|名为)([\u4e00-\u9fff]{2,4})(?=在|是|，|。)", main_promise
    )
    return match.group(1) if match else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value).strip("_")
    return slug[:80] or "unnamed"


def _shorten(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"
