"""ContextCompiler、强类型状态卡和知识边界测试。"""

from __future__ import annotations

from pathlib import Path

from novelwb.core.constants import AuthObjectType, StatusCardType
from novelwb.core.schemas.domain_models import (
    AuthObject,
    CardPatch,
    CharacterKnowledge,
    EventDraft,
    ObservedDelta,
    RevelationGate,
    SourceRef,
    StateSnapshot,
    StatusCard,
    StatusCardIndex,
)
from novelwb.engine.context_compiler import ContextCompiler
from novelwb.engine.hard_lint import HardLintEngine, LintContext
from novelwb.engine.status_card_projector import project_initial_status_cards
from novelwb.storage.context_store import ContextStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.timeutil import utcnow


def _auth(object_type: AuthObjectType, content: dict, version: int = 1) -> AuthObject:
    now = utcnow()
    return AuthObject(
        object_id=f"obj_{object_type.value.lower()}",
        project_id="test_proj",
        object_type=object_type,
        version=version,
        content=content,
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_1",
    )


def _card(card_id: str, card_type: StatusCardType, name: str) -> StatusCard:
    return StatusCard(
        card_id=card_id,
        card_type=card_type,
        card_name=name,
        subject_id=card_id,
        current_state=f"{name}的当前状态",
        source_refs=[SourceRef(authority="REG", path=card_id, version=1)],
    )


def test_legacy_status_cards_are_normalized_to_typed_models():
    snapshot = StateSnapshot.model_validate({
        "snapshot_key": "pre_evt_1",
        "reading_focus": [{
            "card_type": "人物卡",
            "card_id": "char_001",
            "why_needed": "本事件出场",
            "priority": "高",
        }],
        "status_cards": {
            "character_cards": [{
                "card_id": "char_001",
                "card_name": "林深",
                "role": "主角",
                "current_state": "右臂受伤",
                "source": "CHAR.character_states",
            }],
        },
    })

    card = snapshot.status_cards["character_cards"][0]
    assert card.card_type == StatusCardType.CHARACTER
    assert card.attributes["role"] == "主角"
    assert card.source_refs[0].authority == "legacy"
    assert snapshot.reading_focus[0].priority.value == "high"


def test_context_compiler_selects_relevant_cards_and_tracks_omissions():
    relevant = _card("faction_red", StatusCardType.FACTION, "赤霄盟")
    irrelevant = _card("scene_snow", StatusCardType.SCENE, "北境雪原")
    compiler = ContextCompiler(token_budget=8000, cards_per_type=2)

    package = compiler.compile_event(
        event_id="evt_001",
        event_slot={
            "slot_id": "evt_001",
            "event_goal": "赤霄盟突袭港口，主角必须阻止货仓被焚",
            "result_target": "确认赤霄盟的真实目标",
            "forbidden_delta": ["不得提前揭示北境王庭秘密"],
        },
        auth_objects=[
            _auth(AuthObjectType.BIBLE, {
                "rules": {"power_cost": "使用能力必须付出代价"},
                "geography": {"港口": "潮汐港"},
                "unrelated_history": "远古纪年" * 500,
            }, version=3),
            _auth(AuthObjectType.REG, {"factions": ["赤霄盟", "北境王庭"]}, version=2),
        ],
        card_index=StatusCardIndex(cards=[relevant, irrelevant]),
    )

    selected_ids = [item.card.card_id for item in package.selected_cards]
    assert "faction_red" in selected_ids
    assert "scene_snow" not in selected_ids
    assert package.source_versions == {"BIBLE:obj_bible": 3, "REG:obj_reg": 2}
    assert package.fingerprint
    assert package.estimated_tokens <= package.token_budget
    assert any(item.source_id == "scene_snow" for item in package.omitted)

    rendered = compiler.render_input_context(package)
    assert rendered["context_meta"]["fingerprint"] == package.fingerprint
    assert rendered["char_content"]["status_cards"]["faction_cards"][0]["card_id"] == "faction_red"


