"""图E/5/S 集成测试（MockReplayAdapter）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from novelwb.adapters.llm.mock_replay import MockReplayAdapter
from novelwb.core.constants import ChapterIntent
from novelwb.core.schemas.domain_models import ChapterSpec, EventDraft, ObservedDelta, StateSnapshot
from novelwb.engine.orchestrator import Orchestrator, OrchestratorConfig
from novelwb.engine.prose_quality import ProseQualityEvaluator
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_event_id, new_run_id


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    ws = tmp_path / "workspace"
    src = Path(__file__).parent.parent / "src" / "novelwb"
    cfg = OrchestratorConfig(
        workspace_root=ws,
        project_id="test_proj",
        prompts_dir=src / "prompts",
        core_dir=src / "core",
        llm_adapter=MockReplayAdapter(default_response='{"_raw": "ok"}'),
    )
    return Orchestrator(cfg)


def test_run_event_pipeline_returns_success(tmp_path: Path):
    orch = _make_orchestrator(tmp_path)
    run_id = new_run_id()
    event_id = new_event_id()
    draft = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text="这是一段测试草稿文本，用于验证事件流水线基本流程。" * 5,
        blocks=[],
        word_count=100,
    )
    result = orch.run_event_pipeline(run_id, event_id, draft)
    assert isinstance(result, dict)
    assert "success" in result


def test_run_event_pipeline_does_not_commit_invalid_observed_delta(tmp_path: Path):
    orch = _make_orchestrator(tmp_path)
    run_id = new_run_id()
    event_id = new_event_id()
    draft = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text="invalid structured delta must not be committed",
        blocks=[],
        word_count=46,
    )

    result = orch.run_event_pipeline(run_id, event_id, draft)

    assert result["success"] is False
    assert result["event"].aborted is True
    assert orch._events_store.load_optional(event_id) is None
    assert orch._snapshots_store.load_latest() is None


def test_graph_e_extract_retries_schema_invalid_json_and_inherits_state(tmp_path: Path):
    from novelwb.adapters.llm.base import LLMResponse
    from novelwb.core.schemas.domain_models import LLMCallRecord
    from novelwb.utils.timeutil import utcnow

    class _ScriptedLLM(MockReplayAdapter):
        def __init__(self, scripted: list[str]):
            super().__init__()
            self.scripted = scripted
            self.calls = 0
            self.prompts: list[str] = []

        def call(self, prompt, **kwargs):
            self.prompts.append(prompt)
            index = self.calls
            self.calls += 1
            text = self.scripted[min(index, len(self.scripted) - 1)]
            record = LLMCallRecord(
                call_id=f"call_{index}",
                step_id=kwargs.get("step_id", ""),
                prompt_key=kwargs.get("prompt_key", ""),
                prompt_version=kwargs.get("prompt_version", "1"),
                prompt_hash=kwargs.get("prompt_hash", ""),
                model="fake",
                input_tokens=10,
                output_tokens=10,
                latency_ms=1,
                cached=False,
                timestamp=utcnow(),
            )
            return LLMResponse(text=text, record=record)

    orch = _make_orchestrator(tmp_path)
    event_id = "evt_extract_retry"
    run_id = "run_extract_retry"
    invalid = {"state_after": {"snapshot_key": f"post_{event_id}"}}
    valid = {
        "state_after": {
            "snapshot_key": f"post_{event_id}",
            "resources": {"spirit_stones": 2},
            "ability_boundary": ["新能力"],
            "timeline_events": [{"event": "新事件"}],
        },
        "result_state_summary": "主角获得新能力并消耗资源",
    }
    scripted = _ScriptedLLM([
        json.dumps(invalid, ensure_ascii=False),
        json.dumps(valid, ensure_ascii=False),
    ])
    orch._deps.llm = scripted
    draft = EventDraft(
        event_id=event_id,
        run_id=run_id,
        draft_text="主角付出代价后获得新能力。",
    )
    before = StateSnapshot(
        snapshot_key=f"pre_{event_id}",
        event_id=event_id,
        resources={"spirit_stones": 5, "key_items": ["旧物"]},
        ability_boundary=["旧能力"],
        timeline_events=[{"event": "旧事件"}],
    )

    delta = orch._graph_e._run_extract(run_id, event_id, draft, before, None)

    assert scripted.calls == 2
    assert scripted.prompts[0] != scripted.prompts[1]
    assert "result_state_summary" in scripted.prompts[1]
    assert "重试标识" in scripted.prompts[1]
    assert delta.result_state_summary == "主角获得新能力并消耗资源"
    assert delta.state_after.resources == {
        "spirit_stones": 2,
        "key_items": ["旧物"],
    }
    assert delta.state_after.ability_boundary == ["旧能力", "新能力"]
    assert delta.state_after.timeline_events == [
        {"event": "旧事件"},
        {"event": "新事件"},
    ]


def test_graph_e_manual_review_stops_before_automatic_prose_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.schemas.domain_models import DiffReport

    orch = _make_orchestrator(tmp_path)
    event_id = "evt_manual_reconcile"
    run_id = "run_manual_reconcile"
    draft = EventDraft(
        event_id=event_id,
        run_id=run_id,
        draft_text="人工已经审核过的正文。",
    )
    before = StateSnapshot(snapshot_key=f"pre_{event_id}")
    delta = ObservedDelta(
        state_after=StateSnapshot(snapshot_key=f"post_{event_id}"),
        result_state_summary="状态已变化",
    )
    report = DiffReport(
        event_id=event_id,
        run_id=run_id,
        passed=False,
        violated_forbidden=["提前揭示了受保护事实"],
    )
    monkeypatch.setattr(orch._deps.lint_engine, "run", lambda ctx: report)
    monkeypatch.setattr(
        orch._graph_e,
        "_run_fix",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("人工审核路径不得自动修改正文")
        ),
    )

    actual_report, actual_draft, attempts, aborted, reason = (
        orch._graph_e._reconcile_loop(
            run_id,
            event_id,
            draft,
            before,
            delta,
            None,
            None,
            auto_repair=False,
        )
    )

    assert actual_report is report
    assert actual_draft.draft_text == draft.draft_text
    assert attempts == 0
    assert aborted is True
    assert "提前揭示了受保护事实" in reason


def test_graph4_rejects_legacy_single_block_write_shape():
    from novelwb.engine.graphs.graph_4 import Graph4

    ok, reason = Graph4._validate_blocks_write_output(
        event_id="evt_vol1_001",
        block_plan=[
            {"block_id": "b001", "chars_hint": 1400},
            {"block_id": "b002", "chars_hint": 1400},
            {"block_id": "b003", "chars_hint": 800},
        ],
        write_parsed={
            "block_id": "b002",
            "text": "【块－b002】\n下蹲借力换配案始落罐滴柱端凝注流细核底剩损暗涌浅分停废斗涌响。\n",
        },
    )

    assert ok is False
    assert "full_text" in reason


def test_graph4_migrates_legacy_blocks_to_marker_free_event_text():
    from novelwb.engine.graphs.graph_4 import Graph4

    parsed = {
        "blocks_text": [
            {
                "block_id": "b001",
                "text": "【块－b001】\n林深靠在墙角，油灯在桌面上摇晃。" * 30,
            },
            {
                "block_id": "b002",
                "text": "林深把铜纽扣按进石砖，最后的共鸣指向城西。" * 30,
            },
        ],
    }
    normalized = Graph4._normalize_blocks_write_output(parsed)
    ok, reason = Graph4._validate_blocks_write_output(
        event_id="evt_vol1_021",
        block_plan=[
            {"block_id": "b001", "chars_hint": 500},
            {"block_id": "b002", "chars_hint": 500},
        ],
        write_parsed=normalized,
    )

    assert ok is True, reason
    assert "【块" not in normalized["full_text"]
    assert [item["scene_id"] for item in normalized["scene_receipts"]] == ["b001", "b002"]


def test_graph4_normalizes_scene_plan_without_per_scene_word_quotas():
    from novelwb.engine.graphs.graph_4 import Graph4

    plans = Graph4._normalize_block_plan(
        [
            {"block_id": "b001", "block_intent": "Advance", "chars_hint": 200},
            {"block_id": "b002", "block_intent": "Settle", "chars_hint": 100},
        ],
        {"block_count": 2, "total_chars": 3600},
        {"event_goal": "完成第一次公开反击"},
    )

    assert len(plans) == 2
    assert [plan["scene_id"] for plan in plans] == ["b001", "b002"]
    assert all("chars_hint" not in plan for plan in plans)
    assert all(len(plan["beat_chain"]) >= 5 for plan in plans)
    assert all("state_card_focus" in plan for plan in plans)


def test_graph4_builds_layered_fallback_plan_when_model_plan_is_missing():
    from novelwb.engine.graphs.graph_4 import Graph4

    plans = Graph4._normalize_block_plan(
        [],
        {"scene_count_hint": 3, "total_chars": 3600},
        {
            "event_goal": "主角在考核前获得第一项系统任务",
            "key_deliverables": ["任务落地", "对手施压"],
        },
    )

    assert [plan["scene_id"] for plan in plans] == ["s001", "s002", "s003"]
    assert all("chars_hint" not in plan for plan in plans)
    assert all(plan["deliverables"] for plan in plans)


def test_graph4_rejects_event_prose_below_soft_coverage_floor():
    from novelwb.engine.graphs.graph_4 import Graph4

    short = "他向前走了一步。" * 35
    ok, reason = Graph4._validate_blocks_write_output(
        event_id="evt_short",
        block_plan=[{"block_id": "b001", "chars_hint": 1200}],
        write_parsed={"full_text": short, "scene_receipts": [{"scene_id": "b001"}]},
        budget_report={"soft_min_chars": 900},
    )

    assert ok is False
    assert "展开不足" in reason


def test_graph5_splits_continuous_event_text_by_natural_end_anchors():
    from novelwb.core.constants import ChapterIntent
    from novelwb.engine.graphs.graph_5 import Graph5

    first = "第一场压力逐步升级。人物终于作出决定。"
    second = "余波扩散到看台。新的命令从城中传来。"
    specs = [
        ChapterSpec(
            chapter_id="ch_1",
            chapter_index=1,
            chapter_intent=ChapterIntent.ADVANCE,
            start_anchor="第一场压力逐步升级。",
            end_anchor="人物终于作出决定。",
            estimated_chars=len(first),
        ),
        ChapterSpec(
            chapter_id="ch_2",
            chapter_index=2,
            chapter_intent=ChapterIntent.FORESHADOW,
            start_anchor="余波扩散到看台。",
            end_anchor="新的命令从城中传来。",
            estimated_chars=len(second),
        ),
    ]

    chapters = Graph5._split_chapter_texts(first + second, specs)

    assert chapters == {"ch_1": first, "ch_2": second}
    assert Graph5._valid_cut_anchors(first + second, specs) is True

    bad_specs = [specs[0].model_copy(update={"end_anchor": "正文中不存在的边界"}), specs[1]]
    assert Graph5._valid_cut_anchors(first + second, bad_specs) is False


def test_prose_quality_prefers_varied_prose_over_repeated_filler():
    evaluator = ProseQualityEvaluator(threshold=72)
    good = (
        "潮声从仓门底下漫进来。林深停住脚，先听见左侧铁链轻响，又看见窗纸上的影子缩了回去。"
        "他没有追，只把账页压在灯下。墨迹边缘尚未干透，第三行的船号却被人用指甲刮掉了一半。"
        "门外有人咳了一声。短促，克制。林深合上账本，借着搬木箱的动作让出通往后窗的路。"
        "等脚步真正越过门槛，他才抬眼：来人袖口沾着赤色盐霜，那不是港区会有的东西。"
    )
    repeated = ("就在这时，空气仿佛凝固，他心中一颤。" * 30)

    good_report = evaluator.evaluate(good, target_chars=180)
    repeated_report = evaluator.evaluate(repeated, target_chars=300)

    assert good_report.passed is True
    assert repeated_report.score < good_report.score
    assert repeated_report.metrics["repeated_shingle_ratio"] > 0.08
    assert repeated_report.issues

    too_short_report = evaluator.evaluate(good, target_chars=1200)
    assert too_short_report.passed is False
    assert too_short_report.metrics["length_ratio"] < 0.75


def test_run_event_pipeline_publishes_graphe_committed_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orch = _make_orchestrator(tmp_path)
    run_id = new_run_id()
    event_id = new_event_id()
    original = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text='{"block_id":"b002","text":"bad"}',
        blocks=[],
        word_count=32,
    )
    committed_text = "图E修复后的正文。" * 20
    delta = ObservedDelta(
        state_after=StateSnapshot(snapshot_key=f"post_{event_id}", result_state_summary="已修复"),
        result_state_summary="已修复",
    )
    event_out = SimpleNamespace(
        aborted=False,
        event_record=SimpleNamespace(draft_text=committed_text, blocks=[]),
        observed_delta=delta,
        diff_report=SimpleNamespace(passed=True),
        fix_attempts=1,
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr(orch._graph_e, "run", lambda inp: event_out)
    monkeypatch.setattr(orch, "_update_auth_from_event", lambda *args, **kwargs: None)

    def fake_graph5_run(inp):
        captured["draft_text"] = inp.draft.draft_text
        return SimpleNamespace(chapter_specs=[])

    monkeypatch.setattr(orch._graph_5, "run", fake_graph5_run)

    result = orch.run_event_pipeline(run_id, event_id, original)

    assert result["success"] is True
    assert captured["draft_text"] == committed_text
    assert result["draft"].draft_text == committed_text


def test_published_history_dedupes_rerun_by_chapter_index(tmp_path: Path):
    from novelwb.core.schemas.domain_models import ChapterCommitRecord
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    for chapter_id, chapter_index, text in [
        ("ch_bad_1", 1, "坏的第一章"),
        ("ch_good_1", 1, "新的第一章"),
        ("ch_good_2", 2, "第二章"),
    ]:
        record = ChapterCommitRecord(
            chapter_id=chapter_id,
            project_id="test_proj",
            chapter_index=chapter_index,
            chapter_intent=ChapterIntent.ADVANCE,
            text=text,
            word_count=len(text),
            committed_at=now,
            committed_by_run_id="run_1",
            source_event_ids=[f"evt_{chapter_index}"],
        )
        orch._publish_store.publish(record, text)

    assert orch._load_published_chapter_specs(before_chapter_index=1) == []
    before_second = orch._load_published_chapter_specs(before_chapter_index=2)
    assert [spec.chapter_id for spec in before_second] == ["ch_good_1"]
    assert orch._publish_store.chapter_count() == 2


def test_run_regression_returns_report(tmp_path: Path):
    orch = _make_orchestrator(tmp_path)
    run_id = new_run_id()
    result = orch.run_regression(run_id)
    assert "report" in result
    report = result["report"]
    assert hasattr(report, "passed")
    assert hasattr(report, "issues")


def test_story_room_validators_require_character_and_map_layers():
    from novelwb.engine.graphs.graph_2 import Graph2
    from novelwb.engine.graphs.graph_3 import Graph3

    book_room = {
        "master_story_design": {"story_engine": "成长与公开竞争"},
        "major_foreshadowing": [{"hook_id": "hook_1"}],
        "character_growth_arcs": [{"character_id": "char_1"}],
        "ensemble_relationship_arcs": [],
        "narrative_line_registry": [{"line_id": "line_main"}],
        "key_item_arcs": [],
        "major_set_piece_seeds": [],
        "asset_lifecycle_policy": {"transient": "用后退休"},
        "entity_autonomy_rules": ["角色按自己的目标行动"],
    }
    assert Graph2._valid_story_room(book_room) is True
    assert Graph2._valid_story_room({**book_room, "major_foreshadowing": []}) is False
    assert Graph2._valid_map_room({
        "major_map_system": {"major_regions": [{"map_id": "map_1"}]},
    }) is True
    assert Graph2._valid_map_room({
        "major_map_system": {"major_regions": [{"map_id": "map_1"}, {"map_id": "map_1"}]},
    }) is False

    volume_room = {
        "volume_story_engine": {"volume_center": "赢下第一次公开考核"},
        "volume_foreshadowing": [{"hook_id": "hook_1"}],
        "volume_character_arcs": [{"character_id": "char_1"}],
        "volume_cast_cards": [
            {"character_id": "char_1"},
            {"character_id": "char_2"},
        ],
        "relationship_tracks": [{
            "relationship_id": "rel_1_2",
            "character_ids": ["char_1", "char_2"],
            "turn_slots": ["evt_1"],
        }],
        "volume_line_ledger": [{"line_id": "line_main", "scheduled_movements": []}],
        "entity_agendas": [{"agenda_id": "agenda_1", "planned_actions": []}],
        "key_item_tracks": [],
        "set_piece_plans": [],
        "transient_assets": [],
    }
    assert Graph3._valid_volume_story_room(volume_room) is True
    assert Graph3._valid_volume_story_room(
        volume_room,
        master_relationship_pairs={"rel_1_2": ("char_1", "char_2")},
    ) is True
    assert Graph3._valid_volume_story_room(
        {
            **volume_room,
            "relationship_tracks": [{
                **volume_room["relationship_tracks"][0],
                "relationship_id": "rel_unregistered",
            }],
        },
        master_relationship_pairs={"rel_1_2": ("char_1", "char_2")},
    ) is False
    assert Graph3._valid_volume_story_room({**volume_room, "volume_cast_cards": []}) is False

    map_room = {
        "volume_map_system": {"locations": [{"location_id": "loc_1"}]},
        "scene_assets": [{"scene_id": "scene_1", "location_id": "loc_1"}],
    }
    assert Graph3._valid_volume_map_room(map_room) is True
    assert Graph3._valid_volume_map_room({
        **map_room,
        "scene_assets": [{"scene_id": "scene_1", "location_id": "missing"}],
    }) is False

    strict_map_room = {
        "volume_map_system": {
            "active_major_map_ids": ["map_1"],
            "locations": [{
                "location_id": "loc_1",
                "parent_map_id": "map_1",
                "scheduled_slots": ["evt_1"],
                "character_connections": [{"character_id": "char_1"}],
            }],
            "route_matrix": [],
            "map_and_character_progression": [{
                "event_slot_id": "evt_1",
                "location_id": "loc_1",
                "character_id": "char_1",
            }],
        },
        "scene_assets": [{
            "scene_id": "scene_1",
            "location_id": "loc_1",
            "suggested_slots": ["evt_1"],
        }],
    }
    assert Graph3._valid_volume_map_room(
        strict_map_room,
        story_room=volume_room,
        expected_slot_ids={"evt_1"},
        allowed_parent_map_ids={"map_1"},
    ) is True
    invalid_character_map = {
        **strict_map_room,
        "volume_map_system": {
            **strict_map_room["volume_map_system"],
            "locations": [{
                **strict_map_room["volume_map_system"]["locations"][0],
                "character_connections": [{"character_id": "missing"}],
            }],
        },
    }
    assert Graph3._valid_volume_map_room(
        invalid_character_map,
        story_room=volume_room,
        expected_slot_ids={"evt_1"},
        allowed_parent_map_ids={"map_1"},
    ) is False

    complete_room = {**volume_room, **map_room}
    designs = {
        "event_designs": [{
            "slot_id": "evt_1",
            "chapter_center": "完成报名",
            "reader_payoff": "主角获得参赛资格",
            "surface_goal": "在截止前提交报名材料",
            "ending_requirement": "报名成功并引来对手注意",
            "content_must_include": ["主角主动提交报名表"],
            "character_focus_ids": ["char_1"],
            "character_scene_goals": [{"character_id": "char_1", "scene_goal": "完成报名"}],
            "location_ids": ["loc_1"],
            "scene_asset_ids": ["scene_1"],
            "foreshadowing_ids": ["hook_1"],
            "relationship_ids": ["rel_1_2"],
            "relationship_actions": [{
                "relationship_id": "rel_1_2",
                "movement": "试探",
            }],
            "growth_actions": [{"character_id": "char_1", "growth_node": "主动争取"}],
            "foreshadow_actions": [{"hook_id": "hook_1", "action": "埋设"}],
        }],
    }
    assert Graph3._valid_event_designs(
        designs, story_room=complete_room, expected_slot_ids=["evt_1"],
    ) is True
    assert Graph3._valid_event_designs(
        designs, story_room=complete_room, expected_slot_ids=["evt_1", "evt_2"],
    ) is False
    invalid_ref = {
        "event_designs": [{**designs["event_designs"][0], "location_ids": ["missing"]}],
    }
    assert Graph3._valid_event_designs(
        invalid_ref, story_room=complete_room, expected_slot_ids=["evt_1"],
    ) is False
    invalid_relationship_ref = {
        "event_designs": [{
            **designs["event_designs"][0],
            "relationship_ids": ["missing"],
            "relationship_actions": [],
        }],
    }
    assert Graph3._valid_event_designs(
        invalid_relationship_ref,
        story_room=complete_room,
        expected_slot_ids=["evt_1"],
    ) is False


def test_volume_story_room_designs_merge_into_matching_event_slots():
    from novelwb.engine.graphs.graph_3 import Graph3

    plan = {
        "event_slots": [
            {"slot_id": "evt_1", "event_goal": "进入考场"},
            {"slot_id": "evt_2", "event_goal": "完成考核"},
        ]
    }
    Graph3._merge_event_designs(
        plan,
        {
            "volume_character_arcs": [
                {"character_id": "char_1", "start_state": "只求自保"},
                {"character_id": "char_2", "start_state": "暗中观察"},
            ],
            "volume_cast_cards": [
                {"character_id": "char_1", "name": "林野"},
                {"character_id": "char_2", "name": "考官"},
            ],
            "volume_foreshadowing": [
                {"hook_id": "hook_1", "purpose": "系统来源"},
            ],
            "relationship_tracks": [{
                "relationship_id": "rel_hero_examiner",
                "character_ids": ["char_1", "char_2"],
                "turn_slots": ["evt_2"],
                "end_dynamic": "从审视转为认可",
            }],
            "volume_map_system": {
                "locations": [
                    {
                        "location_id": "loc_exam",
                        "scheduled_slots": ["evt_2"],
                        "physical_layout": "三面看台围绕考核台",
                    },
                    {"location_id": "loc_home", "scheduled_slots": ["evt_1"]},
                ],
                "route_matrix": [
                    {
                        "from_location_id": "loc_home",
                        "to_location_id": "loc_exam",
                        "travel_time": "半个时辰",
                    }
                ],
                "map_and_character_progression": [
                    {
                        "event_slot_id": "evt_2",
                        "location_id": "loc_exam",
                        "character_id": "char_1",
                    }
                ],
            },
            "scene_assets": [
                {"scene_id": "scene_exam", "suggested_slots": ["evt_2"]},
            ],
            "event_designs": [
                {
                    "slot_id": "evt_2",
                    "chapter_center": "主角在限制下作出第一次主动选择",
                    "character_focus_ids": ["char_1"],
                    "location_ids": ["loc_exam"],
                    "scene_asset_ids": ["scene_exam"],
                    "foreshadowing_ids": ["hook_1"],
                    "relationship_ids": ["rel_hero_examiner"],
                }
            ]
        },
    )

    assert "chapter_design" not in plan["event_slots"][0]
    design = plan["event_slots"][1]["chapter_design"]
    assert design["chapter_center"].startswith("主角")
    assets = design["reading_assets"]
    assert [item["character_id"] for item in assets["character_cards"]] == ["char_1"]
    assert [item["location_id"] for item in assets["locations"]] == ["loc_exam"]
    assert assets["routes"][0]["travel_time"] == "半个时辰"
    assert assets["scene_assets"][0]["scene_id"] == "scene_exam"
    assert assets["foreshadowing"][0]["hook_id"] == "hook_1"
    assert assets["relationship_tracks"][0]["relationship_id"] == "rel_hero_examiner"


def test_volume_event_slots_require_unique_ids_and_chunk_without_loss():
    from novelwb.engine.graphs.graph_3 import Graph3

    slots = [
        {"slot_id": f"evt_{index:03d}", "event_goal": f"推进事件{index}"}
        for index in range(17)
    ]
    assert Graph3._usable_event_slots({"event_slots": slots}) == slots
    assert Graph3._usable_event_slots({
        "event_slots": [slots[0], {**slots[1], "slot_id": slots[0]["slot_id"]}],
    }) == []
    assert Graph3._usable_event_slots({
        "event_slots": [slots[0], {"event_goal": "缺少ID"}],
    }) == []

    chunks = Graph3._chunk_event_slots(slots)
    assert [len(chunk) for chunk in chunks] == [8, 8, 1]
    assert [slot for chunk in chunks for slot in chunk] == slots


def test_event_design_scope_excludes_unrelated_volume_assets():
    from novelwb.engine.graphs.graph_3 import Graph3

    story_room = {
        "volume_story_engine": {"volume_center": "完成选拔"},
        "volume_foreshadowing": [
            {"hook_id": "hook_1", "plant_slots": ["evt_1"], "reinforce_slots": [], "involved_character_ids": ["char_1"]},
            {"hook_id": "hook_2", "plant_slots": ["evt_2"], "reinforce_slots": [], "involved_character_ids": ["char_2"]},
        ],
        "volume_character_arcs": [
            {"character_id": "char_1", "key_choices": [{"event_slot_id": "evt_1"}]},
            {"character_id": "char_2", "key_choices": [{"event_slot_id": "evt_2"}]},
        ],
        "volume_cast_cards": [
            {"character_id": "char_1", "name": "江辰"},
            {"character_id": "char_2", "name": "远方对手"},
            {"character_id": "char_3", "name": "对手的盟友"},
        ],
        "relationship_tracks": [
            {
                "relationship_id": "rel_1_2",
                "character_ids": ["char_1", "char_2"],
                "turn_slots": ["evt_1"],
            },
            {
                "relationship_id": "rel_2_3",
                "character_ids": ["char_2", "char_3"],
                "turn_slots": ["evt_2"],
            },
        ],
        "volume_map_system": {
            "active_major_map_ids": ["map_1", "map_2"],
            "locations": [
                {"location_id": "loc_1", "scheduled_slots": ["evt_1"], "character_connections": [{"character_id": "char_1"}]},
                {"location_id": "loc_2", "scheduled_slots": ["evt_2"], "character_connections": [{"character_id": "char_2"}]},
            ],
            "route_matrix": [],
            "map_and_character_progression": [
                {"event_slot_id": "evt_1", "location_id": "loc_1", "character_id": "char_1"},
                {"event_slot_id": "evt_2", "location_id": "loc_2", "character_id": "char_2"},
            ],
        },
        "scene_assets": [
            {"scene_id": "scene_1", "location_id": "loc_1", "suggested_slots": ["evt_1"]},
            {"scene_id": "scene_2", "location_id": "loc_2", "suggested_slots": ["evt_2"]},
        ],
    }
    longline = {
        "stages": [{"stage_id": "stage_1"}],
        "story_room": {
            "master_story_design": {"story_engine": "竞争升级"},
            "major_foreshadowing": [{"hook_id": "hook_1"}, {"hook_id": "hook_2"}],
            "character_growth_arcs": [
                {"character_id": "char_1"},
                {"character_id": "char_2"},
                {"character_id": "char_3"},
            ],
            "ensemble_relationship_index": [
                {
                    "relationship_id": "rel_1_2",
                    "character_ids": ["char_1", "char_2"],
                },
                {
                    "relationship_id": "rel_2_3",
                    "character_ids": ["char_2", "char_3"],
                },
            ],
            "ensemble_relationship_arcs": [{
                "relationship_id": "rel_1_2",
                "character_ids": ["char_1", "char_2"],
                "turning_stages": [{"stage_id": "stage_1"}],
            }, {
                "relationship_id": "rel_2_3",
                "character_ids": ["char_2", "char_3"],
                "turning_stages": [{"stage_id": "stage_2"}],
            }],
            "major_map_system": {"major_regions": [{"map_id": "map_1"}, {"map_id": "map_2"}]},
        },
    }

    scoped_longline, scoped_story, scoped_map = Graph3._scope_event_design_assets(
        longline_content=longline,
        story_room=story_room,
        slot_ids={"evt_1"},
    )

    assert [item["character_id"] for item in scoped_story["volume_cast_cards"]] == ["char_1", "char_2"]
    assert [item["relationship_id"] for item in scoped_story["relationship_tracks"]] == ["rel_1_2"]
    assert [
        item["relationship_id"]
        for item in scoped_longline["story_room"]["ensemble_relationship_arcs"]
    ] == ["rel_1_2"]
    assert [item["hook_id"] for item in scoped_story["volume_foreshadowing"]] == ["hook_1"]
    assert [item["location_id"] for item in scoped_map["volume_map_system"]["locations"]] == ["loc_1"]
    assert [item["scene_id"] for item in scoped_map["scene_assets"]] == ["scene_1"]
    assert "major_map_system" not in scoped_longline["story_room"]


def test_layered_story_and_volume_rooms_run_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs.graph_2 import Graph2Input
    from novelwb.engine.graphs.graph_3 import Graph3Input
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()

    def auth(object_id: str, object_type: AuthObjectType, content: dict) -> AuthObject:
        return AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=object_type,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_test",
        )

    graph2_calls: list[str] = []

    def graph2_run(step_key: str, input_pack: dict, **kwargs):
        graph2_calls.append(step_key)
        if step_key == "graph2.longline.core":
            parsed = {
                "dq_promise": "江辰能否赢下公开竞争",
                "stage_nodes": [{"stage_id": "stage_1"}],
            }
        elif step_key == "graph2.map.room":
            parsed = {"major_map_system": {
                "major_regions": [{
                    "map_id": "map_1",
                    "parent_map_id": "",
                    "connected_map_ids": [],
                }],
                "major_routes": [],
            }}
        else:
            target = input_pack["target_key"]
            character_id = str(input_pack.get("target_character", {}).get("id") or "char_1")
            values = {
                "master_story_design": {
                    "central_dramatic_question": "能否取胜",
                    "story_engine": "公开竞争",
                    "active_goal_chain": [{"stage_id": "stage_1"}],
                    "ending_state": "赢得认可",
                },
                "major_foreshadowing": [{
                    "hook_id": "hook_1",
                    "involved_character_ids": ["char_1"],
                }],
                "character_growth_arc": {
                    "character_id": character_id,
                    "relationship_anchors": [],
                    "growth_stages": [{"stage_id": "stage_1"}],
                },
                "ensemble_relationship_index": [{
                    "relationship_id": "rel_1_2",
                    "name": "江辰与赵铁心",
                    "character_ids": ["char_1", "char_2"],
                }],
                "ensemble_relationship_arc": {
                    "relationship_id": "rel_1_2",
                    "name": "江辰与赵铁心",
                    "character_ids": ["char_1", "char_2"],
                    "turning_stages": [{"stage_id": "stage_1"}],
                },
                "narrative_line_index": [{
                    "line_id": "line_main",
                    "name": "公开竞争主线",
                    "owner_ids": ["char_1"],
                }],
                "narrative_line": {
                    "line_id": "line_main",
                    "name": "公开竞争主线",
                    "owner_ids": ["char_1"],
                    "progression_stages": [{"stage_id": "stage_1"}],
                },
                "key_item_index": [{
                    "item_id": "item_badge",
                    "name": "旧徽章",
                }],
                "key_item_arc": {
                    "item_id": "item_badge",
                    "name": "旧徽章",
                    "custody_chain": [{"stage_id": "stage_1"}],
                },
                "major_set_piece_index": [{
                    "set_piece_id": "set_final",
                    "name": "终场公开赛",
                }],
                "major_set_piece_seed": {
                    "set_piece_id": "set_final",
                    "name": "终场公开赛",
                    "build_up_requirements": ["资格争夺完成"],
                },
                "asset_lifecycle_policy": {"transient": "用后退休"},
                "entity_autonomy_rules": ["角色按自己的目标行动"],
                "story_room_rules": {
                    "must_preserve": ["核心因果"],
                    "flexible_zones": ["卷内场景"],
                    "anti_bloat_rules": ["不增加无用支线"],
                },
            }
            parsed = {target: values[target]}
        validator = kwargs.get("parsed_validator")
        assert validator is None or validator(parsed)
        return SimpleNamespace(ok=True, parsed=parsed)

    monkeypatch.setattr(orch._graph_2._runner, "run", graph2_run)
    graph2_out = orch._graph_2.run(Graph2Input(
        run_id="run_test",
        project_id="test_proj",
        spec00=auth("spec00", AuthObjectType.BIBLE, {"genre": "系统流"}),
        world_a=auth("world_a", AuthObjectType.BIBLE, {"rules": []}),
        cast=auth("cast", AuthObjectType.CHAR, {
            "characters": [
                {"id": "char_1", "name": "江辰"},
                {"id": "char_2", "name": "赵铁心"},
            ],
        }),
        commit=False,
    ))
    assert graph2_calls == [
        "graph2.longline.core",
        *(["graph2.story.field"] * 15),
        "graph2.map.room",
    ]
    assert graph2_out.longline.content["story_room"]["major_map_system"]["major_regions"]
    assert graph2_out.longline.content["story_room"]["master_story_design"]["story_engine"] == "公开竞争"
    assert graph2_out.longline.content["story_room"]["narrative_line_index"][0]["line_id"] == "line_main"
    assert graph2_out.longline.content["story_room"]["narrative_line_registry"][0]["line_id"] == "line_main"
    assert graph2_out.longline.content["story_room"]["key_item_arcs"][0]["item_id"] == "item_badge"
    assert graph2_out.longline.content["story_room"]["major_set_piece_seeds"][0]["set_piece_id"] == "set_final"

    slots = [
        {"slot_id": f"evt_{index:03d}", "event_goal": f"推进事件{index}"}
        for index in range(9)
    ]
    graph3_calls: list[str] = []

    def graph3_run(step_key: str, input_pack: dict, **kwargs):
        graph3_calls.append(step_key)
        if step_key == "graph3.volume.plan":
            assert input_pack["target_event_count"] == len(slots)
            parsed = {"volume_id": "vol_001", "event_slots": slots}
        elif step_key == "graph3.volume.story_room":
            parsed = {
                "volume_story_engine": {"volume_center": "赢下选拔"},
                "volume_foreshadowing": [],
                "volume_character_arcs": [{"character_id": "char_1", "key_choices": []}],
                "volume_cast_cards": [{"character_id": "char_1", "name": "江辰"}],
                "relationship_tracks": [],
                "volume_line_ledger": [{
                    "line_id": "line_main",
                    "scheduled_movements": [{
                        "event_slot_id": slot["slot_id"], "action": "推进",
                    } for slot in slots],
                }],
                "entity_agendas": [{
                    "agenda_id": "agenda_char_1",
                    "planned_actions": [{
                        "event_slot_id": slot["slot_id"], "action": "主动参与",
                    } for slot in slots],
                }],
                "key_item_tracks": [],
                "set_piece_plans": [],
                "transient_assets": [],
            }
        elif step_key == "graph3.volume.map_room":
            parsed = {
                "volume_story_engine": {"volume_center": "错误覆盖"},
                "volume_map_system": {
                    "active_major_map_ids": ["map_1"],
                    "locations": [{
                        "location_id": "loc_1",
                        "parent_map_id": "map_1",
                        "scheduled_slots": [slot["slot_id"] for slot in slots],
                        "character_connections": [{"character_id": "char_1"}],
                    }],
                    "route_matrix": [],
                    "map_and_character_progression": [{
                        "event_slot_id": slot["slot_id"],
                        "location_id": "loc_1",
                        "character_id": "char_1",
                    } for slot in slots],
                },
                "scene_assets": [{
                    "scene_id": "scene_1",
                    "location_id": "loc_1",
                    "suggested_slots": [slot["slot_id"] for slot in slots],
                }],
            }
        elif step_key == "graph3.volume.map_schedule":
            parsed = {
                "map_schedule": [{
                    "event_slot_id": slot["slot_id"],
                    "location_ids": ["loc_1"],
                    "scene_asset_ids": ["scene_1"],
                    "movement_and_timing": "原地承接",
                    "character_progression": [{
                        "character_id": "char_1",
                        "location_id": "loc_1",
                        "spatial_advantage_or_pressure": "空间压力",
                        "visible_effect": "主动行动",
                    }],
                } for slot in input_pack["event_slots"]],
            }
        elif step_key == "graph3.volume.event_designs":
            parsed = {
                "volume_map_system": {"locations": []},
                "event_designs": [{
                "slot_id": slot["slot_id"],
                "chapter_center": f"完成{slot['event_goal']}",
                "reader_payoff": "获得明确进展",
                "surface_goal": slot["event_goal"],
                "ending_requirement": "形成下一步压力",
                "content_must_include": ["主角主动行动"],
                "character_focus_ids": ["char_1"],
                "character_scene_goals": [{"character_id": "char_1"}],
                "location_ids": ["loc_1"],
                "scene_asset_ids": ["scene_1"],
                "foreshadowing_ids": [],
                "active_line_ids": ["line_main"],
                "entity_agenda_ids": ["agenda_char_1"],
                "item_track_ids": [],
                "transient_asset_ids": [],
                "set_piece_id": None,
                "growth_actions": [],
                "foreshadow_actions": [],
                } for slot in input_pack["volume_plan_content"]["event_slots"]],
            }
        else:
            parsed = {}
        validator = kwargs.get("parsed_validator")
        assert validator is None or validator(parsed)
        return SimpleNamespace(ok=True, parsed=parsed)

    monkeypatch.setattr(orch._graph_3._runner, "run", graph3_run)
    graph3_out = orch._graph_3.run(Graph3Input(
        run_id="run_test",
        project_id="test_proj",
        longline=graph2_out.longline,
        commit=False,
        events_per_volume=len(slots),
    ))
    assert graph3_out.aborted is False
    assert graph3_calls == [
        "graph3.volume.plan",
        "graph3.volume.story_room",
        "graph3.volume.map_room",
        "graph3.volume.map_schedule",
        "graph3.volume.map_schedule",
        "graph3.volume.event_designs",
        "graph3.volume.event_designs",
        "graph3.volume.fatigue_report",
    ]
    merged_slots = graph3_out.volume_contract.content["event_slots"]
    assert len(merged_slots) == 9
    assert all(slot["chapter_design"]["reading_assets"]["locations"] for slot in merged_slots)
    merged_room = graph3_out.volume_contract.content["story_room"]
    assert merged_room["volume_story_engine"]["volume_center"] == "赢下选拔"
    assert merged_room["volume_map_system"]["locations"]


def test_volume_plan_review_chain_splits_thirty_events_into_twelve_files():
    from novelwb.engine.graphs.graph_3 import volume_plan_steps

    steps = volume_plan_steps(30)

    assert len(steps) == 12
    assert [item.step_id for item in steps[:3]] == [
        "volume_plan",
        "volume_story_room",
        "volume_map_core",
    ]
    assert [(item.start_index, item.end_index) for item in steps[3:7]] == [
        (0, 8), (8, 16), (16, 24), (24, 30),
    ]
    assert all(item.step_id.startswith("volume_map_schedule_") for item in steps[3:7])
    assert all(item.step_id.startswith("volume_event_designs_") for item in steps[7:11])
    assert steps[-1].step_id == "volume_fatigue_report"
    assert sum(item.max_tokens for item in steps) == 260000


def test_volume_map_schedule_chunks_merge_to_full_slot_coverage(tmp_path: Path):
    from novelwb.engine.graphs.graph_3 import next_volume_plan_step, volume_plan_steps

    orch = _make_orchestrator(tmp_path)
    slots = [
        {"slot_id": f"evt_vol1_{index:03d}", "event_goal": f"事件{index}"}
        for index in range(1, 31)
    ]
    content = {
        "volume_id": "vol_001",
        "event_slots": slots,
        "_volume_workflow": {
            "version": 2,
            "events_per_volume": 30,
            "approved_steps": ["volume_plan", "volume_story_room", "volume_map_core"],
        },
        "story_room": {
            "volume_cast_cards": [{"character_id": "char_1", "name": "主角"}],
            "volume_map_system": {
                "locations": [{"location_id": "loc_1", "scheduled_slots": []}],
                "map_and_character_progression": [],
            },
            "scene_assets": [{
                "scene_id": "scene_1",
                "location_id": "loc_1",
                "suggested_slots": [],
            }],
            "volume_map_schedule": [],
        },
    }
    schedule_steps = [
        item for item in volume_plan_steps(30)
        if item.step_id.startswith("volume_map_schedule_")
    ]

    for step in schedule_steps:
        generated = {
            "map_schedule": [
                {
                    "event_slot_id": slot["slot_id"],
                    "location_ids": ["loc_1"],
                    "scene_asset_ids": ["scene_1"],
                    "movement_and_timing": "原地承接",
                    "character_progression": [{
                        "character_id": "char_1",
                        "location_id": "loc_1",
                        "spatial_advantage_or_pressure": "空间压力",
                        "visible_effect": "主动观察并行动",
                    }],
                }
                for slot in slots[step.start_index:step.end_index]
            ],
        }
        content = orch._graph_3.merge_review_step(
            step=step,
            generated=generated,
            approved_content=content,
            volume_index=1,
            events_per_volume=30,
        )

    room = content["story_room"]
    assert len(room["volume_map_schedule"]) == 30
    assert room["volume_map_system"]["locations"][0]["scheduled_slots"] == [
        slot["slot_id"] for slot in slots
    ]
    assert room["scene_assets"][0]["suggested_slots"] == [slot["slot_id"] for slot in slots]
    assert {
        item["event_slot_id"]
        for item in room["volume_map_system"]["map_and_character_progression"]
    } == {slot["slot_id"] for slot in slots}
    assert next_volume_plan_step(content, 30).step_id == "volume_event_designs_01"


def test_volume_workflow_approves_one_file_and_unlocks_only_the_next(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs.graph_3 import next_volume_plan_step
    from novelwb.utils.timeutil import utcnow
    import novelwb.engine.orchestrator as orchestrator_module

    orch = _make_orchestrator(tmp_path)
    now = utcnow()

    def commit(object_id: str, object_type: AuthObjectType, content: dict) -> AuthObject:
        return orch._auth_store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=object_type,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        ))

    commit("spec00", AuthObjectType.BIBLE, {
        "complexity_profile": {"level": "medium"},
        "budget": {"events_per_volume": 2},
    })
    commit("cast", AuthObjectType.CHAR, {
        "characters": [{"id": "char_1", "name": "主角"}],
    })
    longline = commit("longline", AuthObjectType.CONTRACT, {
        "stage_nodes": [{"stage_id": "stage_1"}],
        "story_room": {},
    })
    monkeypatch.setattr(orchestrator_module, "next_master_plan_step", lambda *args: None)
    monkeypatch.setattr(orch, "_load_latest_longline", lambda: longline)

    seen: list[str] = []

    def fake_generate(inp, step, approved_content):
        seen.append(step.step_id)
        assert approved_content == {}
        assert inp.events_per_volume == 2
        return {
            "volume_id": "vol_001",
            "title": "第一卷",
            "event_slots": [
                {"slot_id": "evt_vol1_001", "event_goal": "开局"},
                {"slot_id": "evt_vol1_002", "event_goal": "结算"},
            ],
        }

    monkeypatch.setattr(orch._graph_3, "generate_review_step", fake_generate)
    review = orch.generate_workflow_review(
        run_id="run_volume_file_1",
        stage="volume_plan",
        volume_index=1,
    )

    assert review["volume_step"] == "volume_plan"
    assert review["step_index"] == 1
    assert review["step_total"] == 6
    assert seen == ["volume_plan"]

    result = orch.approve_workflow_review(review["staging_id"], review["editable"])
    current = orch._load_volume_contract(1)
    assert result["volume_plan_complete"] is False
    assert current is not None
    assert current.content["_volume_workflow"]["approved_steps"] == ["volume_plan"]
    assert next_volume_plan_step(current.content, 2).step_id == "volume_story_room"


def test_graph3_plan_failure_persists_raw_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs.graph_3 import Graph3Input
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    longline = AuthObject(
        object_id="longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={"stage_nodes": []},
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    )

    monkeypatch.setattr(
        orch._graph_3._runner,
        "run",
        lambda **kwargs: SimpleNamespace(
            ok=False,
            parsed={"event_slots": [{"slot_id": "evt_001", "event_goal": "仅一项"}]},
            text='{"event_slots":[',
            call_records=[],
            candidates=[],
        ),
    )

    output = orch._graph_3.run(Graph3Input(
        run_id="run_graph3_failure",
        project_id="test_proj",
        longline=longline,
        events_per_volume=2,
        commit=False,
    ))

    failure_path = orch._layout.run_failure_path("run_graph3_failure", "volume_plan")
    assert output.aborted is True
    assert failure_path.name in output.abort_reason
    assert failure_path.exists()
    payload = json.loads(failure_path.read_text(encoding="utf-8"))
    assert payload["step_key"] == "graph3.volume.plan"
    assert payload["raw_text"] == '{"event_slots":['
    assert payload["parsed"]["event_slots"][0]["slot_id"] == "evt_001"


@pytest.mark.parametrize(
    "count_arg",
    [{"event_count": 3}, {"chapter_count": 3}],
    ids=["event-count", "legacy-chapter-count"],
)
def test_run_event_sprout_carries_history_between_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    count_arg: dict[str, int],
):
    orch = _make_orchestrator(tmp_path)
    calls: list[tuple[dict, list[ChapterSpec]]] = []

    def fake_run_event_write(run_id: str, event_slot: dict, history_chapter_specs=None):
        index = len(calls) + 1
        history = list(history_chapter_specs or [])
        calls.append((event_slot, history))
        event_id = f"ev_{index}"
        draft = EventDraft.model_construct(
            event_id=event_id,
            run_id=run_id,
            draft_text=f"第{index}段正文",
            blocks=[],
            word_count=20,
        )
        delta = ObservedDelta(
            state_after=StateSnapshot(
                snapshot_key=f"post_{event_id}",
                result_state_summary=f"第{index}段状态",
            ),
            result_state_summary=f"第{index}段状态",
        )
        event_out = SimpleNamespace(
            diff_report=SimpleNamespace(passed=True),
            fix_attempts=0,
            observed_delta=delta,
        )
        chapter = ChapterSpec.model_construct(
            chapter_id=f"ch_{index}",
            chapter_index=index,
            chapter_intent=ChapterIntent.ADVANCE,
            title=f"第{index}章",
        )
        return {
            "success": True,
            "draft": draft,
            "event": event_out,
            "chapter": SimpleNamespace(chapter_specs=[chapter]),
        }

    monkeypatch.setattr(orch, "run_event_write", fake_run_event_write)

    result = orch.run_event_sprout(
        run_id=new_run_id(),
        root_event_goal="测试一个连续三段的大事件",
        **count_arg,
    )

    assert result["success"] is True
    assert result["completed_slots"] == 3
    assert result["event_count"] == 3
    assert [c["chapter_index"] for c in result["chapters"]] == [1, 2, 3]
    assert len(calls) == 3
    assert len(calls[0][1]) == 0
    assert [spec.chapter_index for spec in calls[1][1]] == [1]
    assert [spec.chapter_index for spec in calls[2][1]] == [1, 2]
    assert [call[0]["sprout"]["phase_index"] for call in calls] == [0, 4, 9]
    assert [call[0]["sprout"]["arc_layer"] for call in calls] == ["建立层", "升级层", "兑现层"]
    assert all(call[0]["sprout"]["scene_unit_target"] >= 2 for call in calls)
    assert all("required_card_focus" in call[0] for call in calls)


def test_step_runner_emits_progress_through_sink(tmp_path: Path):
    """设置 deps.progress 后，每个 step 都应上报 start + done（done 带预览）。"""
    orch = _make_orchestrator(tmp_path)
    events: list[dict] = []
    orch._deps.progress = events.append

    run_id = new_run_id()
    event_id = new_event_id()
    draft = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text="测试草稿。" * 10,
        blocks=[],
        word_count=50,
    )
    orch.run_event_pipeline(run_id, event_id, draft)

    steps = [e for e in events if e.get("event") == "step"]
    assert steps, "应至少上报一个 step 事件"
    starts = [e for e in steps if e["phase"] == "start"]
    dones = [e for e in steps if e["phase"] == "done"]
    assert starts and dones
    assert all("step_key" in e for e in steps)
    assert all("preview" in e for e in dones)


def test_run_volume_auto_consumes_contract_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """run_volume_auto 应读取 CONTRACT.event_slots 并按规划逐槽写作。"""
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="vol_001_contract",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "volume_id": "vol_001",
            "event_slots": [
                {"slot_id": "evt_vol1_001", "event_goal": "规划事件一",
                 "allowed_changes": ["a1"], "forbidden_changes": ["f1"], "is_key_event": False},
                {"slot_id": "evt_vol1_002", "event_goal": "规划事件二", "is_key_event": True},
            ],
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="r0",
    ))

    seen: list[dict] = []

    def fake_run_event_write(run_id: str, event_slot: dict, history_chapter_specs=None):
        seen.append(event_slot)
        draft = EventDraft.model_construct(
            event_id=event_slot["slot_id"], run_id=run_id,
            draft_text="正文", blocks=[], word_count=10,
        )
        return {
            "success": True,
            "draft": draft,
            "event": SimpleNamespace(diff_report=SimpleNamespace(passed=True), fix_attempts=0),
            "chapter": SimpleNamespace(chapter_specs=[]),
        }

    monkeypatch.setattr(orch, "run_event_write", fake_run_event_write)

    result = orch.run_volume_auto(new_run_id())
    assert result["success"] is True
    assert result["completed_slots"] == 2
    assert [s["event_goal"] for s in seen] == ["规划事件一", "规划事件二"]
    # 兼容映射：allowed_changes → allowed_delta
    assert seen[0]["allowed_delta"] == ["a1"]
    assert seen[0]["forbidden_delta"] == ["f1"]


def test_step_runner_retries_empty_and_never_selects_empty(tmp_path: Path):
    """空响应应自动重试；只要有非空候选就选非空，全空才 ok=False。"""
    from novelwb.adapters.llm.base import LLMResponse
    from novelwb.core.schemas.domain_models import LLMCallRecord
    from novelwb.engine.step_runner import StepRunner
    from novelwb.utils.timeutil import utcnow

    class _ScriptedLLM(MockReplayAdapter):
        def __init__(self, scripted):
            super().__init__()
            self._scripted = list(scripted)
            self.calls = 0

        def call(self, prompt, **kw):
            i = self.calls
            self.calls += 1
            text = self._scripted[i] if i < len(self._scripted) else self._scripted[-1]
            rec = LLMCallRecord(
                call_id=f"c{i}", step_id=kw.get("step_id", ""),
                prompt_key=kw.get("prompt_key", ""), prompt_version="1",
                prompt_hash="h", model="fake", input_tokens=0, output_tokens=0,
                latency_ms=1, cached=False, timestamp=utcnow(),
            )
            return LLMResponse(text=text, record=rec)

    orch = _make_orchestrator(tmp_path)

    # 前两次空，第三次出 JSON → 重试拿到非空
    orch._deps.llm = _ScriptedLLM(["", "", '{"genre":"x"}'])
    r = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00", input_pack={"user_brief": "t"}, run_id="r")
    assert r.ok is True
    assert r.parsed == {"genre": "x"}
    assert orch._deps.llm.calls == 3

    # 非空但不是 JSON 不能当成成功；必须继续重试到拿到合法 JSON
    orch._deps.llm = _ScriptedLLM(["not json", '{"genre":"x"}'])
    r_bad_json = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00", input_pack={"user_brief": "t"}, run_id="r")
    assert r_bad_json.ok is True
    assert r_bad_json.parsed == {"genre": "x"}
    assert orch._deps.llm.calls == 2

    # 合法 JSON 但未通过步骤结构校验时，也必须重试且不能进入 Judge 候选池
    orch._deps.llm = _ScriptedLLM([
        '{"genre":"x"}',
        '{"genre":"x","required_field":true}',
    ])
    r_bad_structure = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00",
        input_pack={"user_brief": "t"},
        run_id="r",
        parsed_validator=lambda parsed: bool(parsed.get("required_field")),
    )
    assert r_bad_structure.ok is True
    assert r_bad_structure.parsed["required_field"] is True
    assert orch._deps.llm.calls == 2

    # 带前言/代码围栏时应能提取 JSON
    orch._deps.llm = _ScriptedLLM(['好的：\n```json\n{"genre":"x"}\n```'])
    r_wrapped = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00", input_pack={"user_brief": "t"}, run_id="r")
    assert r_wrapped.ok is True
    assert r_wrapped.parsed == {"genre": "x"}

    # 全部非 JSON → 重试耗尽，ok=False
    orch._deps.llm = _ScriptedLLM(["not json"])
    r_invalid = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00", input_pack={"user_brief": "t"}, run_id="r")
    assert r_invalid.ok is False
    assert orch._deps.llm.calls == StepRunner._EMPTY_RETRY_LIMIT + 1

    # 全空 → 重试耗尽，ok=False
    orch._deps.llm = _ScriptedLLM([""])
    r2 = StepRunner(orch._deps).run(
        step_key="graph1.stage.spec00", input_pack={"user_brief": "t"}, run_id="r")
    assert r2.ok is False
    assert orch._deps.llm.calls == StepRunner._EMPTY_RETRY_LIMIT + 1


def test_stage_engine_rejects_invalid_structured_output_without_partial_commit(tmp_path: Path):
    """The first invalid init artifact must abort without writing authority data."""
    orch = _make_orchestrator(tmp_path)
    result = orch.run_stage_engine(new_run_id(), "brief")
    assert result["success"] is False
    assert "spec00" in result["abort_reason"]
    assert orch._auth_store.load_bundle() == []


def test_complexity_router_respects_explicit_simple_brief():
    from novelwb.engine.complexity import detect_complexity_profile
    from novelwb.engine.step_runner import StepRunner

    low = detect_complexity_profile(
        "\u7b80\u5355\u65e0\u8111\u723d\uff0c\u5355\u7ebf\u63a8\u8fdb\uff0c\u4e0d\u8981\u9634\u8c0b"
    )
    high = detect_complexity_profile(
        "\u7fa4\u50cf\u591a\u7ebf\u6743\u8c0b\uff0c\u9700\u8981\u591a\u91cd\u53cd\u8f6c"
    )

    assert low["level"] == "low"
    assert low["hidden_layers_max"] == 0
    assert low["gray_forces_allowed"] is False
    assert high["level"] == "high"
    assert StepRunner._complexity_level({"complexity_profile": low}) == "low"
    assert StepRunner._complexity_level({
        "bible_content": {"_artifacts": {"spec00": {"complexity_profile": high}}}
    }) == "high"


def test_event_preview_requires_approval_before_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    run_id = new_run_id()
    event_id = new_event_id()
    draft = EventDraft.model_construct(
        event_id=event_id, run_id=run_id, draft_text="review me", blocks=[], word_count=9,
    )
    context = ContextPackage(
        context_id=f"ctx_{event_id}", event_id=event_id, focus="review",
        token_budget=1000, estimated_tokens=10, fingerprint="f" * 64,
    )
    graph4_out = SimpleNamespace(
        aborted=False, abort_reason="", draft=draft, context_package=context,
        budget_report={"target": 1000}, quality_report={"score": 90},
        quality_attempts=1, namecheck_passed=True,
    )
    monkeypatch.setattr(orch._graph_4, "run", lambda inp: graph4_out)

    preview = orch.run_event_preview(run_id, {"slot_id": event_id, "event_goal": "review"})

    assert preview["success"] is True
    assert preview["review_required"] is True
    assert orch._events_store.load_optional(event_id) is None
    assert orch._staging_store.exists(preview["staging_id"])

    committed: dict[str, str] = {}
    def fake_commit(**kwargs):
        committed["text"] = kwargs["draft"].draft_text
        return {"success": True, "draft": kwargs["draft"], "event": None, "chapter": None}
    monkeypatch.setattr(orch, "run_event_pipeline", fake_commit)
    approved = orch.approve_event_preview(preview["staging_id"], draft_text="edited review")
    assert approved["success"] is True
    assert committed["text"] == "edited review"
    assert not orch._staging_store.exists(preview["staging_id"])


def test_event_preview_reject_discards_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    draft = EventDraft.model_construct(
        event_id="evt_review", run_id="run_review", draft_text="reject me", blocks=[], word_count=9,
    )
    context = ContextPackage(
        context_id="ctx_review", event_id="evt_review", focus="review",
        token_budget=1000, fingerprint="e" * 64,
    )
    monkeypatch.setattr(orch._graph_4, "run", lambda inp: SimpleNamespace(
        aborted=False, abort_reason="", draft=draft, context_package=context,
        budget_report={}, quality_report={}, quality_attempts=0, namecheck_passed=True,
    ))
    preview = orch.run_event_preview("run_review", {"slot_id": "evt_review", "event_goal": "review"})

    assert orch.reject_event_preview(preview["staging_id"]) is True
    assert not orch._staging_store.exists(preview["staging_id"])


def test_step_runner_honors_backend_cancellation_before_llm_call(tmp_path: Path):
    import threading
    from novelwb.engine.step_runner import PipelineCancelled, StepRunner

    orch = _make_orchestrator(tmp_path)
    cancel_event = threading.Event()
    cancel_event.set()
    def progress(payload):
        return None
    progress.cancel_event = cancel_event
    orch._deps.progress = progress

    with pytest.raises(PipelineCancelled):
        StepRunner(orch._deps).run(
            step_key="graph1.stage.spec00",
            input_pack={"user_brief": "test", "complexity_profile": {"level": "low"}},
            run_id="run_cancelled",
        )


def test_run_volume_plan_uses_existing_longline_and_carryover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """后续卷规划应只跑图3，并把上一卷契约作为承接上下文传入。"""
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs.graph_3 import Graph3Output
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="spec00",
        project_id="test_proj",
        object_type=AuthObjectType.BIBLE,
        version=1,
        content={"budget": {"events_per_volume": 42}},
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_1",
    ))
    orch._auth_store.commit(AuthObject(
        object_id="run_1_longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={"dq_promise": "长线", "stage_nodes": []},
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_1",
    ))
    orch._auth_store.commit(AuthObject(
        object_id="run_1_vol_001_contract",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "volume_id": "vol_001",
            "event_slots": [{"slot_id": "evt_vol1_001", "event_goal": "上一卷事件"}],
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_1",
    ))

    seen = {}

    def fake_graph3_run(inp):
        seen["volume_index"] = inp.volume_index
        seen["longline"] = inp.longline.content
        seen["carryover"] = inp.carryover_context
        seen["events_per_volume"] = inp.events_per_volume
        contract = AuthObject(
            object_id="run_2_vol_002_contract",
            project_id="test_proj",
            object_type=AuthObjectType.CONTRACT,
            version=1,
            content={
                "volume_id": "vol_002",
                "event_slots": [{"slot_id": "evt_vol2_001", "event_goal": "下一卷事件"}],
            },
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_2",
        )
        orch._auth_store.commit(contract)
        return Graph3Output(volume_contract=contract)

    monkeypatch.setattr(orch._graph_3, "run", fake_graph3_run)

    result = orch.run_volume_plan("run_2", volume_index=2)
    assert result["success"] is True
    assert result["event_slots"] == 1
    assert seen["volume_index"] == 2
    assert seen["longline"]["dq_promise"] == "长线"
    assert seen["carryover"]["previous_volume_contract"]["volume_id"] == "vol_001"
    assert seen["events_per_volume"] == 42


def test_merge_character_state_content_updates_current_state():
    content: dict = {}
    state = StateSnapshot(
        snapshot_key="post_ev",
        event_id="ev",
        location="青云宗外门",
        time_in_story="入门大比前夜",
        resources={"key_items": ["裂纹戒指"]},
        hp={"protagonist": "右臂旧伤未愈"},
        ability_boundary=["无法稳定使用飞行法术"],
        relationship_state={"赵铁心": "暂时互信"},
        open_threads=["黑衣人身份未明"],
        result_state_summary="主角负伤但拿到关键线索",
    )

    Orchestrator._merge_character_state_content(content, state, "ev")

    protagonist = content["character_states"]["protagonist"]
    assert protagonist["location"] == "青云宗外门"
    assert protagonist["hp"] == "右臂旧伤未愈"
    assert protagonist["open_threads"] == ["黑衣人身份未明"]
    assert content["character_states"]["赵铁心"]["relationship_state"] == "暂时互信"
    assert content["current_state"]["snapshot_key"] == "post_ev"


def test_workflow_can_review_and_update_current_master_plan(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={"stage_nodes": [{"stage_id": "s1", "goal": "旧目标"}], "total_stages": 1},
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))

    review = orch.generate_workflow_review(
        run_id="run_review",
        stage="master_plan",
        from_current=True,
    )
    assert review["status"] == "pending"
    assert review["review_kind"] == "master_plan"
    review["editable"]["artifacts"][0]["content"]["stage_nodes"][0]["goal"] = "人工微调后的目标"

    result = orch.approve_workflow_review(review["staging_id"], review["editable"])

    assert result["approved"] is True
    revised = orch._auth_store.load_artifact("longline")
    assert revised is not None
    assert revised.version == 2
    assert revised.content["stage_nodes"][0]["goal"] == "人工微调后的目标"
    state = orch.workflow_state()
    assert state["pending_reviews"] == []
    assert next(item for item in state["reviews"] if item["staging_id"] == review["staging_id"])["status"] == "approved"


def test_workflow_rejects_foundation_bundle_review_in_favor_of_single_file_assets(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    for object_id in ("spec00", "world_a"):
        orch._auth_store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content={"name": object_id},
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        ))
    with pytest.raises(ValueError, match="逐文件微调"):
        orch.generate_workflow_review(
            run_id="run_review",
            stage="foundation",
            from_current=True,
        )


def test_foundation_workflow_generates_and_approves_exactly_one_file_at_a_time(
    tmp_path: Path,
):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    calls: list[tuple[str, dict[str, AuthObject]]] = []

    def fake_generate_step(inp, artifact_key: str, approved: dict[str, AuthObject]) -> AuthObject:
        calls.append((artifact_key, dict(approved)))
        now = utcnow()
        return AuthObject(
            object_id=artifact_key,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content={"generated_for": artifact_key},
            created_at=now,
            updated_at=now,
            committed_by_run_id=inp.run_id,
        )

    orch._graph_1.generate_step = fake_generate_step

    first = orch.generate_workflow_review(
        run_id="run_foundation_1",
        stage="foundation",
        brief="系统流爽文，小白文",
    )

    assert first["foundation_step"] == "spec00"
    assert first["step_index"] == 1
    assert first["step_total"] == 8
    assert [item["artifact_key"] for item in first["editable"]["artifacts"]] == ["spec00"]
    assert orch._auth_store.load_artifact("spec00") is None
    assert calls == [("spec00", {})]

    pending_state = orch.workflow_state()
    assert pending_state["foundation_progress"]["approved_count"] == 0
    assert pending_state["foundation_progress"]["steps"][0]["status"] == "pending"
    assert next(item for item in pending_state["stages"] if item["id"] == "master_plan")["status"] == "locked"

    with pytest.raises(ValueError, match="等待审核"):
        orch.generate_workflow_review(
            run_id="run_foundation_duplicate",
            stage="foundation",
            brief="系统流爽文，小白文",
        )

    first_editable = first["editable"]
    first_editable["artifacts"][0]["content"] = {
        "genre": "玄幻",
        "complexity_profile": {"level": "medium"},
        "main_promise": "主角以明确代价持续变强",
        "lens": "第三人称贴身视角",
        "lens_climate": {"emotion_base": "爽快"},
        "type_contract": {"training_baseline": "稳定升级"},
        "taboo_words": ["无代价升级"],
        "budget": {"total_events": 100},
        "core_hook": "系统奖励背后存在代价",
        "protagonist_core": {"want": "变强"},
        "scale_budget": {"max_entities_per_event": 4},
        "breather_policy": {"quota_ratio": 0.2},
        "writing_dictionary": {"chapter_intents": {"Advance": "推进"}},
        "forbidden_zones": ["反派降智"],
        "self_check": {"risks": ["升级过快"]},
        "human_review_marker": "以人工审核版本为准",
    }
    approved = orch.approve_workflow_review(first["staging_id"], first_editable)
    assert approved["committed"] == ["spec00"]

    approved_state = orch.workflow_state()
    assert approved_state["foundation_progress"]["approved_count"] == 1
    assert approved_state["foundation_progress"]["steps"][0]["status"] == "approved"
    assert approved_state["foundation_progress"]["steps"][1]["status"] == "available"
    with pytest.raises(ValueError, match="全部八个文件"):
        orch.generate_workflow_review(
            run_id="run_master_too_early",
            stage="master_plan",
        )

    second = orch.generate_workflow_review(
        run_id="run_foundation_2",
        stage="foundation",
    )

    assert second["foundation_step"] == "world_a"
    assert second["step_index"] == 2
    assert [item["artifact_key"] for item in second["editable"]["artifacts"]] == ["world_a"]
    assert calls[1][0] == "world_a"
    assert calls[1][1]["spec00"].content["human_review_marker"] == "以人工审核版本为准"


def test_foundation_only_unlocks_master_plan_after_all_eight_files_exist(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs import FOUNDATION_STEP_ORDER
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    for object_id in FOUNDATION_STEP_ORDER:
        orch._auth_store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content={"name": object_id},
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        ))

    state = orch.workflow_state()

    assert state["foundation_progress"]["approved_count"] == 8
    assert state["foundation_progress"]["complete"] is True
    assert next(item for item in state["stages"] if item["id"] == "foundation")["status"] == "approved"
    assert next(item for item in state["stages"] if item["id"] == "master_plan")["status"] == "available"


def test_master_plan_generates_and_approves_exactly_one_dynamic_file(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs import FOUNDATION_STEP_ORDER
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    for object_id in FOUNDATION_STEP_ORDER:
        content = {"name": object_id}
        if object_id == "spec00":
            content["complexity_profile"] = {"level": "medium"}
        if object_id == "cast":
            content["characters"] = [
                {"id": "char_1", "name": "江辰"},
                {"id": "char_2", "name": "赵铁心"},
            ]
        orch._auth_store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        ))

    seen: list[tuple[str, dict]] = []

    def fake_generate(inp, step_id: str, approved_content: dict):
        seen.append((step_id, approved_content))
        if step_id == "longline_core":
            return {
                "dq_promise": "江辰能否带队赢下公开竞争",
                "stage_nodes": [{"stage_id": "stage_1"}],
            }
        return {
            "central_dramatic_question": "能否赢下竞争",
            "story_engine": "选择与公开排名推动局面",
            "active_goal_chain": [{"stage_id": "stage_1"}],
            "ending_state": "团队建立新秩序",
        }

    orch._graph_2.generate_step = fake_generate
    state = orch.workflow_state()
    assert state["master_plan_progress"]["total"] == 13
    assert state["master_plan_progress"]["total_output_budget"] > 60000
    assert state["master_plan_progress"]["steps"][0]["status"] == "available"

    first = orch.generate_workflow_review(run_id="run_master_1", stage="master_plan")
    assert first["master_step"] == "longline_core"
    assert set(first["editable"]) == {"content"}
    assert first["asset_id"] == "master.longline_core"
    assert orch._auth_store.load_artifact("longline") is None
    pending = orch.workflow_state()
    assert pending["master_plan_progress"]["steps"][0]["status"] == "pending"
    assert next(item for item in pending["stages"] if item["id"] == "volume_plan")["status"] == "locked"

    approved = orch.approve_workflow_review(first["staging_id"], first["editable"])
    assert approved["master_step"] == "longline_core"
    partial = orch._auth_store.load_artifact("longline")
    assert partial is not None and partial.content["dq_promise"]
    after_first = orch.workflow_state()
    assert after_first["master_plan_progress"]["approved_count"] == 1
    assert after_first["master_plan_progress"]["steps"][1]["status"] == "available"

    second = orch.generate_workflow_review(run_id="run_master_2", stage="master_plan")
    assert second["master_step"] == "master_story_design"
    assert seen[1][1]["dq_promise"] == "江辰能否带队赢下公开竞争"
    orch.approve_workflow_review(second["staging_id"], second["editable"])
    revised = orch._auth_store.load_artifact("longline")
    assert revised is not None and revised.version == 2
    assert revised.content["story_room"]["master_story_design"]["story_engine"]


def test_master_asset_catalog_projects_individual_story_items(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "dq_promise": "能否取胜",
            "stage_nodes": [{"stage_id": "stage_1"}],
            "story_room": {
                "major_foreshadowing": [{"hook_id": "hook_1", "name": "旧徽章"}],
                "character_growth_arcs": [{"character_id": "char_1", "name": "江辰"}],
                "ensemble_relationship_index": [{
                    "relationship_id": "rel_jiang_zhao",
                    "name": "江辰与赵铁心",
                    "character_ids": ["char_1", "char_2"],
                }],
                "ensemble_relationship_arcs": [{
                    "relationship_id": "rel_jiang_zhao",
                    "name": "江辰与赵铁心",
                    "character_ids": ["char_1", "char_2"],
                    "turning_stages": [{"stage_id": "stage_1"}],
                }],
                "narrative_line_index": [{
                    "line_id": "line_main",
                    "name": "公开竞争索引",
                    "owner_ids": ["char_1"],
                }],
                "narrative_line_registry": [{"line_id": "line_main", "name": "公开竞争"}],
                "key_item_index": [{"item_id": "item_badge", "name": "旧徽章索引"}],
                "key_item_arcs": [{"item_id": "item_badge", "name": "旧徽章"}],
                "major_set_piece_index": [{"set_piece_id": "set_final", "name": "终场索引"}],
                "major_set_piece_seeds": [{"set_piece_id": "set_final", "name": "终场"}],
            },
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))

    catalog = orch.layered_asset_catalog()
    asset_ids = {item["asset_id"] for item in catalog["assets"]}
    assert "master.story.major_foreshadowing.hook_1" in asset_ids
    assert "master.story.character_growth_arcs.char_1" in asset_ids
    assert "master.story.ensemble_relationship_index.rel_jiang_zhao" in asset_ids
    assert "master.story.ensemble_relationship_arcs.rel_jiang_zhao" in asset_ids
    assert "master.story.narrative_line_index.line_main" in asset_ids
    assert "master.story.narrative_line_registry.line_main" in asset_ids
    assert "master.story.key_item_index.item_badge" in asset_ids
    assert "master.story.key_item_arcs.item_badge" in asset_ids
    assert "master.story.major_set_piece_index.set_final" in asset_ids
    assert "master.story.major_set_piece_seeds.set_final" in asset_ids
    detail = orch.layered_asset_detail("master.story.major_foreshadowing.hook_1")
    assert detail["content"]["name"] == "旧徽章"
    assert detail["editable"] is True
    relation_detail = orch.layered_asset_detail(
        "master.story.ensemble_relationship_arcs.rel_jiang_zhao"
    )
    assert relation_detail["content"]["relationship_id"] == "rel_jiang_zhao"
    assert relation_detail["editable"] is True


def test_relationship_index_expands_into_individual_review_steps():
    from novelwb.engine.graphs.graph_2 import (
        Graph2,
        master_plan_steps,
        merge_master_plan_step,
        next_master_plan_step,
    )

    cast = {"characters": [
        {"id": "char_1", "name": "江辰", "large_dossier": "甲" * 5000},
        {"id": "char_2", "name": "赵铁心", "large_dossier": "乙" * 5000},
        {"id": "char_3", "name": "苏晴", "large_dossier": "丙" * 5000},
    ]}
    content = {
        "dq_promise": "能否取胜",
        "stage_nodes": [{"stage_id": "stage_1"}],
        "story_room": {
            "master_story_design": {"story_engine": "公开竞争"},
            "major_foreshadowing": [{"hook_id": "hook_1"}],
            "character_growth_arcs": [
                {
                    "character_id": f"char_{index}",
                    "name": name,
                    "external_goal": "赢得资格",
                    "relationship_anchors": [],
                    "growth_stages": [{"detail": "长阶段" * 1000}],
                }
                for index, name in enumerate(("江辰", "赵铁心", "苏晴"), start=1)
            ],
        },
    }
    index_step = next_master_plan_step(content, cast)
    assert index_step is not None and index_step.step_id == "ensemble_relationship_index"

    cast_view, room_view, _ = Graph2._story_inputs(index_step, content, cast)
    assert all("large_dossier" in item for item in cast_view["characters"])
    assert all(
        "growth_stages" in item
        for item in room_view["character_growth_arcs"]
    )
    assert len(json.dumps([cast_view, room_view], ensure_ascii=False)) > 20000

    relation_index = [
        {
            "relationship_id": "rel_1_2",
            "name": "江辰与赵铁心",
            "character_ids": ["char_1", "char_2"],
        },
        {
            "relationship_id": "rel_2_3",
            "name": "赵铁心与苏晴",
            "character_ids": ["char_2", "char_3"],
        },
    ]
    content = merge_master_plan_step(content, index_step, relation_index)
    steps = master_plan_steps(cast, content)
    relation_steps = [item for item in steps if item.kind == "relationship_arc"]
    assert [item.relationship_id for item in relation_steps] == ["rel_1_2", "rel_2_3"]
    assert next_master_plan_step(content, cast).step_id == "ensemble_relationship_arc:rel_1_2"

    first_arc = {
        "relationship_id": "rel_1_2",
        "character_ids": ["char_1", "char_2"],
        "turning_stages": [{"stage_id": "stage_1"}],
    }
    assert Graph2.validate_step_content(
        relation_steps[0], first_arc, {"char_1", "char_2", "char_3"}
    ) == []
    content = merge_master_plan_step(content, relation_steps[0], first_arc)
    assert next_master_plan_step(content, cast).step_id == "ensemble_relationship_arc:rel_2_3"


def test_tail_indexes_expand_into_individual_bounded_review_steps():
    from novelwb.engine.graphs.graph_2 import (
        Graph2,
        master_plan_steps,
        merge_master_plan_step,
        next_master_plan_step,
    )

    cast = {"characters": [
        {"id": "char_1", "name": "江辰", "large_dossier": "甲" * 20000},
        {"id": "char_2", "name": "赵铁心", "large_dossier": "乙" * 20000},
    ]}
    content = {
        "dq_promise": "能否取胜",
        "stage_nodes": [{"stage_id": "stage_1"}],
        "story_room": {
            "master_story_design": {"story_engine": "公开竞争"},
            "major_foreshadowing": [{"hook_id": "hook_1", "name": "旧徽章"}],
            "character_growth_arcs": [
                {
                    "character_id": f"char_{index}",
                    "name": name,
                    "external_goal": "赢得资格",
                    "growth_stages": [{"detail": "长阶段" * 5000}],
                }
                for index, name in enumerate(("江辰", "赵铁心"), start=1)
            ],
            "ensemble_relationship_index": [{
                "relationship_id": "rel_1_2",
                "character_ids": ["char_1", "char_2"],
            }],
            "ensemble_relationship_arcs": [{
                "relationship_id": "rel_1_2",
                "character_ids": ["char_1", "char_2"],
                "turning_stages": [{"detail": "长转折" * 5000}],
            }],
        },
    }

    line_index_step = next_master_plan_step(content, cast)
    assert line_index_step is not None
    assert line_index_step.step_id == "narrative_line_index"
    cast_view, room_view, _ = Graph2._story_inputs(line_index_step, content, cast)
    full_context_json = json.dumps([cast_view, room_view], ensure_ascii=False)
    assert "large_dossier" in full_context_json
    assert "growth_stages" in full_context_json
    assert "turning_stages" in full_context_json
    assert len(full_context_json) > 80000

    line_index = [
        {
            "line_id": "line_main",
            "name": "公开竞争主线",
            "owner_ids": ["char_1"],
            "relationship_ids": ["rel_1_2"],
        },
        {
            "line_id": "line_rivalry",
            "name": "对手关系线",
            "owner_ids": ["char_2"],
            "relationship_ids": ["rel_1_2"],
        },
    ]
    assert Graph2.validate_step_content(
        line_index_step, line_index, {"char_1", "char_2"}
    ) == []
    content = merge_master_plan_step(content, line_index_step, line_index)
    line_steps = [item for item in master_plan_steps(cast, content) if item.kind == "narrative_line"]
    assert [item.entry_id for item in line_steps] == ["line_main", "line_rivalry"]
    assert next_master_plan_step(content, cast).step_id == "narrative_line:line_main"

    for step in line_steps:
        generated = {
            "line_id": step.entry_id,
            "owner_ids": ["char_1" if step.entry_id == "line_main" else "char_2"],
            "progression_stages": [{"stage_id": "stage_1"}],
        }
        assert Graph2.validate_step_content(
            step, generated, {"char_1", "char_2"}
        ) == []
        content = merge_master_plan_step(content, step, generated)

    item_index_step = next_master_plan_step(content, cast)
    assert item_index_step is not None and item_index_step.step_id == "key_item_index"
    content = merge_master_plan_step(content, item_index_step, [
        {"item_id": "item_badge", "name": "旧徽章"},
        {"item_id": "item_key", "name": "终场钥匙"},
    ])
    item_steps = [item for item in master_plan_steps(cast, content) if item.kind == "key_item_arc"]
    assert [item.entry_id for item in item_steps] == ["item_badge", "item_key"]
    for step in item_steps:
        generated = {
            "item_id": step.entry_id,
            "custody_chain": [{"stage_id": "stage_1"}],
        }
        assert Graph2.validate_step_content(step, generated) == []
        content = merge_master_plan_step(content, step, generated)

    set_index_step = next_master_plan_step(content, cast)
    assert set_index_step is not None and set_index_step.step_id == "major_set_piece_index"
    content = merge_master_plan_step(content, set_index_step, [
        {"set_piece_id": "set_final", "name": "终场公开赛"},
    ])
    set_step = next_master_plan_step(content, cast)
    assert set_step is not None and set_step.step_id == "major_set_piece_seed:set_final"
    generated_set_piece = {
        "set_piece_id": "set_final",
        "build_up_requirements": ["资格争夺完成"],
    }
    assert Graph2.validate_step_content(set_step, generated_set_piece) == []
    content = merge_master_plan_step(content, set_step, generated_set_piece)
    rule_step = next_master_plan_step(content, cast)
    assert rule_step is not None and rule_step.step_id == "asset_lifecycle_policy"

    content["story_room"]["narrative_line_registry"][0]["large_detail"] = "线" * 20000
    content["story_room"]["key_item_arcs"][0]["large_detail"] = "物" * 20000
    content["story_room"]["major_set_piece_seeds"][0]["large_detail"] = "场" * 20000
    full_rule_cast, full_rule_room, _ = Graph2._story_inputs(rule_step, content, cast)
    rule_json = json.dumps([full_rule_cast, full_rule_room], ensure_ascii=False)
    assert rule_json.count("large_detail") == 3
    assert "large_dossier" in rule_json

    map_step = next(item for item in master_plan_steps(cast, content) if item.kind == "map")
    map_json = json.dumps(Graph2._story_context(map_step, content), ensure_ascii=False)
    assert map_json.count("large_detail") == 3


def test_foundation_rewind_keeps_history_and_invalidates_only_dependents(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs import FOUNDATION_STEP_ORDER
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    for object_id in FOUNDATION_STEP_ORDER[:-1]:
        orch._auth_store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content={"name": object_id},
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        ))

    result = orch.rewind_foundation("world_b", "run_rewind")

    assert result["affected"] == ["world_b", "pow_s", "pow_e", "opp_eco", "cast"]
    assert Path(result["snapshot_path"]).exists()
    assert orch._auth_store.load_artifact("world_b") is None
    assert orch._auth_store.load_artifact("world_b", include_invalidated=True) is not None
    assert orch._auth_store.load_artifact("pow_l") is not None
    assert orch._auth_store.load_artifact("pow_s") is None
    state = orch.workflow_state()["foundation_progress"]
    assert state["next_step"] == "world_b"
    assert "world_b" in state["invalidated"]


def test_layered_asset_review_merges_one_story_room_file_without_overwriting_siblings(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "stage_nodes": [{"stage_id": "s1", "goal": "保持不变"}],
            "story_room": {
                "master_story_design": {"story_engine": "旧引擎", "ending_state": "旧结局"},
                "major_foreshadowing": [{"hook_id": "hook_1", "purpose": "不得丢失"}],
            },
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))

    catalog = orch.layered_asset_catalog()
    assert any(item["asset_id"] == "master.story.master_story_design" for item in catalog["assets"])
    detail = orch.layered_asset_detail("master.story.master_story_design")
    assert detail["content"]["story_engine"] == "旧引擎"
    assert detail["artifact_key"] == "longline"

    review = orch.generate_asset_review(
        "run_asset_edit",
        "master.story.master_story_design",
        {"story_engine": "人工细化后的引擎", "ending_state": "新结局"},
    )
    before = orch._auth_store.load_artifact("longline")
    assert before is not None
    assert before.version == 1
    assert before.content["story_room"]["master_story_design"]["story_engine"] == "旧引擎"
    assert review["review_kind"] == "asset_edit"
    assert review["asset_meta"]["json_path"] == "/story_room/master_story_design"

    result = orch.approve_workflow_review(review["staging_id"], review["editable"])

    assert result["approved"] is True
    revised = orch._auth_store.load_artifact("longline")
    assert revised is not None
    assert revised.version == 2
    assert revised.content["stage_nodes"][0]["goal"] == "保持不变"
    assert revised.content["story_room"]["major_foreshadowing"][0]["hook_id"] == "hook_1"
    assert revised.content["story_room"]["master_story_design"]["story_engine"] == "人工细化后的引擎"


def test_layered_asset_review_rejects_stale_authority_version(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    seed = orch._auth_store.commit(AuthObject(
        object_id="longline",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={"stage_nodes": [], "story_room": {"master_story_design": {"story_engine": "v1"}}},
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))
    review = orch.generate_asset_review(
        "run_asset_edit",
        "master.story.master_story_design",
        {"story_engine": "待审核修改"},
    )
    orch._auth_store.commit(seed.model_copy(update={
        "content": {"stage_nodes": [{"stage_id": "external"}], "story_room": {"master_story_design": {"story_engine": "v2"}}},
        "updated_at": utcnow(),
        "committed_by_run_id": "run_external",
    }))

    with pytest.raises(ValueError, match="版本已从 v1 更新到 v2"):
        orch.approve_workflow_review(review["staging_id"], review["editable"])
    latest = orch._auth_store.load_artifact("longline")
    assert latest is not None
    assert latest.content["story_room"]["master_story_design"]["story_engine"] == "v2"


def test_layered_asset_catalog_exposes_event_reading_assets_as_read_only(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="vol_001_contract",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "volume_id": "vol_001",
            "event_slots": [{
                "slot_id": "evt_vol1_001",
                "event_goal": "进入考场",
                "chapter_design": {"reading_assets": {"character_cards": [{"character_id": "char_1"}]}},
            }],
            "story_room": {
                "relationship_tracks": [{
                    "relationship_id": "rel_1_2",
                    "name": "江辰与赵铁心",
                    "character_ids": ["char_1", "char_2"],
                    "turn_slots": ["evt_vol1_001"],
                }],
                "event_designs": [{
                    "slot_id": "evt_vol1_001",
                    "chapter_center": "公开选择",
                }],
            },
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))

    asset_id = "event.volume_vol_001.evt_vol1_001.reading_assets"
    detail = orch.layered_asset_detail(asset_id)
    assert detail["derived"] is True
    assert detail["editable"] is False
    assert detail["content"]["character_cards"][0]["character_id"] == "char_1"
    relation_detail = orch.layered_asset_detail(
        "volume.volume_vol_001.story.relationship_tracks.rel_1_2"
    )
    assert relation_detail["content"]["relationship_id"] == "rel_1_2"
    assert relation_detail["editable"] is True
    with pytest.raises(ValueError, match="派生投影不能直接修改"):
        orch.generate_asset_review("run_asset_edit", asset_id, {})


def test_cast_generation_is_split_into_roster_dossiers_and_relations(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.engine.graphs import Graph1Input
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    graph = orch._graph_1
    now = utcnow()

    def auth(key: str, content: dict) -> AuthObject:
        return AuthObject(
            object_id=key,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id="run_seed",
        )

    roster = [
        {
            "id": f"char_{index}",
            "name": f"角色{index}",
            "role": "主角" if index == 0 else "伙伴",
            "identity": "宗门弟子",
            "public_goal": "完成当前任务",
            "relationship_to_protagonist": "本人" if index == 0 else "同伴",
            "entry_stage": "第一卷",
        }
        for index in range(6)
    ]
    calls: list[str] = []

    def fake_structured_step(**kwargs):
        step_key = kwargs["step_key"]
        calls.append(step_key)
        if step_key == "graph1.cast.roster":
            return {"roster": roster}
        if step_key == "graph1.cast.dossier":
            entry = kwargs["input_pack"]["roster_entry"]
            return {"character": {
                **entry,
                "background": {"origin": "本地", "faction": "宗门"},
                "motivation": "主动解决问题",
                "inner_design": {"desire": "成长", "fear": "失败"},
                "ability": {"current_boundary": "当前境界"},
                "known_facts": ["公开事实"],
                "unknown_facts": ["幕后真相"],
                "performance_anchors": {"speech_rhythm": "简短"},
                "scene_engine": ["任务分歧"],
            }}
        characters = kwargs["input_pack"]["characters"]
        ids = [item["id"] for item in characters]
        return {
            "relationships": [{
                "from_id": ids[0], "to_id": ids[1], "current_state": "同伴",
                "tension": "方法不同", "forbidden_jump": "不得突然决裂",
            }],
            "knowledge_boundaries": [{
                "fact": "幕后真相", "known_by": [ids[1]], "unknown_to": [ids[0]],
                "reveal_condition": "完成第三个事件",
            }],
            "ensemble_balance": [{
                "character_id": char_id,
                "unique_story_value": "独有价值",
                "independent_action_source": "主动执行个人目标",
                "avoid_redundancy_with": [],
            } for char_id in ids],
        }

    graph._run_structured_step = fake_structured_step
    approved = {
        "spec00": auth("spec00", {"complexity_profile": {"level": "medium"}}),
        "world_b": auth("world_b", {"geography": {"macro": "三域"}}),
        "opp_eco": auth("opp_eco", {"tier1_boss": {"name": "圣主"}}),
    }
    artifact = graph.generate_step(Graph1Input(
        run_id="run_cast_split",
        project_id="test_proj",
        user_brief="系统流爽文",
        complexity_profile={"level": "medium"},
    ), "cast", approved)

    assert len(artifact.content["characters"]) == 6
    assert calls == [
        "graph1.cast.roster",
        *(["graph1.cast.dossier"] * 6),
        "graph1.cast.relations",
    ]


def test_layered_asset_catalog_exposes_each_cast_character_as_a_file(tmp_path: Path):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    orch = _make_orchestrator(tmp_path)
    now = utcnow()
    orch._auth_store.commit(AuthObject(
        object_id="cast",
        project_id="test_proj",
        object_type=AuthObjectType.CHAR,
        version=1,
        content={
            "characters": [{"id": "char_hero", "name": "林舟"}],
            "relationships": [],
            "knowledge_boundaries": [],
            "ensemble_balance": [],
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))

    catalog = orch.layered_asset_catalog()
    asset_ids = {item["asset_id"] for item in catalog["assets"]}
    assert "foundation.cast.character.char_hero" in asset_ids
    detail = orch.layered_asset_detail("foundation.cast.character.char_hero")
    assert detail["content"]["name"] == "林舟"
    assert detail["json_path"] == "/characters/0"


def test_foundation_failure_persists_raw_response_and_validation_errors(tmp_path: Path):
    from novelwb.engine.step_runner import StepResult
    from novelwb.engine.foundation_validation import validate_foundation_content

    orch = _make_orchestrator(tmp_path)
    graph = orch._graph_1
    graph._runner.run = lambda **_: StepResult(
        step_id="step_invalid",
        step_key="graph1.world.B",
        text='{"macro_structure":"残缺返回"}',
        parsed={"macro_structure": "残缺返回"},
        call_records=[],
        candidates=[],
        lint_passed=True,
        ok=False,
    )

    with pytest.raises(ValueError, match="失败记录"):
        graph._run_structured_step(
            step_key="graph1.world.B",
            input_pack={},
            run_id="run_invalid_world_b",
            diagnostic_key="world_b",
            validator=lambda value: validate_foundation_content("world_b", value),
        )

    path = graph._layout.run_failure_path("run_invalid_world_b", "world_b")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["raw_text"] == '{"macro_structure":"残缺返回"}'
    assert "geography" in payload["validation_errors"][0]


def _seed_event_volume(orch: Orchestrator):
    from novelwb.core.constants import AuthObjectType
    from novelwb.core.schemas.domain_models import AuthObject
    from novelwb.utils.timeutil import utcnow

    now = utcnow()
    return orch._auth_store.commit(AuthObject(
        object_id="volume_vol_001",
        project_id="test_proj",
        object_type=AuthObjectType.CONTRACT,
        version=1,
        content={
            "volume_id": "vol_001",
            "title": "测试卷",
            "event_slots": [{
                "slot_id": "evt_vol1_001",
                "event_goal": "进入考场并确认第一位对手",
                "result_target": "获得公开考核资格",
                "key_deliverables": ["资格落地"],
            }],
            "story_room": {"event_designs": []},
        },
        created_at=now,
        updated_at=now,
        committed_by_run_id="run_seed",
    ))


def test_event_plan_files_approve_without_prose_and_survive_prose_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    _seed_event_volume(orch)
    generated_calls: list[str] = []
    payloads = {
        "constraints_route": {
            "budget_report": {"total_chars": 1200, "soft_min_chars": 20},
            "event_route": {"expansion_routes": ["plot", "character"]},
        },
        "world_pulse": {"world_pulse": {"entity_actions": []}},
        "event_expansion": {"event_expansion": {"dramatic_core": "资格冲突"}},
        "scene_plan": {
            "event_plan": {"scenes": [{"scene_id": "s001"}]},
            "scene_plan": [{"scene_id": "s001", "block_intent": "Advance"}],
        },
        "prewrite_assets": {
            "prewrite_check": {"passed": True, "issues": []},
            "namecheck": {"passed": True, "collisions": []},
            "jit_cards": [],
        },
    }

    def fake_generate(inp, step, approved_execution):
        generated_calls.append(step.step_id)
        return payloads[step.step_id], ContextPackage(
            context_id=f"ctx_{step.step_id}",
            event_id="evt_vol1_001",
            focus=step.label,
            token_budget=120000,
            estimated_tokens=100,
            fingerprint=(step.step_id * 64)[:64],
        )

    monkeypatch.setattr(orch._graph_4, "generate_review_step", fake_generate)
    monkeypatch.setattr(
        orch._graph_4,
        "run",
        lambda inp: (_ for _ in ()).throw(AssertionError("批准规划不得生成正文")),
    )

    for expected_step in payloads:
        review = orch.generate_workflow_review(
            run_id=f"run_{expected_step}",
            stage="event_plan",
            volume_index=1,
            event_index=1,
        )
        assert review["event_plan_step"] == expected_step
        result = orch.approve_workflow_review(review["staging_id"], review["editable"])
        assert result["event_plan_step"] == expected_step
        if expected_step == "constraints_route":
            assert orch.approve_workflow_review(review["staging_id"], review["editable"]) == result

    assert generated_calls == list(payloads)
    approved_volume = orch._load_volume_contract(1)
    assert approved_volume is not None
    approved_record = approved_volume.content["event_plans"]["evt_vol1_001"]
    assert approved_record["approved_steps"] == list(payloads)
    assert not any(
        packet.content.get("review_kind") == "prose"
        for packet in orch._staging_store.list_all()
    )

    preserved_version = approved_volume.version
    preserved_files = json.loads(json.dumps(approved_record["files"], ensure_ascii=False))
    monkeypatch.setattr(orch._graph_4, "run", lambda inp: SimpleNamespace(
        aborted=True,
        abort_reason="模拟正文超时",
    ))
    with pytest.raises(ValueError, match="模拟正文超时"):
        orch.generate_workflow_review(
            run_id="run_prose_failed",
            stage="prose",
            volume_index=1,
            event_index=1,
        )
    after_failure = orch._load_volume_contract(1)
    assert after_failure is not None
    assert after_failure.version == preserved_version
    assert after_failure.content["event_plans"]["evt_vol1_001"]["files"] == preserved_files
    assert generated_calls == list(payloads)


def test_graph4_execution_override_calls_only_prose_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.engine.graphs.graph_4 import Graph4Input

    orch = _make_orchestrator(tmp_path)
    calls: list[str] = []
    prose = "林深看见灯光，伸手推开考场的门。" * 20

    def fake_run(*, step_key, input_pack, run_id):
        calls.append(step_key)
        return SimpleNamespace(
            ok=True,
            parsed={
                "full_text": prose,
                "scene_receipts": [{"scene_id": "s001", "delivered_items": []}],
            },
            text=prose,
        )

    monkeypatch.setattr(orch._graph_4._runner, "run", fake_run)
    monkeypatch.setattr(orch._graph_4._quality, "evaluate", lambda *args, **kwargs: SimpleNamespace(
        score=100.0,
        passed=True,
        issues=[],
        to_dict=lambda: {"score": 100.0, "passed": True, "issues": []},
    ))
    out = orch._graph_4.run(Graph4Input(
        run_id="run_override",
        project_id="test_proj",
        event_slot={"slot_id": "evt_override", "event_goal": "进入考场"},
        execution_override={
            "budget_report": {"total_chars": 100, "soft_min_chars": 20},
            "event_route": {"expansion_routes": ["plot"]},
            "world_pulse": {},
            "event_expansion": {},
            "prewrite_check": {"passed": True},
            "event_plan": {"scenes": [{"scene_id": "s001"}]},
            "scene_plan": [{"scene_id": "s001", "block_intent": "Advance"}],
            "namecheck": {"passed": True},
            "jit_cards": [],
        },
    ))

    assert out.aborted is False
    assert calls == ["graph4.event.blocks.write"]


def test_event_plan_asset_edit_reopens_downstream_files(tmp_path: Path):
    from novelwb.engine.graphs.graph_4 import event_plan_steps, merge_event_plan_step

    orch = _make_orchestrator(tmp_path)
    volume = _seed_event_volume(orch)
    content = volume.content
    for step in event_plan_steps():
        payload = {field: {} for field in step.required_fields}
        if step.step_id == "scene_plan":
            payload = {"event_plan": {"scenes": [{"scene_id": "s001"}]}, "scene_plan": [{"scene_id": "s001"}]}
        elif step.step_id == "prewrite_assets":
            payload = {"prewrite_check": {"passed": True}, "namecheck": {"passed": True}, "jit_cards": []}
        content = merge_event_plan_step(
            content,
            event_id="evt_vol1_001",
            event_index=1,
            step=step,
            generated=payload,
        )
    orch._auth_store.commit(volume.model_copy(update={"content": content}))

    asset_id = "event.volume_vol_001.evt_vol1_001.plan.world_pulse"
    detail = orch.layered_asset_detail(asset_id)
    assert detail["editable"] is True
    assert detail["group_label"] == "事件 1 · 展开规划"
    review = orch.generate_asset_review("run_edit_plan", asset_id, {
        "world_pulse": {"entity_actions": [{"entity_id": "char_1", "action": "改为主动挑战"}]},
    })
    orch.approve_workflow_review(review["staging_id"], review["editable"])
    revised = orch._load_volume_contract(1)
    assert revised is not None
    record = revised.content["event_plans"]["evt_vol1_001"]
    assert record["approved_steps"] == ["constraints_route", "world_pulse"]
    assert set(record["files"]) == {"constraints_route", "world_pulse"}


def test_legacy_event_plan_review_migrates_without_prose_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import StagingType

    orch = _make_orchestrator(tmp_path)
    _seed_event_volume(orch)
    execution = {
        "budget_report": {"total_chars": 1200},
        "event_route": {"expansion_routes": ["plot"]},
        "world_pulse": {},
        "event_expansion": {},
        "event_plan": {"scenes": [{"scene_id": "s001"}]},
        "scene_plan": [{"scene_id": "s001"}],
        "prewrite_check": {"passed": True},
        "jit_cards": [],
    }
    packet = orch._save_review_packet(
        run_id="run_legacy",
        review_kind="event_plan",
        title="事件 1 展开方案",
        staging_type=StagingType.STG_EVENT,
        editable={
            "event_slot": {"slot_id": "evt_vol1_001", "event_goal": "进入考场"},
            "execution_report": execution,
        },
        internal={"event_index": 1},
    )
    monkeypatch.setattr(
        orch._graph_4,
        "run",
        lambda inp: (_ for _ in ()).throw(AssertionError("迁移不得调用模型或正文")),
    )

    result = orch.approve_workflow_review(
        packet.staging_id,
        packet.content["editable"],
    )

    assert result["event_plan_step"] == "legacy_bundle"
    assert result["event_plan_complete"] is True
    assert not any(
        item.content.get("review_kind") == "prose"
        for item in orch._staging_store.list_all()
    )


def test_failed_prewrite_reject_reopens_scene_plan_with_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import StagingType
    from novelwb.engine.graphs.graph_4 import (
        Graph4Input,
        event_plan_steps,
        execution_report_from_event_plan,
        merge_event_plan_step,
        next_event_plan_step,
    )

    orch = _make_orchestrator(tmp_path)
    volume = _seed_event_volume(orch)
    content = volume.content
    payloads = {
        "constraints_route": {
            "budget_report": {"total_chars": 1200},
            "event_route": {"expansion_routes": ["plot"]},
        },
        "world_pulse": {"world_pulse": {}},
        "event_expansion": {"event_expansion": {}},
        "scene_plan": {
            "event_plan": {"scenes": [{"scene_id": "s001"}]},
            "scene_plan": [{"scene_id": "s001"}],
        },
    }
    for step in event_plan_steps()[:4]:
        content = merge_event_plan_step(
            content,
            event_id="evt_vol1_001",
            event_index=1,
            step=step,
            generated=payloads[step.step_id],
        )
    committed = orch._auth_store.commit(volume.model_copy(update={"content": content}))
    feedback = {
        "passed": False,
        "issues": [{"dimension": "map", "problem": "地图压力未进入场景"}],
        "repair_instructions": ["让空间限制改变角色行动"],
    }
    packet = orch._save_review_packet(
        run_id="run_failed_prewrite",
        review_kind="event_plan",
        title="事件 1 · 5/5 · 正文前检查与临时资产",
        staging_type=StagingType.STG_EVENT,
        editable={"content": {
            "prewrite_check": feedback,
            "namecheck": {},
            "jit_cards": [],
        }},
        internal={
            "event_plan_step": "prewrite_assets",
            "event_id": "evt_vol1_001",
            "event_index": 1,
            "volume_index": 1,
            "base_version": committed.version,
        },
    )

    result = orch.reject_workflow_review(packet.staging_id)

    assert result["reopened_step"] == "scene_plan"
    revised = orch._load_volume_contract(1)
    assert revised is not None
    record = revised.content["event_plans"]["evt_vol1_001"]
    assert record["approved_steps"] == [
        "constraints_route", "world_pulse", "event_expansion",
    ]
    assert set(record["files"]) == {
        "constraints_route", "world_pulse", "event_expansion",
    }
    assert record["revision_feedback"]["passed"] is False
    assert record["revision_feedback"]["issues"] == feedback["issues"]
    assert record["revision_feedback"]["repair_instructions"] == feedback["repair_instructions"]
    assert next_event_plan_step(revised.content, "evt_vol1_001").step_id == "scene_plan"

    captured: dict = {}
    def fake_plan(*, step_key, input_pack, run_id, **kwargs):
        captured.update(input_pack)
        return SimpleNamespace(
            ok=True,
            parsed={"scenes": [{"scene_id": "s001", "scene_summary": "进入考场"}]},
        )
    monkeypatch.setattr(orch._graph_4._runner, "run", fake_plan)
    step = event_plan_steps()[3]
    orch._graph_4.generate_review_step(
        Graph4Input(
            run_id="run_scene_rework",
            project_id="test_proj",
            event_slot=revised.content["event_slots"][0],
            authority_bundle=orch._auth_store.load_bundle(),
        ),
        step,
        execution_report_from_event_plan(revised.content, "evt_vol1_001"),
    )
    assert captured["prewrite_feedback"] == record["revision_feedback"]


def test_flat_failed_prewrite_never_defaults_to_passed():
    from novelwb.engine.graphs.graph_4 import Graph4, event_plan_steps

    raw = {
        "causality": True,
        "timeline": True,
        "map": True,
        "knowledge_boundary": True,
        "entity_agency": True,
        "line_lifecycle": True,
        "asset_coverage": False,
        "non_checklist_rhythm": False,
    }
    normalized = Graph4.normalize_prewrite_check(raw)

    assert normalized["passed"] is False
    assert normalized["checks"]["asset_coverage"] is False
    assert normalized["issues"]
    assert normalized["repair_instructions"]
    errors = Graph4.validate_review_step(
        event_plan_steps()[-1],
        {
            "prewrite_check": raw,
            "namecheck": {},
            "jit_cards": [],
        },
    )
    assert errors
    assert "正文前检查未通过" in errors[0]


def test_scene_plan_response_requires_real_scenes():
    from novelwb.engine.graphs.graph_4 import Graph4

    assert Graph4._valid_scene_plan_response(
        {"event_summary": {"dramatic_center": "进入考场"}}
    ) is False
    assert Graph4._valid_scene_plan_response({
        "scenes": [{"scene_id": "s001", "scene_summary": "林深推门进入考场"}],
    }) is True


def test_prose_approval_rechecks_edited_quality(tmp_path: Path):
    from novelwb.core.constants import StagingType
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    draft_text = "他向前走了一步。" * 20
    draft = EventDraft.model_construct(
        event_id="evt_short",
        run_id="run_short",
        draft_text=draft_text,
        blocks=[],
        word_count=len(draft_text),
    )
    context = ContextPackage(
        context_id="ctx_short",
        event_id="evt_short",
        focus="短正文质量检查",
        token_budget=120000,
        estimated_tokens=10,
        fingerprint="a" * 64,
    )
    packet = orch._save_review_packet(
        run_id="run_short",
        review_kind="prose",
        title="事件 1 · 正文草稿",
        staging_type=StagingType.STG_EVENT,
        editable={"draft_text": draft_text},
        internal={
            "event_id": "evt_short",
            "event_index": 1,
            "volume_index": 1,
            "draft": draft.model_dump(mode="json"),
            "context_package": context.model_dump(mode="json"),
            "execution_report": {"prewrite_check": {"passed": True, "checks": {
                "causality": True,
            }}},
            "budget_report": {"total_chars": 2000},
        },
    )

    with pytest.raises(ValueError, match="正文质量仍未达标"):
        orch.approve_workflow_review(packet.staging_id, packet.content["editable"])


def test_prose_review_revision_uses_current_text_and_keeps_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import StagingType
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    generated_text = "原始正文。\n" + "\n".join(
        "".join(chr(0x4E00 + i * 37 + j) for j in range(20 + i % 30)) + "。"
        for i in range(50)
    )
    manually_edited_text = generated_text + "人工先补的一句。"
    revised_text = manually_edited_text.replace("原始正文", "修订正文", 1)
    draft = EventDraft.model_construct(
        event_id="evt_revision",
        run_id="run_revision",
        draft_text=generated_text,
        blocks=[],
        word_count=len(generated_text),
    )
    context = ContextPackage(
        context_id="ctx_revision",
        event_id="evt_revision",
        focus="审核修订",
        token_budget=120000,
        estimated_tokens=100,
        fingerprint="b" * 64,
    )
    packet = orch._save_review_packet(
        run_id="run_revision",
        review_kind="prose",
        title="事件 1 · 正文草稿",
        staging_type=StagingType.STG_EVENT,
        editable={"draft_text": generated_text},
        internal={
            "event_id": "evt_revision",
            "event_index": 1,
            "volume_index": 1,
            "draft": draft.model_dump(mode="json"),
            "context_package": context.model_dump(mode="json"),
            "execution_report": {"prewrite_check": {"passed": True}},
            "budget_report": {"total_chars": len(revised_text)},
        },
    )
    initial_payload = orch._review_payload(packet)
    assert initial_payload["current_audit"] is None
    assert initial_payload["suggested_feedback"] == ""
    captured: dict = {}

    def fake_audit(step_key, input_pack, **kwargs):
        captured.update(input_pack)
        return SimpleNamespace(
            ok=True,
            parsed={
                "verdict": "revise",
                "summary": "开头措辞需要修正，其余内容保留",
                "strengths": ["人工补句与后文衔接自然"],
                "issues": [{
                    "severity": "minor",
                    "category": "措辞",
                    "location_anchor": "原始正文",
                    "problem": "措辞重复",
                    "authority_basis": "不涉及权威冲突",
                    "revision_instruction": "只替换第一次出现",
                }],
                "revision_feedback": "只替换第一次出现的‘原始正文’，保留人工补句与其余全文",
            },
            call_records=[],
        )

    monkeypatch.setattr(orch._review_runner, "run", fake_audit)
    current_editable = {"draft_text": manually_edited_text}
    audited = orch.audit_workflow_review(packet.staging_id, current_editable)

    assert captured["original_content"] == manually_edited_text
    assert audited["status"] == "pending"
    assert audited["editable"] == current_editable
    assert audited["audit_count"] == 1
    assert audited["current_audit"]["issues"][0]["location_anchor"] == "原始正文"
    assert audited["suggested_feedback"].startswith("只替换第一次")
    assert captured["full_context"]["mechanical_quality_report"]["passed"] is True

    stored_audit_packet = orch._staging_store.load_optional(packet.staging_id)
    changed_content = dict(stored_audit_packet.content)
    changed_content["editable"] = {"draft_text": manually_edited_text + "浏览器新增内容"}
    changed_packet = stored_audit_packet.model_copy(update={"content": changed_content})
    assert orch._review_payload(changed_packet)["current_audit"] is None

    def fake_revise(step_key, input_pack, **kwargs):
        captured.update(input_pack)
        return SimpleNamespace(
            ok=True,
            parsed={
                "revised_content": revised_text,
                "change_summary": "只修正了开头措辞",
                "preserved_summary": "保留其余正文和人工补句",
            },
            call_records=[],
        )

    monkeypatch.setattr(orch._review_runner, "run", fake_revise)
    review = orch.revise_workflow_review(
        packet.staging_id,
        current_editable,
        "只改开头措辞，保留我手动补充的句子",
    )

    assert captured["original_content"] == manually_edited_text
    assert review["status"] == "pending"
    assert review["editable"]["draft_text"] == revised_text
    assert review["revision_count"] == 1
    assert review["revision_history"][0]["before_editable"] == current_editable
    assert review["revision_history"][0]["feedback"] == "只改开头措辞，保留我手动补充的句子"
    assert review["quality_report"]["revised_from_review"] is True
    assert review["current_audit"] is None
    assert review["audit_count"] == 1


def test_prose_ai_audit_cannot_pass_when_mechanical_quality_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import StagingType
    from novelwb.core.schemas.domain_models import ContextPackage

    orch = _make_orchestrator(tmp_path)
    draft_text = "太短。" * 10
    draft = EventDraft(
        event_id="evt_audit_quality",
        run_id="run_audit_quality",
        draft_text=draft_text,
    )
    context = ContextPackage(
        context_id="ctx_audit_quality",
        event_id=draft.event_id,
        focus="审核机械质量",
        token_budget=120000,
        fingerprint="c" * 64,
    )
    packet = orch._save_review_packet(
        run_id=draft.run_id,
        review_kind="prose",
        title="事件 1 · 正文草稿",
        staging_type=StagingType.STG_EVENT,
        editable={"draft_text": draft_text},
        internal={
            "event_id": draft.event_id,
            "event_index": 1,
            "volume_index": 1,
            "draft": draft.model_dump(mode="json"),
            "context_package": context.model_dump(mode="json"),
            "execution_report": {"prewrite_check": {"passed": True}},
            "budget_report": {"total_chars": 2000},
        },
    )

    def fake_audit(step_key, input_pack, **kwargs):
        assert input_pack["full_context"]["mechanical_quality_report"]["passed"] is False
        return SimpleNamespace(
            ok=True,
            parsed={
                "verdict": "pass",
                "summary": "语义与规划一致",
                "strengths": ["因果清晰"],
                "issues": [],
                "revision_feedback": "无需修改",
            },
            call_records=[],
        )

    monkeypatch.setattr(orch._review_runner, "run", fake_audit)
    audited = orch.audit_workflow_review(
        packet.staging_id,
        {"draft_text": draft_text},
    )

    assert audited["current_audit"]["verdict"] == "revise"
    assert audited["current_audit"]["issues"][0]["category"] == "机械质量"
    assert audited["quality_report"]["passed"] is False
    assert "机械质量问题" in audited["suggested_feedback"]


def test_event_plan_review_revision_revalidates_without_committing_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from novelwb.core.constants import StagingType

    orch = _make_orchestrator(tmp_path)
    volume = _seed_event_volume(orch)
    original = {
        "budget_report": {"total_chars": 1200},
        "event_route": {"expansion_routes": ["plot"]},
    }
    packet = orch._save_review_packet(
        run_id="run_plan_revision",
        review_kind="event_plan",
        title="事件 1 · 1/5 · 约束预算与展开路线",
        staging_type=StagingType.STG_EVENT,
        editable={"content": original},
        internal={
            "event_plan_step": "constraints_route",
            "event_id": "evt_vol1_001",
            "event_index": 1,
            "volume_index": 1,
            "base_version": volume.version,
            "event_slot": volume.content["event_slots"][0],
        },
    )
    manually_edited = {
        "budget_report": {"total_chars": 1400},
        "event_route": {"expansion_routes": ["plot", "character"]},
    }
    revised = {
        "budget_report": {"total_chars": 1400, "soft_min_chars": 1000},
        "event_route": {"expansion_routes": ["plot", "character"]},
    }
    captured: dict = {}

    def fake_revise(step_key, input_pack, **kwargs):
        captured.update(input_pack)
        return SimpleNamespace(
            ok=True,
            parsed={
                "revised_content": revised,
                "change_summary": "补足软下限并保留人工增加的角色路线",
                "preserved_summary": "保留事件目标和原有剧情路线",
            },
            call_records=[],
        )

    monkeypatch.setattr(orch._review_runner, "run", fake_revise)
    review = orch.revise_workflow_review(
        packet.staging_id,
        {"content": manually_edited},
        "保留角色路线，补足预算下限",
    )

    assert captured["original_content"] == manually_edited
    assert review["editable"]["content"] == revised
    assert review["status"] == "pending"
    assert orch._load_volume_contract(1).version == volume.version

    monkeypatch.setattr(orch._review_runner, "run", lambda *args, **kwargs: SimpleNamespace(
        ok=True,
        parsed={
            "revised_content": {"budget_report": {"total_chars": 1500}},
            "change_summary": "错误地删除了必需字段",
            "preserved_summary": "",
        },
        call_records=[],
    ))
    with pytest.raises(ValueError, match="结构校验失败"):
        orch.revise_workflow_review(
            packet.staging_id,
            review["editable"],
            "再次调整但不要丢字段",
        )
    unchanged = orch._staging_store.load(packet.staging_id)
    assert unchanged.content["editable"]["content"] == revised
    assert len(unchanged.content["internal"]["revision_history"]) == 1


def test_bad_approved_prewrite_prose_reject_reopens_scene_plan(tmp_path: Path):
    from novelwb.core.constants import StagingType
    from novelwb.engine.graphs.graph_4 import (
        event_plan_steps,
        merge_event_plan_step,
        next_event_plan_step,
    )

    orch = _make_orchestrator(tmp_path)
    volume = _seed_event_volume(orch)
    content = volume.content
    flat_failed = {
        "causality": True,
        "timeline": True,
        "map": True,
        "knowledge_boundary": True,
        "entity_agency": True,
        "line_lifecycle": True,
        "asset_coverage": False,
        "non_checklist_rhythm": False,
    }
    payloads = {
        "constraints_route": {"budget_report": {"total_chars": 1200}, "event_route": {}},
        "world_pulse": {"world_pulse": {}},
        "event_expansion": {"event_expansion": {}},
        "scene_plan": {
            "event_plan": {"scenes": [{"scene_id": "s001"}]},
            "scene_plan": [{"scene_id": "s001"}],
        },
        "prewrite_assets": {
            "prewrite_check": flat_failed,
            "namecheck": {},
            "jit_cards": [],
        },
    }
    for step in event_plan_steps():
        content = merge_event_plan_step(
            content,
            event_id="evt_vol1_001",
            event_index=1,
            step=step,
            generated=payloads[step.step_id],
        )
    committed = orch._auth_store.commit(volume.model_copy(update={"content": content}))
    packet = orch._save_review_packet(
        run_id="run_bad_prose",
        review_kind="prose",
        title="事件 1 · 正文草稿",
        staging_type=StagingType.STG_EVENT,
        editable={"draft_text": "错误规划生成的正文"},
        internal={
            "event_id": "evt_vol1_001",
            "event_index": 1,
            "volume_index": 1,
            "volume_version": committed.version,
            "execution_report": {"prewrite_check": flat_failed},
        },
    )

    result = orch.reject_workflow_review(packet.staging_id)

    assert result["reopened_step"] == "scene_plan"
    revised = orch._load_volume_contract(1)
    assert revised is not None
    assert next_event_plan_step(
        revised.content, "evt_vol1_001",
    ).step_id == "scene_plan"
    record = revised.content["event_plans"]["evt_vol1_001"]
    assert record["approved_steps"] == [
        "constraints_route", "world_pulse", "event_expansion",
    ]
    assert record["revision_feedback"]["passed"] is False
