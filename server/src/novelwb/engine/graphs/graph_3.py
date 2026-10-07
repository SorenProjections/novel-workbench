"""图3 — 分卷规划（Volume Planning）。

步骤：
  3.1 volume_plan          — 卷契约 + 事件槽位表
  3.2 volume_story_room    — 卷故事核心/角色成长/多维角色卡
  3.3 volume_map_room      — 卷地图/地点/路线/场景资产
  3.4 volume_event_designs — 逐事件中心与资产引用
  3.5 fatigue_report       — 卷级疲劳报告
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novelwb.core.constants import AuthObjectType
from novelwb.core.schemas.domain_models import AuthObject, FatigueReport
from novelwb.core.schemas.patch_models import CommitReceipt
from novelwb.engine.step_runner import GraphDeps, PipelineCancelled, StepResult, StepRunner
from novelwb.storage import AuthStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_receipt_id, new_report_id
from novelwb.utils.io_atomic import atomic_write_json
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow

_logger = get_logger(__name__)


@dataclass
class Graph3Input:
    """图3 的输入。"""

    run_id: str
    project_id: str
    longline: AuthObject
    volume_index: int = 1  # 第几卷（1-indexed）
    carryover_context: dict[str, Any] | None = None
    commit: bool = True
    complexity_profile: dict[str, Any] | None = None
    events_per_volume: int = 30


@dataclass
class Graph3Output:
    """图3 的输出。"""

    volume_contract: AuthObject | None = None  # VolumeContract 包在 content 里
    fatigue_report: FatigueReport | None = None
    commit_receipt: CommitReceipt | None = None
    aborted: bool = False
    abort_reason: str = ""


@dataclass(frozen=True)
class VolumePlanStep:
    """一个可独立生成、审核并提交的卷级逻辑文件。"""

    step_id: str
    label: str
    step_key: str
    asset_id: str
    max_tokens: int
    start_index: int = 0
    end_index: int = 0

    @property
    def is_chunk(self) -> bool:
        return self.end_index > self.start_index


def volume_plan_steps(events_per_volume: int) -> list[VolumePlanStep]:
    """Return the fixed review chain plus event-count-derived chunk files."""

    count = max(1, int(events_per_volume or 30))
    steps = [
        VolumePlanStep(
            "volume_plan", "卷纲骨架与事件槽", "graph3.volume.plan", "volume.plan", 48000
        ),
        VolumePlanStep(
            "volume_story_room",
            "本卷故事核心、人物与关系",
            "graph3.volume.story_room",
            "volume.story_room",
            40000,
        ),
        VolumePlanStep(
            "volume_map_core",
            "本卷地点、路线与场景资产",
            "graph3.volume.map_room",
            "volume.map_core",
            24000,
        ),
    ]
    chunks = [
        (start, min(start + Graph3._EVENT_DESIGN_CHUNK_SIZE, count))
        for start in range(0, count, Graph3._EVENT_DESIGN_CHUNK_SIZE)
    ]
    for index, (start, end) in enumerate(chunks, start=1):
        steps.append(
            VolumePlanStep(
                f"volume_map_schedule_{index:02d}",
                f"地图排期 {start + 1}-{end}",
                "graph3.volume.map_schedule",
                f"volume.map_schedule.{index:02d}",
                12000,
                start,
                end,
            )
        )
    for index, (start, end) in enumerate(chunks, start=1):
        steps.append(
            VolumePlanStep(
                f"volume_event_designs_{index:02d}",
                f"逐事件设计 {start + 1}-{end}",
                "graph3.volume.event_designs",
                f"volume.event_designs.{index:02d}",
                24000,
                start,
                end,
            )
        )
    steps.append(
        VolumePlanStep(
            "volume_fatigue_report",
            "卷级疲劳检查与最终组装",
            "graph3.volume.fatigue_report",
            "volume.fatigue_report",
            4000,
        )
    )
    return steps


def volume_plan_step_complete(content: dict[str, Any], step: VolumePlanStep) -> bool:
    workflow = content.get("_volume_workflow", {}) if isinstance(content, dict) else {}
    receipts = workflow.get("approved_steps", []) if isinstance(workflow, dict) else []
    if isinstance(receipts, list) and step.step_id in set(map(str, receipts)):
        return True
    # Backward compatibility for contracts created by the former all-at-once Graph3.
    if not workflow and isinstance(content, dict):
        slots = content.get("event_slots", [])
        room = content.get("story_room", {})
        designs = room.get("event_designs", []) if isinstance(room, dict) else []
        slot_ids = {
            str(item.get("slot_id"))
            for item in slots
            if isinstance(item, dict) and item.get("slot_id")
        }
        design_ids = {
            str(item.get("slot_id"))
            for item in designs
            if isinstance(item, dict) and item.get("slot_id")
        }
        if slot_ids and slot_ids == design_ids:
            return True
    return False


def next_volume_plan_step(
    content: dict[str, Any],
    events_per_volume: int,
) -> VolumePlanStep | None:
    return next(
        (
            step
            for step in volume_plan_steps(events_per_volume)
            if not volume_plan_step_complete(content, step)
        ),
        None,
    )


class Graph3:
    """分卷规划图执行器。"""

    _EVENT_DESIGN_CHUNK_SIZE = 8

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._runner = StepRunner(deps)
        self._auth_store = AuthStore(layout)
        self._layout = layout

    def _run_step(
        self,
        *,
        step_key: str,
        input_pack: dict[str, Any],
        run_id: str,
        diagnostic_key: str,
        parsed_validator: Callable[[Any], bool] | None = None,
    ) -> StepResult:
        try:
            result = self._runner.run(
                step_key=step_key,
                input_pack=input_pack,
                run_id=run_id,
                parsed_validator=parsed_validator,
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            path = self._persist_failure(
                run_id=run_id,
                diagnostic_key=diagnostic_key,
                step_key=step_key,
                error=f"请求异常：{exc}",
            )
            raise RuntimeError(f"{step_key} 请求失败：{exc}；失败记录：{path.name}") from exc

        if not getattr(result, "ok", False):
            call_records = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in getattr(result, "call_records", [])
            ]
            candidates = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in getattr(result, "candidates", [])
            ]
            self._persist_failure(
                run_id=run_id,
                diagnostic_key=diagnostic_key,
                step_key=step_key,
                error="结构化输出校验失败",
                parsed=getattr(result, "parsed", None),
                raw_text=getattr(result, "text", ""),
                call_records=call_records,
                candidates=candidates,
            )
        return result

    def _persist_failure(
        self,
        *,
        run_id: str,
        diagnostic_key: str,
        step_key: str,
        error: str,
        parsed: Any = None,
        raw_text: str = "",
        call_records: list[Any] | None = None,
        candidates: list[Any] | None = None,
    ) -> Path:
        path = self._layout.run_failure_path(run_id, f"volume_{diagnostic_key}")
        atomic_write_json(
            path,
            {
                "run_id": run_id,
                "project_id": self._layout.project_id,
                "diagnostic_key": diagnostic_key,
                "step_key": step_key,
                "failed_at": utcnow().isoformat(),
                "error": error,
                "raw_text": raw_text,
                "parsed": parsed,
                "call_records": call_records or [],
                "candidates": candidates or [],
            },
        )
        _logger.error(f"volume_plan_failure_saved run={run_id} step={step_key} path={path}")
        return path

    def generate_review_step(
        self,
        inp: Graph3Input,
        step: VolumePlanStep,
        approved_content: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate exactly one editable Graph3 review file."""

        try:
            target_event_count = max(1, int(inp.events_per_volume or 30))
        except (TypeError, ValueError):
            target_event_count = 30
        content = deepcopy(approved_content) if isinstance(approved_content, dict) else {}
        volume_id = f"vol_{inp.volume_index:03d}"
        slots = self._usable_event_slots(content)

        if step.step_id == "volume_plan":
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key="plan",
                input_pack={
                    "longline_content": inp.longline.content,
                    "volume_index": inp.volume_index,
                    "volume_id": volume_id,
                    "carryover_context": inp.carryover_context or {},
                    "complexity_profile": inp.complexity_profile or {},
                    "target_event_count": target_event_count,
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: (
                    isinstance(parsed, dict)
                    and len(self._usable_event_slots(parsed)) == target_event_count
                ),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, "volume_plan")
                raise ValueError(
                    f"卷纲骨架未返回{target_event_count}个完整事件槽位；失败记录：{path.name}"
                )
            return deepcopy(result.parsed)

        if len(slots) != target_event_count:
            raise ValueError(
                f"卷纲骨架尚未批准完整：应有{target_event_count}个事件槽位，当前为{len(slots)}个"
            )

        if step.step_id == "volume_story_room":
            relationship_pairs = self._master_relationship_pairs(inp.longline.content)
            expected_ids = {str(item["slot_id"]) for item in slots}
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key="story_room",
                input_pack={
                    "longline_content": inp.longline.content,
                    "volume_plan_content": self._plan_without_story_room(content),
                    "carryover_context": inp.carryover_context or {},
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: self._valid_volume_story_room(
                    parsed,
                    expected_slot_ids=expected_ids,
                    master_relationship_pairs=relationship_pairs,
                ),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, "volume_story_room")
                raise ValueError(f"本卷故事核心结构不完整；失败记录：{path.name}")
            return self._story_room_payload(result.parsed)

        story_room = content.get("story_room", {})
        if not isinstance(story_room, dict):
            raise ValueError("本卷故事核心尚未批准")

        if step.step_id == "volume_map_core":
            major_map_system = inp.longline.content.get("story_room", {}).get(
                "major_map_system", {}
            )
            allowed_parent_map_ids = (
                {
                    str(item.get("map_id"))
                    for item in major_map_system.get("major_regions", [])
                    if isinstance(item, dict) and item.get("map_id")
                }
                if isinstance(major_map_system, dict)
                else set()
            )
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key="map_core",
                input_pack={
                    "longline_content": inp.longline.content,
                    "volume_plan_content": self._plan_without_story_room(content),
                    "volume_story_core": self._story_room_payload(story_room),
                    "carryover_context": inp.carryover_context or {},
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: (
                    self._valid_volume_map_room(
                        parsed,
                        story_room=story_room,
                        expected_slot_ids=None,
                        allowed_parent_map_ids=allowed_parent_map_ids,
                    )
                    and bool(parsed.get("scene_assets"))
                ),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, "volume_map_core")
                raise ValueError(f"本卷地点、路线或场景资产结构不完整；失败记录：{path.name}")
            return {
                "volume_map_system": deepcopy(result.parsed["volume_map_system"]),
                "scene_assets": deepcopy(result.parsed["scene_assets"]),
            }

        if step.step_id.startswith("volume_map_schedule_"):
            chunk_slots = slots[step.start_index : step.end_index]
            schedule_ids = [str(item["slot_id"]) for item in chunk_slots]
            map_room = self._map_room_payload(story_room)
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key=step.step_id,
                input_pack={
                    "volume_id": volume_id,
                    "event_slots": chunk_slots,
                    "volume_story_core": {
                        "volume_story_engine": story_room.get("volume_story_engine", {}),
                        "volume_cast_cards": story_room.get("volume_cast_cards", []),
                    },
                    "volume_map_room": map_room,
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: self._valid_map_schedule(
                    parsed,
                    story_room=story_room,
                    map_room=map_room,
                    expected_slot_ids=schedule_ids,
                ),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, f"volume_{step.step_id}")
                raise ValueError(f"{step.label}未逐槽完整覆盖；失败记录：{path.name}")
            return {"map_schedule": deepcopy(result.parsed["map_schedule"])}

        if step.step_id.startswith("volume_event_designs_"):
            chunk_slots = slots[step.start_index : step.end_index]
            chunk_ids = [str(item["slot_id"]) for item in chunk_slots]
            scoped_plan = self._plan_without_story_room(content)
            scoped_plan["event_slots"] = chunk_slots
            scoped_plan["event_design_scope"] = {
                "chunk_index": next(
                    index
                    for index, item in enumerate(
                        [
                            candidate
                            for candidate in volume_plan_steps(target_event_count)
                            if candidate.step_id.startswith("volume_event_designs_")
                        ],
                        start=1,
                    )
                    if item.step_id == step.step_id
                ),
                "previous_slot": slots[step.start_index - 1] if step.start_index > 0 else None,
                "next_slot": slots[step.end_index] if step.end_index < len(slots) else None,
            }
            scoped_longline, scoped_story, scoped_map = self._scope_event_design_assets(
                longline_content=inp.longline.content,
                story_room=story_room,
                slot_ids=set(chunk_ids),
            )
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key=step.step_id,
                input_pack={
                    "longline_content": scoped_longline,
                    "volume_plan_content": scoped_plan,
                    "volume_story_core": scoped_story,
                    "volume_map_room": scoped_map,
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: self._valid_event_designs(
                    parsed,
                    story_room=story_room,
                    expected_slot_ids=chunk_ids,
                ),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, f"volume_{step.step_id}")
                raise ValueError(f"{step.label}未完整覆盖当前批次；失败记录：{path.name}")
            return {"event_designs": deepcopy(result.parsed["event_designs"])}

        if step.step_id == "volume_fatigue_report":
            result = self._run_step(
                step_key=step.step_key,
                diagnostic_key="fatigue_report",
                input_pack={
                    "volume_plan_content": content,
                    "volume_id": volume_id,
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=inp.run_id,
                parsed_validator=lambda parsed: isinstance(parsed, dict) and bool(parsed),
            )
            if not result.ok or not isinstance(result.parsed, dict):
                path = self._layout.run_failure_path(inp.run_id, "volume_fatigue_report")
                raise ValueError(f"卷级疲劳检查未返回完整JSON；失败记录：{path.name}")
            return deepcopy(result.parsed)

        raise ValueError(f"未知卷规划审核步骤：{step.step_id}")

    def validate_review_step(
        self,
        *,
        step: VolumePlanStep,
        generated: object,
        approved_content: dict[str, Any],
        longline_content: dict[str, Any],
        events_per_volume: int,
    ) -> list[str]:
        """Validate a user-edited review file before merging it into authority."""

        target = max(1, int(events_per_volume or 30))
        content = approved_content if isinstance(approved_content, dict) else {}
        slots = self._usable_event_slots(content)
        if step.step_id == "volume_plan":
            if not isinstance(generated, dict):
                return ["卷纲必须是JSON对象"]
            actual = len(self._usable_event_slots(generated))
            return (
                []
                if actual == target
                else [f"必须包含{target}个唯一且完整的事件槽位，当前为{actual}个"]
            )
        if not isinstance(generated, dict):
            return ["当前审核文件必须是JSON对象"]
        if len(slots) != target:
            return [f"前序卷纲槽位数量不完整：应有{target}个，当前为{len(slots)}个"]
        story_room = content.get("story_room", {})
        expected_ids = {str(item["slot_id"]) for item in slots}
        if step.step_id == "volume_story_room":
            valid = self._valid_volume_story_room(
                generated,
                expected_slot_ids=expected_ids,
                master_relationship_pairs=self._master_relationship_pairs(longline_content),
            )
            return [] if valid else ["卷故事引擎、角色成长、关系、故事线或议程结构不完整/引用无效"]
        if step.step_id == "volume_map_core":
            major = longline_content.get("story_room", {}).get("major_map_system", {})
            allowed = (
                {
                    str(item.get("map_id"))
                    for item in major.get("major_regions", [])
                    if isinstance(item, dict) and item.get("map_id")
                }
                if isinstance(major, dict)
                else set()
            )
            valid = self._valid_volume_map_room(
                generated,
                story_room=story_room,
                expected_slot_ids=None,
                allowed_parent_map_ids=allowed,
            ) and bool(generated.get("scene_assets"))
            return [] if valid else ["地点、父级地图、人物联系、路线或场景引用无效"]
        if step.step_id.startswith("volume_map_schedule_"):
            chunk_ids = [str(item["slot_id"]) for item in slots[step.start_index : step.end_index]]
            valid = self._valid_map_schedule(
                generated,
                story_room=story_room,
                map_room=self._map_room_payload(story_room),
                expected_slot_ids=chunk_ids,
            )
            return [] if valid else [f"地图排期必须逐一覆盖：{', '.join(chunk_ids)}"]
        if step.step_id.startswith("volume_event_designs_"):
            chunk_ids = [str(item["slot_id"]) for item in slots[step.start_index : step.end_index]]
            valid = self._valid_event_designs(
                generated,
                story_room=story_room,
                expected_slot_ids=chunk_ids,
            )
            return (
                []
                if valid
                else [f"逐事件设计必须逐一覆盖当前批次并使用有效资产ID：{', '.join(chunk_ids)}"]
            )
        if step.step_id == "volume_fatigue_report":
            return [] if generated else ["疲劳检查不能为空"]
        return [f"未知卷规划步骤：{step.step_id}"]

    def merge_review_step(
        self,
        *,
        step: VolumePlanStep,
        generated: dict[str, Any],
        approved_content: dict[str, Any],
        volume_index: int,
        events_per_volume: int,
    ) -> dict[str, Any]:
        """Merge one approved logical file into the partial volume contract."""

        if step.step_id == "volume_plan":
            content = deepcopy(generated)
            content.setdefault("volume_id", f"vol_{volume_index:03d}")
            content["_volume_workflow"] = {
                "version": 2,
                "events_per_volume": max(1, int(events_per_volume or 30)),
                "approved_steps": [],
            }
        else:
            content = deepcopy(approved_content)
        room = content.setdefault("story_room", {})

        if step.step_id == "volume_story_room":
            room.update(self._story_room_payload(generated))
        elif step.step_id == "volume_map_core":
            map_system = deepcopy(generated["volume_map_system"])
            for location in map_system.get("locations", []):
                if isinstance(location, dict):
                    location["scheduled_slots"] = []
            map_system["map_and_character_progression"] = []
            scenes = deepcopy(generated["scene_assets"])
            for scene in scenes:
                if isinstance(scene, dict):
                    scene["suggested_slots"] = []
            room["volume_map_system"] = map_system
            room["scene_assets"] = scenes
            room["volume_map_schedule"] = []
        elif step.step_id.startswith("volume_map_schedule_"):
            existing = {
                str(item.get("event_slot_id")): deepcopy(item)
                for item in room.get("volume_map_schedule", [])
                if isinstance(item, dict) and item.get("event_slot_id")
            }
            for item in generated["map_schedule"]:
                existing[str(item["event_slot_id"])] = deepcopy(item)
            order = {
                str(item.get("slot_id")): index
                for index, item in enumerate(content.get("event_slots", []))
                if isinstance(item, dict)
            }
            room["volume_map_schedule"] = sorted(
                existing.values(),
                key=lambda item: order.get(str(item.get("event_slot_id")), 10**9),
            )
            self._apply_volume_map_schedule(room)
        elif step.step_id.startswith("volume_event_designs_"):
            existing = {
                str(item.get("slot_id")): deepcopy(item)
                for item in room.get("event_designs", [])
                if isinstance(item, dict) and item.get("slot_id")
            }
            for item in generated["event_designs"]:
                existing[str(item["slot_id"])] = deepcopy(item)
            order = {
                str(item.get("slot_id")): index
                for index, item in enumerate(content.get("event_slots", []))
                if isinstance(item, dict)
            }
            room["event_designs"] = sorted(
                existing.values(),
                key=lambda item: order.get(str(item.get("slot_id")), 10**9),
            )
            self._merge_event_designs(content, room)
        elif step.step_id == "volume_fatigue_report":
            content["volume_fatigue_report"] = deepcopy(generated)

        workflow = content.setdefault(
            "_volume_workflow",
            {
                "version": 2,
                "events_per_volume": max(1, int(events_per_volume or 30)),
                "approved_steps": [],
            },
        )
        receipts = workflow.setdefault("approved_steps", [])
        if step.step_id not in receipts:
            receipts.append(step.step_id)
        return content

    @staticmethod
    def _plan_without_story_room(content: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in content.items()
            if key not in {"story_room", "_volume_workflow", "volume_fatigue_report"}
        }

    @staticmethod
    def _story_room_payload(content: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "volume_story_engine",
            "volume_foreshadowing",
            "volume_character_arcs",
            "volume_cast_cards",
            "relationship_tracks",
            "volume_line_ledger",
            "entity_agendas",
            "key_item_tracks",
            "set_piece_plans",
            "transient_assets",
        )
        return {key: deepcopy(content[key]) for key in keys if key in content}

    @staticmethod
    def _map_room_payload(story_room: dict[str, Any]) -> dict[str, Any]:
        return {
            "volume_map_system": deepcopy(story_room.get("volume_map_system", {})),
            "scene_assets": deepcopy(story_room.get("scene_assets", [])),
        }

    @staticmethod
    def _valid_map_schedule(
        parsed: object,
        *,
        story_room: dict[str, Any],
        map_room: dict[str, Any],
        expected_slot_ids: list[str],
    ) -> bool:
        if not isinstance(parsed, dict) or not isinstance(parsed.get("map_schedule"), list):
            return False
        entries = parsed["map_schedule"]
        entry_ids = [
            str(item.get("event_slot_id") or "").strip()
            for item in entries
            if isinstance(item, dict)
        ]
        if (
            len(entry_ids) != len(entries)
            or len(entry_ids) != len(set(entry_ids))
            or set(entry_ids) != set(expected_slot_ids)
        ):
            return False
        map_system = map_room.get("volume_map_system", {})
        locations = map_system.get("locations", []) if isinstance(map_system, dict) else []
        location_ids = {
            str(item.get("location_id"))
            for item in locations
            if isinstance(item, dict) and item.get("location_id")
        }
        scenes = map_room.get("scene_assets", [])
        scene_locations = {
            str(item.get("scene_id")): str(item.get("location_id"))
            for item in scenes
            if isinstance(item, dict) and item.get("scene_id")
        }
        character_ids = {
            str(item.get("character_id"))
            for item in story_room.get("volume_cast_cards", [])
            if isinstance(item, dict) and item.get("character_id")
        }
        if not location_ids or not character_ids:
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            assigned_locations = entry.get("location_ids")
            assigned_scenes = entry.get("scene_asset_ids")
            progression = entry.get("character_progression")
            if (
                not isinstance(assigned_locations, list)
                or not assigned_locations
                or not set(map(str, assigned_locations)) <= location_ids
                or not isinstance(assigned_scenes, list)
                or not set(map(str, assigned_scenes)) <= set(scene_locations)
                or any(
                    scene_locations.get(str(scene_id)) not in set(map(str, assigned_locations))
                    for scene_id in assigned_scenes
                )
                or not isinstance(progression, list)
                or not progression
            ):
                return False
            assigned_location_set = set(map(str, assigned_locations))
            if any(
                not isinstance(item, dict)
                or str(item.get("character_id")) not in character_ids
                or str(item.get("location_id")) not in assigned_location_set
                or not str(item.get("spatial_advantage_or_pressure") or "").strip()
                or not str(item.get("visible_effect") or "").strip()
                for item in progression
            ):
                return False
        return True

    @staticmethod
    def _apply_volume_map_schedule(story_room: dict[str, Any]) -> None:
        map_system = story_room.get("volume_map_system", {})
        if not isinstance(map_system, dict):
            return
        locations = map_system.get("locations", [])
        scenes = story_room.get("scene_assets", [])
        location_by_id = {
            str(item.get("location_id")): item
            for item in locations
            if isinstance(item, dict) and item.get("location_id")
        }
        scene_by_id = {
            str(item.get("scene_id")): item
            for item in scenes
            if isinstance(item, dict) and item.get("scene_id")
        }
        for location in location_by_id.values():
            location["scheduled_slots"] = []
        for scene in scene_by_id.values():
            scene["suggested_slots"] = []
        progression: list[dict[str, Any]] = []
        for entry in story_room.get("volume_map_schedule", []):
            if not isinstance(entry, dict):
                continue
            slot_id = str(entry.get("event_slot_id") or "")
            for location_id in entry.get("location_ids", []):
                scheduled_location = location_by_id.get(str(location_id))
                if (
                    scheduled_location is not None
                    and slot_id not in scheduled_location["scheduled_slots"]
                ):
                    scheduled_location["scheduled_slots"].append(slot_id)
            for scene_id in entry.get("scene_asset_ids", []):
                scheduled_scene = scene_by_id.get(str(scene_id))
                if (
                    scheduled_scene is not None
                    and slot_id not in scheduled_scene["suggested_slots"]
                ):
                    scheduled_scene["suggested_slots"].append(slot_id)
            for item in entry.get("character_progression", []):
                if isinstance(item, dict):
                    movement = deepcopy(item)
                    movement["event_slot_id"] = slot_id
                    progression.append(movement)
        map_system["map_and_character_progression"] = progression

    def run(self, inp: Graph3Input) -> Graph3Output:
        run_id = inp.run_id
        project_id = inp.project_id
        volume_index = inp.volume_index
        volume_id = f"vol_{volume_index:03d}"
        try:
            target_event_count = max(1, int(inp.events_per_volume or 30))
        except (TypeError, ValueError):
            target_event_count = 30

        # ── 3.1: volume_plan ───────────────────────────────────
        _logger.info(f"graph3_step volume_plan run={run_id} volume={volume_id}")
        plan_result = self._run_step(
            step_key="graph3.volume.plan",
            diagnostic_key="plan",
            input_pack={
                "longline_content": inp.longline.content,
                "volume_index": volume_index,
                "volume_id": volume_id,
                "carryover_context": inp.carryover_context or {},
                "complexity_profile": inp.complexity_profile or {},
                "target_event_count": target_event_count,
            },
            run_id=run_id,
            parsed_validator=lambda parsed: (
                isinstance(parsed, dict)
                and len(self._usable_event_slots(parsed)) == target_event_count
            ),
        )

        now = utcnow()
        plan_content: dict[str, Any] = {}
        if plan_result.ok and isinstance(plan_result.parsed, dict):
            plan_content = plan_result.parsed
        else:
            reason = (
                f"图3分卷规划未返回包含{target_event_count}个完整事件槽位的合法JSON；失败记录："
                f"{self._layout.run_failure_path(run_id, 'volume_plan').name}"
            )
            _logger.error(f"graph3_aborted_invalid_plan run={run_id} volume={volume_id}")
            return Graph3Output(aborted=True, abort_reason=reason)

        # Ensure volume_id is present in the content
        if "volume_id" not in plan_content:
            plan_content["volume_id"] = volume_id

        slots = self._usable_event_slots(plan_content)
        if len(slots) != target_event_count:
            reason = (
                f"图3分卷规划应生成{target_event_count}个事件槽位，实际只有{len(slots)}个，"
                "初始化已中止，未覆盖现有卷契约"
            )
            _logger.error(
                f"graph3_aborted_event_slot_count run={run_id} volume={volume_id} "
                f"expected={target_event_count} actual={len(slots)}"
            )
            return Graph3Output(aborted=True, abort_reason=reason)

        # ── 3.2: volume_story_room ────────────────────────────
        _logger.info(f"graph3_step volume_story_room run={run_id} volume={volume_id}")
        master_relationship_pairs = self._master_relationship_pairs(inp.longline.content)
        room_result = self._run_step(
            step_key="graph3.volume.story_room",
            diagnostic_key="story_room",
            input_pack={
                "longline_content": inp.longline.content,
                "volume_plan_content": plan_content,
                "carryover_context": inp.carryover_context or {},
                "complexity_profile": inp.complexity_profile or {},
            },
            run_id=run_id,
            parsed_validator=lambda parsed: self._valid_volume_story_room(
                parsed,
                expected_slot_ids={str(slot.get("slot_id")) for slot in slots},
                master_relationship_pairs=master_relationship_pairs,
            ),
        )
        if not room_result.ok or not self._valid_volume_story_room(
            room_result.parsed,
            expected_slot_ids={str(slot.get("slot_id")) for slot in slots},
            master_relationship_pairs=master_relationship_pairs,
        ):
            reason = "本卷故事核心未返回完整的卷弧、角色成长线和多维角色卡，卷规划已中止"
            _logger.error(f"graph3_aborted_invalid_story_room run={run_id} volume={volume_id}")
            return Graph3Output(aborted=True, abort_reason=reason)
        story_room = {
            key: room_result.parsed[key]
            for key in (
                "volume_story_engine",
                "volume_foreshadowing",
                "volume_character_arcs",
                "volume_cast_cards",
                "relationship_tracks",
                "volume_line_ledger",
                "entity_agendas",
                "key_item_tracks",
                "set_piece_plans",
                "transient_assets",
            )
            if key in room_result.parsed
        }

        # ── 3.3: volume_map_room ──────────────────────────────
        _logger.info(f"graph3_step volume_map_room run={run_id} volume={volume_id}")
        major_map_system = inp.longline.content.get("story_room", {}).get("major_map_system", {})
        allowed_parent_map_ids = (
            {
                str(item.get("map_id"))
                for item in major_map_system.get("major_regions", [])
                if isinstance(item, dict) and item.get("map_id")
            }
            if isinstance(major_map_system, dict)
            else set()
        )
        expected_slot_ids = {str(slot.get("slot_id")) for slot in slots}
        map_result = self._run_step(
            step_key="graph3.volume.map_room",
            diagnostic_key="map_room",
            input_pack={
                "longline_content": inp.longline.content,
                "volume_plan_content": plan_content,
                "volume_story_core": story_room,
                "carryover_context": inp.carryover_context or {},
                "complexity_profile": inp.complexity_profile or {},
            },
            run_id=run_id,
            parsed_validator=lambda parsed: (
                self._valid_volume_map_room(
                    parsed,
                    story_room=story_room,
                    expected_slot_ids=None,
                    allowed_parent_map_ids=allowed_parent_map_ids,
                )
                and bool(parsed.get("scene_assets"))
            ),
        )
        if (
            not map_result.ok
            or not self._valid_volume_map_room(
                map_result.parsed,
                story_room=story_room,
                expected_slot_ids=None,
                allowed_parent_map_ids=allowed_parent_map_ids,
            )
            or not map_result.parsed.get("scene_assets")
        ):
            reason = "本卷地图核心未返回引用一致的地点、路线与场景资产，卷规划已中止"
            _logger.error(f"graph3_aborted_invalid_map_room run={run_id} volume={volume_id}")
            return Graph3Output(aborted=True, abort_reason=reason)
        story_room["volume_map_system"] = map_result.parsed["volume_map_system"]
        story_room["scene_assets"] = map_result.parsed["scene_assets"]

        # ── 3.4: volume_map_schedule（逐批地图排期）────────────
        schedule_chunks = self._chunk_event_slots(slots)
        all_schedule: list[dict[str, Any]] = []
        map_room = self._map_room_payload(story_room)
        for chunk_index, chunk_slots in enumerate(schedule_chunks):
            chunk_ids = [str(slot.get("slot_id")) for slot in chunk_slots]
            schedule_result = self._run_step(
                step_key="graph3.volume.map_schedule",
                diagnostic_key=f"map_schedule_chunk_{chunk_index + 1}",
                input_pack={
                    "volume_id": volume_id,
                    "event_slots": chunk_slots,
                    "volume_story_core": {
                        "volume_story_engine": story_room.get("volume_story_engine", {}),
                        "volume_cast_cards": story_room.get("volume_cast_cards", []),
                    },
                    "volume_map_room": map_room,
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=run_id,
                parsed_validator=lambda parsed: self._valid_map_schedule(
                    parsed,
                    story_room=story_room,
                    map_room=map_room,
                    expected_slot_ids=chunk_ids,
                ),
            )
            if not schedule_result.ok or not self._valid_map_schedule(
                schedule_result.parsed,
                story_room=story_room,
                map_room=map_room,
                expected_slot_ids=chunk_ids,
            ):
                reason = (
                    f"地图排期第{chunk_index + 1}/{len(schedule_chunks)}批未逐槽覆盖，卷规划已中止"
                )
                _logger.error(
                    f"graph3_aborted_invalid_map_schedule run={run_id} volume={volume_id} "
                    f"chunk={chunk_index + 1}/{len(schedule_chunks)}"
                )
                return Graph3Output(aborted=True, abort_reason=reason)
            all_schedule.extend(schedule_result.parsed["map_schedule"])
        story_room["volume_map_schedule"] = all_schedule
        self._apply_volume_map_schedule(story_room)
        if not self._valid_volume_map_room(
            self._map_room_payload(story_room),
            story_room=story_room,
            expected_slot_ids=expected_slot_ids,
            allowed_parent_map_ids=allowed_parent_map_ids,
        ):
            reason = "地图排期合并后未覆盖全卷事件槽或存在无效引用，卷规划已中止"
            _logger.error(f"graph3_aborted_merged_map_schedule run={run_id} volume={volume_id}")
            return Graph3Output(aborted=True, abort_reason=reason)

        # ── 3.5: volume_event_designs ─────────────────────────
        _logger.info(f"graph3_step volume_event_designs run={run_id} volume={volume_id}")
        design_chunks = self._chunk_event_slots(slots)
        all_designs: list[dict[str, Any]] = []
        for chunk_index, chunk_slots in enumerate(design_chunks):
            chunk_ids = [str(slot.get("slot_id")) for slot in chunk_slots]
            first_index = slots.index(chunk_slots[0])
            last_index = first_index + len(chunk_slots) - 1
            scoped_plan = dict(plan_content)
            scoped_plan["event_slots"] = chunk_slots
            scoped_plan["event_design_scope"] = {
                "chunk_index": chunk_index + 1,
                "chunk_total": len(design_chunks),
                "previous_slot": slots[first_index - 1] if first_index > 0 else None,
                "next_slot": slots[last_index + 1] if last_index + 1 < len(slots) else None,
            }
            scoped_longline, scoped_story, scoped_map = self._scope_event_design_assets(
                longline_content=inp.longline.content,
                story_room=story_room,
                slot_ids=set(chunk_ids),
            )
            designs_result = self._run_step(
                step_key="graph3.volume.event_designs",
                diagnostic_key=f"event_designs_chunk_{chunk_index + 1}",
                input_pack={
                    "longline_content": scoped_longline,
                    "volume_plan_content": scoped_plan,
                    "volume_story_core": scoped_story,
                    "volume_map_room": scoped_map,
                    "complexity_profile": inp.complexity_profile or {},
                },
                run_id=run_id,
                parsed_validator=lambda parsed: self._valid_event_designs(
                    parsed,
                    story_room=story_room,
                    expected_slot_ids=chunk_ids,
                ),
            )
            if not designs_result.ok or not self._valid_event_designs(
                designs_result.parsed,
                story_room=story_room,
                expected_slot_ids=chunk_ids,
            ):
                reason = (
                    f"逐事件设计第{chunk_index + 1}/{len(design_chunks)}批未完整覆盖槽位，"
                    "或人物/地点/场景/伏笔ID引用无效，卷规划已中止"
                )
                _logger.error(
                    f"graph3_aborted_invalid_event_designs run={run_id} volume={volume_id} "
                    f"chunk={chunk_index + 1}/{len(design_chunks)}"
                )
                return Graph3Output(aborted=True, abort_reason=reason)
            all_designs.extend(designs_result.parsed["event_designs"])

        aggregated_designs = {"event_designs": all_designs}
        if not self._valid_event_designs(
            aggregated_designs,
            story_room=story_room,
            expected_slot_ids=list(expected_slot_ids),
        ):
            reason = "逐事件设计分批结果合并后未完整覆盖全卷槽位，卷规划已中止"
            _logger.error(f"graph3_aborted_merged_event_designs run={run_id} volume={volume_id}")
            return Graph3Output(aborted=True, abort_reason=reason)
        story_room["event_designs"] = all_designs
        plan_content["story_room"] = story_room
        self._merge_event_designs(plan_content, story_room)

        volume_contract = AuthObject(
            object_id=f"volume_{volume_id}",
            project_id=project_id,
            object_type=AuthObjectType.CONTRACT,
            version=1,
            content=plan_content,
            created_at=now,
            updated_at=now,
            committed_by_run_id=run_id,
        )
        if inp.commit:
            volume_contract = self._auth_store.commit(volume_contract)

        # ── 3.5: fatigue_report ────────────────────────────────
        _logger.info(f"graph3_step fatigue_report run={run_id} volume={volume_id}")
        fatigue_result = self._run_step(
            step_key="graph3.volume.fatigue_report",
            diagnostic_key="fatigue_report",
            input_pack={
                "volume_plan_content": plan_content,
                "volume_id": volume_id,
                "complexity_profile": inp.complexity_profile or {},
            },
            run_id=run_id,
        )

        fatigue_report = self._build_fatigue_report(fatigue_result.parsed, project_id, volume_id)

        receipt = CommitReceipt(
            receipt_id=new_receipt_id(),
            run_id=run_id,
            staging_id=f"stg_{volume_id}_{run_id}",
            commit_type="auth_patch",
            committed_objects=[f"volume_contract:{volume_id}"],
            committed_at=now,
        )

        _logger.info(f"graph3_done run={run_id} volume={volume_id}")
        return Graph3Output(
            volume_contract=volume_contract,
            fatigue_report=fatigue_report,
            commit_receipt=receipt,
        )

    @staticmethod
    def _usable_event_slots(plan_content: dict[str, Any]) -> list[dict[str, Any]]:
        raw_slots = plan_content.get("event_slots", [])
        if not isinstance(raw_slots, list) or not raw_slots:
            return []
        slots = [
            slot
            for slot in raw_slots
            if (
                isinstance(slot, dict)
                and str(slot.get("slot_id", "")).strip()
                and str(slot.get("event_goal", "")).strip()
            )
        ]
        slot_ids = [str(slot["slot_id"]).strip() for slot in slots]
        if len(slots) != len(raw_slots) or len(slot_ids) != len(set(slot_ids)):
            return []
        return slots

    @classmethod
    def _chunk_event_slots(cls, slots: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        return [
            slots[index : index + cls._EVENT_DESIGN_CHUNK_SIZE]
            for index in range(0, len(slots), cls._EVENT_DESIGN_CHUNK_SIZE)
        ]

    @staticmethod
    def _scope_event_design_assets(
        *,
        longline_content: dict[str, Any],
        story_room: dict[str, Any],
        slot_ids: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Project only the volume assets needed by one event-design chunk."""

        map_system = story_room.get("volume_map_system", {})
        locations = (
            [
                item
                for item in map_system.get("locations", [])
                if isinstance(item, dict)
                and bool(slot_ids & {str(value) for value in item.get("scheduled_slots", [])})
            ]
            if isinstance(map_system, dict)
            else []
        )
        location_ids = {str(item.get("location_id")) for item in locations}
        progression = (
            [
                item
                for item in map_system.get("map_and_character_progression", [])
                if isinstance(item, dict) and str(item.get("event_slot_id")) in slot_ids
            ]
            if isinstance(map_system, dict)
            else []
        )
        scene_assets = [
            item
            for item in story_room.get("scene_assets", [])
            if isinstance(item, dict)
            and (
                str(item.get("location_id")) in location_ids
                or bool(slot_ids & {str(value) for value in item.get("suggested_slots", [])})
            )
        ]

        selected_character_ids = {
            str(link.get("character_id"))
            for location in locations
            for link in location.get("character_connections", [])
            if isinstance(link, dict) and link.get("character_id")
        }
        selected_character_ids.update(
            str(item.get("character_id")) for item in progression if item.get("character_id")
        )

        foreshadowing = []
        for hook in story_room.get("volume_foreshadowing", []):
            if not isinstance(hook, dict):
                continue
            referenced_slots = {
                str(value)
                for value in [
                    *(
                        hook.get("plant_slots", [])
                        if isinstance(hook.get("plant_slots"), list)
                        else []
                    ),
                    *(
                        hook.get("reinforce_slots", [])
                        if isinstance(hook.get("reinforce_slots"), list)
                        else []
                    ),
                    hook.get("payoff_slot"),
                ]
                if value
            }
            if slot_ids & referenced_slots:
                foreshadowing.append(hook)
                selected_character_ids.update(
                    str(value) for value in hook.get("involved_character_ids", [])
                )

        arcs = []
        for arc in story_room.get("volume_character_arcs", []):
            if not isinstance(arc, dict):
                continue
            character_id = str(arc.get("character_id") or "")
            choice_slots = {
                str(choice.get("event_slot_id"))
                for choice in arc.get("key_choices", [])
                if isinstance(choice, dict)
            }
            if character_id in selected_character_ids or slot_ids & choice_slots:
                arcs.append(arc)
                if character_id:
                    selected_character_ids.add(character_id)

        relationships = []
        relationship_seed_character_ids = set(selected_character_ids)
        relationship_character_ids: set[str] = set()
        for relationship in story_room.get("relationship_tracks", []):
            if not isinstance(relationship, dict):
                continue
            relationship_ids = {str(value) for value in relationship.get("character_ids", [])}
            turn_slots = {str(value) for value in relationship.get("turn_slots", [])}
            if slot_ids & turn_slots or relationship_seed_character_ids & relationship_ids:
                relationships.append(relationship)
                relationship_character_ids.update(relationship_ids)
        selected_character_ids.update(relationship_character_ids)

        cast_cards = [
            item
            for item in story_room.get("volume_cast_cards", [])
            if isinstance(item, dict) and str(item.get("character_id")) in selected_character_ids
        ]
        routes = (
            [
                item
                for item in map_system.get("route_matrix", [])
                if isinstance(item, dict)
                and (
                    str(item.get("from_location_id")) in location_ids
                    or str(item.get("to_location_id")) in location_ids
                )
            ]
            if isinstance(map_system, dict)
            else []
        )

        def active_for_slots(items: object, *slot_fields: str) -> list[dict[str, Any]]:
            selected: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                referenced: set[str] = set()
                for field_name in slot_fields:
                    value = item.get(field_name, [])
                    if isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, dict) and entry.get("event_slot_id"):
                                referenced.add(str(entry["event_slot_id"]))
                            elif not isinstance(entry, dict):
                                referenced.add(str(entry))
                if slot_ids & referenced:
                    selected.append(item)
            return selected

        volume_lines = active_for_slots(story_room.get("volume_line_ledger"), "scheduled_movements")
        agendas = active_for_slots(story_room.get("entity_agendas"), "planned_actions")
        item_tracks = active_for_slots(story_room.get("key_item_tracks"), "event_movements")
        set_pieces = active_for_slots(story_room.get("set_piece_plans"), "event_slot_ids")
        transient_assets = active_for_slots(story_room.get("transient_assets"), "active_slot_ids")

        scoped_story = {
            "volume_story_engine": story_room.get("volume_story_engine", {}),
            "volume_foreshadowing": foreshadowing,
            "volume_character_arcs": arcs,
            "volume_cast_cards": cast_cards,
            "relationship_tracks": relationships,
            "volume_line_ledger": volume_lines,
            "entity_agendas": agendas,
            "key_item_tracks": item_tracks,
            "set_piece_plans": set_pieces,
            "transient_assets": transient_assets,
        }
        scoped_map_system = {
            "active_major_map_ids": map_system.get("active_major_map_ids", [])
            if isinstance(map_system, dict)
            else [],
            "volume_spatial_arc": map_system.get("volume_spatial_arc", "")
            if isinstance(map_system, dict)
            else "",
            "locations": locations,
            "route_matrix": routes,
            "spatial_continuity_rules": map_system.get("spatial_continuity_rules", [])
            if isinstance(map_system, dict)
            else [],
            "map_and_character_progression": progression,
        }
        scoped_map = {
            "volume_map_system": scoped_map_system,
            "scene_assets": scene_assets,
        }

        full_book_room = longline_content.get("story_room", {})
        selected_hook_ids = {str(item.get("hook_id")) for item in foreshadowing}
        selected_line_ids = {str(item.get("line_id")) for item in volume_lines}
        selected_item_ids = {
            str(item.get("source_arc_id") or item.get("item_id")) for item in item_tracks
        }
        selected_set_piece_ids = {
            str(item.get("source_seed_id") or item.get("set_piece_id")) for item in set_pieces
        }
        selected_relationship_ids = {
            str(item.get("relationship_id"))
            for item in relationships
            if isinstance(item, dict) and item.get("relationship_id")
        }
        scoped_book_room = {
            "master_story_design": full_book_room.get("master_story_design", {})
            if isinstance(full_book_room, dict)
            else {},
            "major_foreshadowing": [
                item
                for item in full_book_room.get("major_foreshadowing", [])
                if isinstance(item, dict) and str(item.get("hook_id")) in selected_hook_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "character_growth_arcs": [
                item
                for item in full_book_room.get("character_growth_arcs", [])
                if isinstance(item, dict)
                and str(item.get("character_id")) in selected_character_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "ensemble_relationship_index": [
                item
                for item in full_book_room.get("ensemble_relationship_index", [])
                if isinstance(item, dict)
                and str(item.get("relationship_id")) in selected_relationship_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "ensemble_relationship_arcs": [
                item
                for item in full_book_room.get("ensemble_relationship_arcs", [])
                if isinstance(item, dict)
                and str(item.get("relationship_id")) in selected_relationship_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "story_room_rules": full_book_room.get("story_room_rules", {})
            if isinstance(full_book_room, dict)
            else {},
            "narrative_line_registry": [
                item
                for item in full_book_room.get("narrative_line_registry", [])
                if isinstance(item, dict) and str(item.get("line_id")) in selected_line_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "key_item_arcs": [
                item
                for item in full_book_room.get("key_item_arcs", [])
                if isinstance(item, dict) and str(item.get("item_id")) in selected_item_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "major_set_piece_seeds": [
                item
                for item in full_book_room.get("major_set_piece_seeds", [])
                if isinstance(item, dict)
                and str(item.get("set_piece_id")) in selected_set_piece_ids
            ]
            if isinstance(full_book_room, dict)
            else [],
            "asset_lifecycle_policy": full_book_room.get("asset_lifecycle_policy", {})
            if isinstance(full_book_room, dict)
            else {},
        }
        scoped_longline = {
            key: value for key, value in longline_content.items() if key != "story_room"
        }
        scoped_longline["story_room"] = scoped_book_room
        return scoped_longline, scoped_story, scoped_map

    @staticmethod
    def _valid_volume_story_room(
        parsed: object,
        *,
        expected_slot_ids: set[str] | None = None,
        master_relationship_pairs: dict[str, tuple[str, str]] | None = None,
    ) -> bool:
        if not isinstance(parsed, dict):
            return False
        base_valid = (
            isinstance(parsed.get("volume_story_engine"), dict)
            and isinstance(parsed.get("volume_foreshadowing"), list)
            and isinstance(parsed.get("volume_character_arcs"), list)
            and bool(parsed.get("volume_character_arcs"))
            and isinstance(parsed.get("volume_cast_cards"), list)
            and bool(parsed.get("volume_cast_cards"))
            and isinstance(parsed.get("relationship_tracks"), list)
            and isinstance(parsed.get("volume_line_ledger"), list)
            and bool(parsed.get("volume_line_ledger"))
            and isinstance(parsed.get("entity_agendas"), list)
            and bool(parsed.get("entity_agendas"))
            and isinstance(parsed.get("key_item_tracks"), list)
            and isinstance(parsed.get("set_piece_plans"), list)
            and isinstance(parsed.get("transient_assets"), list)
        )
        if not base_valid:
            return False
        cast_ids = [
            str(item.get("character_id") or "").strip()
            for item in parsed["volume_cast_cards"]
            if isinstance(item, dict)
        ]
        arc_ids = [
            str(item.get("character_id") or "").strip()
            for item in parsed["volume_character_arcs"]
            if isinstance(item, dict)
        ]
        hook_ids = [
            str(item.get("hook_id") or "").strip()
            for item in parsed["volume_foreshadowing"]
            if isinstance(item, dict)
        ]
        if (
            len(cast_ids) != len(parsed["volume_cast_cards"])
            or len(arc_ids) != len(parsed["volume_character_arcs"])
            or len(hook_ids) != len(parsed["volume_foreshadowing"])
            or any(not value for value in [*cast_ids, *arc_ids, *hook_ids])
        ):
            return False
        if not (
            len(cast_ids) == len(set(cast_ids))
            and len(arc_ids) == len(set(arc_ids))
            and len(hook_ids) == len(set(hook_ids))
            and set(arc_ids) <= set(cast_ids)
        ):
            return False
        known_characters = set(cast_ids)
        for hook in parsed["volume_foreshadowing"]:
            involved = hook.get("involved_character_ids", [])
            plant_slots = hook.get("plant_slots", [])
            reinforce_slots = hook.get("reinforce_slots", [])
            if not isinstance(involved, list) or not set(map(str, involved)) <= known_characters:
                return False
            if expected_slot_ids is not None and (
                not isinstance(plant_slots, list)
                or not isinstance(reinforce_slots, list)
                or not set(map(str, [*plant_slots, *reinforce_slots])) <= expected_slot_ids
            ):
                return False
        for arc in parsed["volume_character_arcs"]:
            choices = arc.get("key_choices", [])
            if not isinstance(choices, list):
                return False
            if expected_slot_ids is not None and any(
                not isinstance(choice, dict)
                or str(choice.get("event_slot_id")) not in expected_slot_ids
                for choice in choices
            ):
                return False
        for relationship in parsed["relationship_tracks"]:
            relationship_id = (
                str(relationship.get("relationship_id") or "").strip()
                if isinstance(relationship, dict)
                else ""
            )
            character_ids = (
                relationship.get("character_ids", []) if isinstance(relationship, dict) else []
            )
            turn_slots = (
                relationship.get("turn_slots", []) if isinstance(relationship, dict) else []
            )
            if (
                not relationship_id
                or not isinstance(character_ids, list)
                or len(character_ids) != 2
                or len(set(map(str, character_ids))) != 2
                or not set(map(str, character_ids)) <= known_characters
            ):
                return False
            if expected_slot_ids is not None and (
                not isinstance(turn_slots, list)
                or not set(map(str, turn_slots)) <= expected_slot_ids
            ):
                return False
        relationship_ids = [
            str(item.get("relationship_id") or "").strip()
            for item in parsed["relationship_tracks"]
            if isinstance(item, dict)
        ]
        relationship_pairs = [
            tuple(sorted(map(str, item.get("character_ids", []))))
            for item in parsed["relationship_tracks"]
            if isinstance(item, dict)
        ]
        if (
            len(relationship_ids) != len(parsed["relationship_tracks"])
            or len(relationship_ids) != len(set(relationship_ids))
            or len(relationship_pairs) != len(set(relationship_pairs))
        ):
            return False
        if master_relationship_pairs:
            for relationship_id, pair in zip(relationship_ids, relationship_pairs):
                if relationship_id in master_relationship_pairs:
                    if pair != master_relationship_pairs[relationship_id]:
                        return False
                elif not relationship_id.startswith("vol_rel_"):
                    return False
        lifecycle_specs = (
            ("volume_line_ledger", "line_id"),
            ("entity_agendas", "agenda_id"),
            ("key_item_tracks", "item_id"),
            ("set_piece_plans", "set_piece_id"),
            ("transient_assets", "asset_id"),
        )
        for field_name, id_key in lifecycle_specs:
            values = parsed[field_name]
            ids = [str(item.get(id_key) or "").strip() for item in values if isinstance(item, dict)]
            if (
                len(ids) != len(values)
                or any(not value for value in ids)
                or len(ids) != len(set(ids))
            ):
                return False
        if expected_slot_ids is not None:
            for field_name in ("volume_line_ledger", "entity_agendas", "key_item_tracks"):
                for item in parsed[field_name]:
                    movements = item.get(
                        "scheduled_movements",
                        item.get("planned_actions", item.get("event_movements", [])),
                    )
                    if not isinstance(movements, list) or any(
                        not isinstance(movement, dict)
                        or str(movement.get("event_slot_id")) not in expected_slot_ids
                        for movement in movements
                    ):
                        return False
            for item in parsed["set_piece_plans"]:
                if not set(map(str, item.get("event_slot_ids", []))) <= expected_slot_ids:
                    return False
            for item in parsed["transient_assets"]:
                if not set(map(str, item.get("active_slot_ids", []))) <= expected_slot_ids:
                    return False
        return True

    @staticmethod
    def _master_relationship_pairs(
        longline_content: dict[str, Any],
    ) -> dict[str, tuple[str, str]]:
        room = longline_content.get("story_room", {})
        if not isinstance(room, dict):
            return {}
        arcs = room.get("ensemble_relationship_arcs", [])
        pairs: dict[str, tuple[str, str]] = {}
        for arc in arcs if isinstance(arcs, list) else []:
            if not isinstance(arc, dict):
                continue
            relationship_id = str(arc.get("relationship_id") or "").strip()
            character_ids = arc.get("character_ids", [])
            if relationship_id and isinstance(character_ids, list) and len(character_ids) == 2:
                pairs[relationship_id] = (
                    min(map(str, character_ids)),
                    max(map(str, character_ids)),
                )
        return pairs

    @staticmethod
    def _valid_volume_map_room(
        parsed: object,
        *,
        story_room: dict[str, Any] | None = None,
        expected_slot_ids: set[str] | None = None,
        allowed_parent_map_ids: set[str] | None = None,
    ) -> bool:
        if not isinstance(parsed, dict):
            return False
        map_system = parsed.get("volume_map_system")
        if not isinstance(map_system, dict):
            return False
        locations = map_system.get("locations")
        scenes = parsed.get("scene_assets")
        if not isinstance(locations, list) or not locations or not isinstance(scenes, list):
            return False
        location_ids = [
            str(item.get("location_id") or "").strip()
            for item in locations
            if isinstance(item, dict)
        ]
        if len(location_ids) != len(locations) or any(not value for value in location_ids):
            return False
        if len(location_ids) != len(set(location_ids)):
            return False
        known_locations = set(location_ids)
        active_major_maps = map_system.get("active_major_map_ids", [])
        if not isinstance(active_major_maps, list):
            return False
        if (
            allowed_parent_map_ids
            and not set(map(str, active_major_maps)) <= allowed_parent_map_ids
        ):
            return False
        known_characters = {
            str(item.get("character_id"))
            for item in (story_room or {}).get("volume_cast_cards", [])
            if isinstance(item, dict) and item.get("character_id")
        }
        scheduled_union: set[str] = set()
        for location in locations:
            parent_id = str(location.get("parent_map_id") or "").strip()
            scheduled = location.get("scheduled_slots")
            if allowed_parent_map_ids and parent_id not in allowed_parent_map_ids:
                return False
            if expected_slot_ids is not None and (
                not isinstance(scheduled, list) or not set(map(str, scheduled)) <= expected_slot_ids
            ):
                return False
            if isinstance(scheduled, list):
                scheduled_union.update(map(str, scheduled))
            connections = location.get("character_connections", [])
            if not isinstance(connections, list) or (known_characters and not connections):
                return False
            if known_characters and any(
                not isinstance(item, dict) or str(item.get("character_id")) not in known_characters
                for item in connections
            ):
                return False
        if expected_slot_ids is not None and scheduled_union != expected_slot_ids:
            return False
        scene_ids: list[str] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                return False
            scene_id = str(scene.get("scene_id") or "").strip()
            location_id = str(scene.get("location_id") or "").strip()
            if not scene_id or location_id not in known_locations:
                return False
            suggested = scene.get("suggested_slots")
            if expected_slot_ids is not None and (
                not isinstance(suggested, list) or not set(map(str, suggested)) <= expected_slot_ids
            ):
                return False
            scene_ids.append(scene_id)
        if len(scene_ids) != len(set(scene_ids)):
            return False
        routes = map_system.get("route_matrix", [])
        if not isinstance(routes, list) or any(
            not isinstance(route, dict)
            or str(route.get("from_location_id")) not in known_locations
            or str(route.get("to_location_id")) not in known_locations
            for route in routes
        ):
            return False
        progression = map_system.get("map_and_character_progression", [])
        if not isinstance(progression, list):
            return False
        if not all(
            isinstance(item, dict)
            and str(item.get("location_id")) in known_locations
            and (not known_characters or str(item.get("character_id")) in known_characters)
            and (expected_slot_ids is None or str(item.get("event_slot_id")) in expected_slot_ids)
            for item in progression
        ):
            return False
        if expected_slot_ids is not None:
            progression_slots = {str(item.get("event_slot_id")) for item in progression}
            if progression_slots != expected_slot_ids:
                return False
        return True

    @staticmethod
    def _valid_event_designs(
        parsed: object,
        *,
        story_room: dict[str, Any],
        expected_slot_ids: list[str],
    ) -> bool:
        if not isinstance(parsed, dict) or not isinstance(parsed.get("event_designs"), list):
            return False
        designs = parsed["event_designs"]
        design_ids = [
            str(item.get("slot_id") or "").strip() for item in designs if isinstance(item, dict)
        ]
        if len(design_ids) != len(designs) or len(design_ids) != len(set(design_ids)):
            return False
        if set(design_ids) != set(expected_slot_ids):
            return False

        cast_ids = {
            str(item.get("character_id"))
            for item in story_room.get("volume_cast_cards", [])
            if isinstance(item, dict)
        }
        map_system = story_room.get("volume_map_system", {})
        location_ids = (
            {
                str(item.get("location_id"))
                for item in map_system.get("locations", [])
                if isinstance(item, dict)
            }
            if isinstance(map_system, dict)
            else set()
        )
        scene_ids = {
            str(item.get("scene_id"))
            for item in story_room.get("scene_assets", [])
            if isinstance(item, dict)
        }
        hook_ids = {
            str(item.get("hook_id"))
            for item in story_room.get("volume_foreshadowing", [])
            if isinstance(item, dict)
        }
        relationship_ids = {
            str(item.get("relationship_id"))
            for item in story_room.get("relationship_tracks", [])
            if isinstance(item, dict) and item.get("relationship_id")
        }

        for design in designs:
            if not isinstance(design, dict):
                return False
            characters = design.get("character_focus_ids")
            locations = design.get("location_ids")
            scenes = design.get("scene_asset_ids")
            hooks = design.get("foreshadowing_ids")
            relationships = design.get("relationship_ids", [])
            if not str(design.get("dramatic_center") or design.get("chapter_center") or "").strip():
                return False
            if not str(design.get("reader_payoff") or "").strip():
                return False
            if not str(design.get("surface_goal") or "").strip():
                return False
            if not str(design.get("ending_requirement") or "").strip():
                return False
            if (
                not isinstance(design.get("content_must_include"), list)
                or not design["content_must_include"]
            ):
                return False
            if not isinstance(characters, list) or not 1 <= len(characters) <= 4:
                return False
            if not isinstance(locations, list) or not 1 <= len(locations) <= 3:
                return False
            if not isinstance(scenes, list) or len(scenes) > 3:
                return False
            if not isinstance(hooks, list) or len(hooks) > 4:
                return False
            if not isinstance(relationships, list) or len(relationships) > 3:
                return False
            for values in (characters, locations, scenes, hooks, relationships):
                normalized = list(map(str, values))
                if len(normalized) != len(set(normalized)):
                    return False
            if not set(map(str, characters)) <= cast_ids:
                return False
            if not set(map(str, locations)) <= location_ids:
                return False
            if not set(map(str, scenes)) <= scene_ids:
                return False
            if not set(map(str, hooks)) <= hook_ids:
                return False
            if not set(map(str, relationships)) <= relationship_ids:
                return False
            relationship_actions = design.get("relationship_actions", [])
            if not isinstance(relationship_actions, list) or any(
                not isinstance(item, dict)
                or str(item.get("relationship_id")) not in set(map(str, relationships))
                for item in relationship_actions
            ):
                return False
            reference_specs = (
                ("active_line_ids", "volume_line_ledger", "line_id"),
                ("entity_agenda_ids", "entity_agendas", "agenda_id"),
                ("item_track_ids", "key_item_tracks", "item_id"),
                ("transient_asset_ids", "transient_assets", "asset_id"),
            )
            for design_field, room_field, id_key in reference_specs:
                values = design.get(design_field, [])
                known_ids = {
                    str(item.get(id_key))
                    for item in story_room.get(room_field, [])
                    if isinstance(item, dict)
                }
                if not isinstance(values, list) or not set(map(str, values)) <= known_ids:
                    return False
            set_piece_id = design.get("set_piece_id")
            known_set_pieces = {
                str(item.get("set_piece_id"))
                for item in story_room.get("set_piece_plans", [])
                if isinstance(item, dict)
            }
            if set_piece_id and str(set_piece_id) not in known_set_pieces:
                return False
            character_goals = design.get("character_scene_goals", [])
            growth_actions = design.get("growth_actions", [])
            foreshadow_actions = design.get("foreshadow_actions", [])
            if not isinstance(character_goals, list) or any(
                not isinstance(item, dict)
                or str(item.get("character_id")) not in set(map(str, characters))
                for item in character_goals
            ):
                return False
            if not isinstance(growth_actions, list) or any(
                not isinstance(item, dict)
                or str(item.get("character_id")) not in set(map(str, characters))
                for item in growth_actions
            ):
                return False
            if not isinstance(foreshadow_actions, list) or any(
                not isinstance(item, dict) or str(item.get("hook_id")) not in set(map(str, hooks))
                for item in foreshadow_actions
            ):
                return False
            if {str(item.get("character_id")) for item in character_goals} != set(
                map(str, characters)
            ):
                return False
            if {str(item.get("hook_id")) for item in foreshadow_actions} != set(map(str, hooks)):
                return False
        return True

    @staticmethod
    def _merge_event_designs(plan_content: dict[str, Any], story_room: dict[str, Any]) -> None:
        designs = {
            str(item.get("slot_id")): item
            for item in story_room.get("event_designs", [])
            if isinstance(item, dict) and item.get("slot_id")
        }
        for slot in plan_content.get("event_slots", []):
            if not isinstance(slot, dict):
                continue
            design = designs.get(str(slot.get("slot_id")))
            if design:
                chapter_design = dict(design)
                if "chapter_center" not in chapter_design and chapter_design.get("dramatic_center"):
                    chapter_design["chapter_center"] = chapter_design["dramatic_center"]
                chapter_design["reading_assets"] = Graph3._resolve_reading_assets(
                    story_room=story_room,
                    slot_id=str(slot.get("slot_id") or ""),
                    design=chapter_design,
                )
                slot["chapter_design"] = chapter_design

    @staticmethod
    def _resolve_reading_assets(
        *,
        story_room: dict[str, Any],
        slot_id: str,
        design: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve explicit chapter references into a compact, traceable asset pack."""

        def referenced_ids(field: str) -> list[str]:
            values = design.get(field, [])
            if not isinstance(values, list):
                return []
            return [str(value) for value in values if str(value).strip()]

        def select_by_id(
            items: object,
            id_key: str,
            ids: list[str],
        ) -> list[dict[str, Any]]:
            if not isinstance(items, list):
                return []
            wanted = set(ids)
            selected: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get(id_key) or "")
                if item_id in wanted:
                    selected.append(item)
            return selected

        character_ids = referenced_ids("character_focus_ids")
        location_ids = referenced_ids("location_ids")
        scene_ids = referenced_ids("scene_asset_ids")
        hook_ids = referenced_ids("foreshadowing_ids")
        line_ids = referenced_ids("active_line_ids")
        agenda_ids = referenced_ids("entity_agenda_ids")
        item_ids = referenced_ids("item_track_ids")
        transient_ids = referenced_ids("transient_asset_ids")
        relationship_ids = referenced_ids("relationship_ids")

        cast_cards = select_by_id(
            story_room.get("volume_cast_cards"),
            "character_id",
            character_ids,
        )
        character_arcs = select_by_id(
            story_room.get("volume_character_arcs"),
            "character_id",
            character_ids,
        )
        map_system = story_room.get("volume_map_system", {})
        locations = select_by_id(
            map_system.get("locations") if isinstance(map_system, dict) else [],
            "location_id",
            location_ids,
        )
        scene_assets = select_by_id(
            story_room.get("scene_assets"),
            "scene_id",
            scene_ids,
        )
        foreshadowing = select_by_id(
            story_room.get("volume_foreshadowing"),
            "hook_id",
            hook_ids,
        )
        narrative_lines = select_by_id(story_room.get("volume_line_ledger"), "line_id", line_ids)
        entity_agendas = select_by_id(story_room.get("entity_agendas"), "agenda_id", agenda_ids)
        key_item_tracks = select_by_id(story_room.get("key_item_tracks"), "item_id", item_ids)
        transient_assets = select_by_id(
            story_room.get("transient_assets"), "asset_id", transient_ids
        )
        relationship_tracks = select_by_id(
            story_room.get("relationship_tracks"),
            "relationship_id",
            relationship_ids,
        )
        set_piece_ids = [str(design.get("set_piece_id"))] if design.get("set_piece_id") else []
        set_piece_plans = select_by_id(
            story_room.get("set_piece_plans"), "set_piece_id", set_piece_ids
        )

        selected_locations = {str(item.get("location_id")) for item in locations}
        routes: list[dict[str, Any]] = []
        progression: list[dict[str, Any]] = []
        if isinstance(map_system, dict):
            routes = [
                item
                for item in map_system.get("route_matrix", [])
                if isinstance(item, dict)
                and (
                    str(item.get("from_location_id")) in selected_locations
                    or str(item.get("to_location_id")) in selected_locations
                )
            ][:6]
            progression = [
                item
                for item in map_system.get("map_and_character_progression", [])
                if isinstance(item, dict) and str(item.get("event_slot_id")) == slot_id
            ][:6]

        return {
            "character_cards": cast_cards,
            "character_arcs": character_arcs,
            "locations": locations,
            "routes": routes,
            "map_character_progression": progression,
            "scene_assets": scene_assets,
            "foreshadowing": foreshadowing,
            "relationship_tracks": relationship_tracks,
            "narrative_lines": narrative_lines,
            "entity_agendas": entity_agendas,
            "key_item_tracks": key_item_tracks,
            "set_piece_plans": set_piece_plans,
            "transient_assets": transient_assets,
        }

    @staticmethod
    def _build_fatigue_report(parsed: object, project_id: str, volume_id: str) -> FatigueReport:
        now = utcnow()
        base = {
            "report_id": new_report_id(),
            "project_id": project_id,
            "volume_id": volume_id,
            "generated_at": now,
        }
        if isinstance(parsed, dict):
            # Merge LLM output, but keep required base fields
            merged = {**parsed, **base}
            try:
                return FatigueReport.model_validate(merged)
            except Exception:
                pass
        return FatigueReport(
            report_id=str(base["report_id"]),
            project_id=project_id,
            volume_id=volume_id,
            generated_at=now,
        )