def test_context_compiler_omits_full_story_room_and_event_table_when_slice_exists():
    compiler = ContextCompiler(token_budget=8000)
    package = compiler.compile_event(
        event_id="evt_001",
        event_slot={
            "slot_id": "evt_001",
            "event_goal": "完成考核",
            "chapter_design": {
                "reading_assets": {
                    "character_cards": [{"character_id": "char_1", "name": "江辰"}],
                    "locations": [{"location_id": "loc_exam", "name": "考核台"}],
                },
            },
        },
        auth_objects=[_auth(AuthObjectType.CONTRACT, {
            "volume_id": "vol_001",
            "event_slots": [{"slot_id": f"evt_{index:03d}"} for index in range(30)],
            "story_room": {"volume_cast_cards": [{"character_id": f"char_{index}"} for index in range(30)]},
            "volume_promise": "赢下考核",
        })],
    )

    omitted_ids = {item.source_id for item in package.omitted}
    assert "CONTRACT.obj_contract.event_slots" in omitted_ids
    assert "CONTRACT.obj_contract.story_room" in omitted_ids
    selected_paths = {
        item.path for item in [*package.protected_sources, *package.selected_sources]
    }
    assert "event_slots" not in selected_paths
    assert "story_room" not in selected_paths
    assert "volume_promise" in selected_paths


def test_context_store_merges_touched_cards_without_deleting_untouched(tmp_path: Path):
    layout = WorkspaceLayout(tmp_path / "workspace", "test_proj")
    store = ContextStore(layout)
    original = StatusCardIndex(cards=[
        _card("plot_a", StatusCardType.PLOT, "旧线索"),
        _card("scene_b", StatusCardType.SCENE, "旧场景"),
    ])
    from novelwb.utils.io_atomic import atomic_write_json
    atomic_write_json(layout.status_card_index_path, original.model_dump(mode="json"))

    updated_card = _card("plot_a", StatusCardType.PLOT, "旧线索")
    updated_card = updated_card.model_copy(update={"current_state": "本事件确认了新证据"})
    delta = ObservedDelta(
        state_after=StateSnapshot(
            snapshot_key="post_evt_2",
            event_id="evt_2",
            status_cards={"plot_cards": [updated_card]},
        ),
        result_state_summary="线索推进",
        card_updates={"plot_cards": [CardPatch(
            patch_id="patch_plot_a",
            card_id="plot_a",
            card_type=StatusCardType.PLOT,
            changed_fields=["current_state"],
            card=updated_card,
            evidence=["b001：主角从账本中确认了接头时间"],
        )]},
    )

    index = store.apply_event_delta(delta, "evt_2")
    by_id = {card.card_id: card for card in index.cards}
    assert set(by_id) == {"plot_a", "scene_b"}
    assert by_id["plot_a"].current_state == "本事件确认了新证据"
    assert by_id["plot_a"].last_touched_event_id == "evt_2"
    assert by_id["plot_a"].source_version == 2


def test_initial_status_cards_cover_navigation_types_and_preserve_event_cards(tmp_path: Path):
    artifacts = [
        _auth(AuthObjectType.BIBLE, {
            "main_promise": "普通学生江辰在高武世界用升级系统一路横推。",
            "protagonist_core": {"want": "成为最强武者"},
            "geography": {"key_locations": [{"name": "临海三中", "description": "故事起点"}]},
            "factions": [{"name": "天道武院", "ideology": "实力优先"}],
            "taboo_words": ["套娃阴谋"],
        }),
        _auth(AuthObjectType.REG, {
            "levels": ["武徒", "武者", "武师"],
            "equipment_interface": {"common": "制式战刀"},
        }),
        _auth(AuthObjectType.CONTRACT, {
            "volume_id": "vol_001",
            "title": "一拳成名",
            "volume_promise": "夺得全市第一",
            "event_slots": [{
                "slot_id": "evt_vol1_001",
                "event_goal": "江辰在气血测试中激活系统",
                "forbidden_changes": ["不得暴露系统来源"],
            }],
            "motif_arc": [{"motif": "气血检测器", "stage_1_meaning": "打脸见证"}],
        }),
    ]
    cards = project_initial_status_cards(artifacts)
    assert {card.card_type for card in cards} == set(StatusCardType)
    assert any(card.card_name == "江辰" for card in cards)
    assert any(card.card_id == "plot_evt_vol1_001" for card in cards)

    layout = WorkspaceLayout(tmp_path / "workspace", "test_proj")
    store = ContextStore(layout)
    first = store.seed_authority_cards(cards, "run_init")
    assert len(first.cards) == len(cards)

    event_card = _card("plot_event", StatusCardType.PLOT, "事件后状态").model_copy(
        update={"last_touched_event_id": "evt_9"}
    )
    from novelwb.utils.io_atomic import atomic_write_json
    atomic_write_json(
        layout.status_card_index_path,
        StatusCardIndex(cards=[*cards, event_card]).model_dump(mode="json"),
    )
    second = store.seed_authority_cards(cards[:-1], "run_reinit")
    assert any(card.card_id == "plot_event" for card in second.cards)


def test_cast_authority_projects_each_character_with_relationship_context():
    cast = _auth(AuthObjectType.CHAR, {
        "characters": [
            {"id": "char_hero", "name": "Hero", "role": "protagonist"},
            {"id": "char_friend", "name": "Friend", "role": "partner"},
            {"id": "char_rival", "name": "Rival", "role": "early opponent"},
        ],
        "relationships": [{
            "from_id": "char_hero",
            "to_id": "char_friend",
            "current_state": "allies",
            "forbidden_jump": "no unexplained betrayal",
        }],
        "knowledge_boundaries": [{
            "fact": "system source",
            "known_by": ["char_hero"],
            "unknown_to": ["char_friend", "char_rival"],
            "reveal_condition": "after event 10",
        }],
    })

    cards = project_initial_status_cards([cast])

    assert {card.subject_id for card in cards} == {"char_hero", "char_friend", "char_rival"}
    friend = next(card for card in cards if card.subject_id == "char_friend")
    assert friend.current_state["relationships"][0]["current_state"] == "allies"
    assert friend.current_state["knowledge_boundaries"][0]["fact"] == "system source"


def test_story_room_projects_outline_maps_volume_cast_and_scene_assets():
    longline = _auth(AuthObjectType.CONTRACT, {
        "story_room": {
            "master_story_design": {"story_engine": "从校内考核走向全国竞赛"},
            "major_foreshadowing": [{"hook_id": "hook_system", "purpose": "系统来源"}],
            "character_growth_arcs": [{"character_id": "char_hero", "name": "江辰"}],
            "ensemble_relationship_index": [{
                "relationship_id": "rel_hero_rival",
                "name": "江辰与对手",
                "character_ids": ["char_hero", "char_rival"],
                "story_function": "竞争迫使双方改变选择",
            }],
            "ensemble_relationship_arcs": [{
                "relationship_id": "rel_hero_rival",
                "name": "江辰与对手",
                "character_ids": ["char_hero", "char_rival"],
                "turning_stages": [{"stage_id": "stage_1", "event": "首次正面对抗"}],
                "end_dynamic": "彼此承认",
            }],
            "narrative_line_registry": [{"line_id": "line_rivalry", "name": "选拔暗线"}],
            "key_item_arcs": [{"item_id": "item_badge", "name": "旧徽章"}],
            "major_set_piece_seeds": [{"set_piece_id": "set_final", "name": "终场混战"}],
            "asset_lifecycle_policy": {"transient": "用后退休"},
            "major_map_system": {
                "major_regions": [{
                    "map_id": "map_linhai",
                    "name": "临海城",
                    "controlling_factions": ["city_guard"],
                }],
            },
        },
    })
    volume = _auth(AuthObjectType.CONTRACT, {
        "story_room": {
            "volume_story_engine": {"volume_center": "赢下校内选拔"},
            "volume_foreshadowing": [{"hook_id": "hook_system", "purpose": "系统来源加深"}],
            "volume_character_arcs": [
                {"character_id": "char_hero", "start_state": "不受重视"},
                {"character_id": "char_rival", "start_state": "轻视江辰"},
            ],
            "volume_cast_cards": [
                {"character_id": "char_hero", "name": "江辰", "story_status": "主角"},
                {"character_id": "char_rival", "name": "赵铁心", "story_status": "对手"},
            ],
            "relationship_tracks": [{
                "relationship_id": "rel_hero_rival",
                "name": "江辰与对手",
                "character_ids": ["char_hero", "char_rival"],
                "turn_slots": ["evt_9"],
                "end_dynamic": "从轻视转为警惕",
            }],
            "volume_line_ledger": [{
                "line_id": "line_rivalry", "volume_goal": "查清选拔作弊",
            }],
            "entity_agendas": [{
                "agenda_id": "agenda_board",
                "subject_id": "school_board",
                "subject_type": "faction",
                "independent_goal": "压住作弊传闻",
            }],
            "key_item_tracks": [{"item_id": "item_badge", "state": "被误认"}],
            "set_piece_plans": [{"set_piece_id": "set_final", "event_slot_ids": ["evt_9"]}],
            "transient_assets": [{
                "asset_id": "clue_score_sheet", "asset_type": "clue", "purpose": "一次性分数线索",
            }],
            "volume_map_system": {
                "locations": [{
                    "location_id": "loc_exam",
                    "name": "校内考核台",
                    "controlling_faction_ids": ["school_board"],
                }],
            },
            "scene_assets": [{"scene_id": "scene_test", "name": "气血复测"}],
        },
    })

    cards = project_initial_status_cards([longline, volume])
    by_id = {card.card_id: card for card in cards}

    assert "plot_master_story_design" in by_id
    assert by_id["plot_hook_hook_system"].current_state["purpose"] == "系统来源加深"
    assert "scene_major_map_map_linhai" in by_id
    assert "scene_location_loc_exam" in by_id
    assert "scene_asset_scene_test" in by_id
    assert "faction_city_guard" in by_id
    assert "faction_school_board" in by_id
    assert "plot_line_line_rivalry" in by_id
    assert by_id["plot_line_line_rivalry"].current_state["volume_goal"] == "查清选拔作弊"
    assert "plot_relationship_rel_hero_rival" in by_id
    assert (
        by_id["plot_relationship_rel_hero_rival"].current_state["end_dynamic"]
        == "从轻视转为警惕"
    )
    assert "item_arc_item_badge" in by_id
    assert "item_track_item_badge" in by_id
    assert "plot_set_piece_set_final" in by_id
    assert "faction_agenda_agenda_board" in by_id
    assert "plot_transient_clue_score_sheet" in by_id
    assert "rule_asset_lifecycle" in by_id
    assert by_id["character_char_hero"].current_state["volume_arc"]["start_state"] == "不受重视"


def test_master_tail_indexes_project_preview_cards_before_full_entries():
    longline = _auth(AuthObjectType.CONTRACT, {
        "story_room": {
            "narrative_line_index": [{
                "line_id": "line_main",
                "name": "主线索引",
                "story_function": "推动全书核心因果",
            }],
            "key_item_index": [{
                "item_id": "item_badge",
                "name": "旧徽章索引",
                "selection_reason": "跨阶段证明身份",
            }],
            "major_set_piece_index": [{
                "set_piece_id": "set_final",
                "name": "终场索引",
                "spatial_requirement": "多层竞技场",
            }],
        },
    })

    by_id = {card.card_id: card for card in project_initial_status_cards([longline])}

    assert by_id["plot_line_line_main"].current_state["story_function"] == "推动全书核心因果"
    assert by_id["item_arc_item_badge"].current_state["selection_reason"] == "跨阶段证明身份"
    assert by_id["plot_set_piece_set_final"].current_state["spatial_requirement"] == "多层竞技场"


def test_hard_lint_blocks_evidence_free_patch_and_unauthorized_reveal():
    secret = StatusCard(
        card_id="plot_secret",
        card_type=StatusCardType.PLOT,
        card_name="幕后身份",
        current_state="身份仍未公开",
        character_knowledge={
            "char_a": CharacterKnowledge(blind_spots=["幕后人身份"]),
        },
        revelation_gate=RevelationGate(
            required_hint_ids=["hint_1", "hint_2"],
            satisfied_hint_ids=["hint_1"],
            allowed_knowers=["char_a"],
        ),
    )
    delta = ObservedDelta(
        state_after=StateSnapshot(snapshot_key="post_evt_3", event_id="evt_3"),
        result_state_summary="错误揭秘",
        card_updates={"plot_cards": [CardPatch(
            patch_id="patch_secret",
            card_id="plot_secret",
            card_type=StatusCardType.PLOT,
            card=secret,
            evidence=[],
            revealed_to=["char_b"],
        )]},
    )
    report = HardLintEngine().run(LintContext(
        run_id="run_3",
        event_id="evt_3",
        draft=EventDraft(event_id="evt_3", run_id="run_3", draft_text="测试正文"),
        pre_snapshot=StateSnapshot(snapshot_key="pre_evt_3", event_id="evt_3"),
        observed_delta=delta,
        enabled_rule_groups=["G"],
    ))

    assert report.passed is False
    messages = "\n".join(report.violated_forbidden)
    assert "缺少正文证据" in messages
    assert "知识边界越权" in messages
    assert "揭秘前置伏笔不足" in messages
