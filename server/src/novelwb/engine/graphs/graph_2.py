"""图2 — 全书长线规划。

交互工作台按逻辑文件逐步生成和审核：长线骨架、总纲、伏笔、逐角色
成长弧、群像关系、故事线、物品、大场面、资产规则和全书地图。后一步
只读取已经批准并写入 ``longline`` 权威历史的前序文件。
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novelwb.core.constants import AuthObjectType
from novelwb.core.schemas.domain_models import AuthObject
from novelwb.core.schemas.patch_models import CommitReceipt
from novelwb.engine.step_runner import GraphDeps, PipelineCancelled, StepRunner
from novelwb.storage import AuthStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_receipt_id
from novelwb.utils.io_atomic import atomic_write_json
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow

_logger = get_logger(__name__)


@dataclass(frozen=True)
class MasterPlanStep:
    step_id: str
    label: str
    asset_id: str
    kind: str
    field: str = ""
    output_key: str = ""
    character_id: str = ""
    relationship_id: str = ""
    character_ids: tuple[str, str] = ("", "")
    entry_id: str = ""
    token_budget_low: int = 4000
    token_budget_medium: int = 6000
    token_budget_high: int = 8000

    def max_tokens(self, level: str) -> int:
        if level == "low":
            return self.token_budget_low
        if level == "high":
            return self.token_budget_high
        return self.token_budget_medium


_LONG_LINE = MasterPlanStep(
    "longline_core",
    "长线骨架",
    "master.longline_core",
    "longline",
    token_budget_low=7000,
    token_budget_medium=9000,
    token_budget_high=12000,
)
_MASTER_DESIGN = MasterPlanStep(
    "master_story_design",
    "全书故事设计",
    "master.story.master_story_design",
    "story_field",
    "master_story_design",
    "master_story_design",
    token_budget_low=6000,
    token_budget_medium=8000,
    token_budget_high=10000,
)
_FORESHADOWING = MasterPlanStep(
    "major_foreshadowing",
    "主要伏笔",
    "master.story.major_foreshadowing",
    "story_field",
    "major_foreshadowing",
    "major_foreshadowing",
    token_budget_low=5000,
    token_budget_medium=7000,
    token_budget_high=10000,
)
_RELATION_INDEX = MasterPlanStep(
    "ensemble_relationship_index",
    "核心关系索引",
    "master.story.ensemble_relationship_index",
    "relationship_index",
    "ensemble_relationship_index",
    "ensemble_relationship_index",
    token_budget_low=2500,
    token_budget_medium=3500,
    token_budget_high=5000,
)
_LINE_INDEX = MasterPlanStep(
    "narrative_line_index",
    "故事线索引",
    "master.story.narrative_line_index",
    "narrative_line_index",
    "narrative_line_index",
    "narrative_line_index",
    token_budget_low=2200,
    token_budget_medium=3000,
    token_budget_high=4000,
)
_ITEM_INDEX = MasterPlanStep(
    "key_item_index",
    "关键物品索引",
    "master.story.key_item_index",
    "key_item_index",
    "key_item_index",
    "key_item_index",
    token_budget_low=1800,
    token_budget_medium=2500,
    token_budget_high=3500,
)
_SET_PIECE_INDEX = MasterPlanStep(
    "major_set_piece_index",
    "大场面索引",
    "master.story.major_set_piece_index",
    "set_piece_index",
    "major_set_piece_index",
    "major_set_piece_index",
    token_budget_low=1800,
    token_budget_medium=2500,
    token_budget_high=3500,
)
_FINAL_STEPS: tuple[MasterPlanStep, ...] = (
    MasterPlanStep(
        "asset_lifecycle_policy",
        "资产生命周期策略",
        "master.story.asset_lifecycle_policy",
        "story_field",
        "asset_lifecycle_policy",
        "asset_lifecycle_policy",
        token_budget_low=3000,
        token_budget_medium=4000,
        token_budget_high=5000,
    ),
    MasterPlanStep(
        "entity_autonomy_rules",
        "实体自治规则",
        "master.story.entity_autonomy_rules",
        "story_field",
        "entity_autonomy_rules",
        "entity_autonomy_rules",
        token_budget_low=3000,
        token_budget_medium=4000,
        token_budget_high=5000,
    ),
    MasterPlanStep(
        "story_room_rules",
        "StoryRoom继承规则",
        "master.story.story_room_rules",
        "story_field",
        "story_room_rules",
        "story_room_rules",
        token_budget_low=3000,
        token_budget_medium=4000,
        token_budget_high=5000,
    ),
    MasterPlanStep(
        "major_map_system",
        "全书主要地图",
        "master.map.major_map_system",
        "map",
        "major_map_system",
        "major_map_system",
        token_budget_low=8000,
        token_budget_medium=10000,
        token_budget_high=12000,
    ),
)


def master_plan_steps(
    cast_content: dict[str, Any] | None,
    master_content: dict[str, Any] | None = None,
) -> list[MasterPlanStep]:
    """Return fixed files plus dynamic character and relationship arc files."""
    steps = [_LONG_LINE, _MASTER_DESIGN, _FORESHADOWING]
    characters = (cast_content or {}).get("characters", [])
    names: dict[str, str] = {}
    if isinstance(characters, list):
        for index, character in enumerate(characters, start=1):
            if not isinstance(character, dict):
                continue
            character_id = str(character.get("id") or "").strip()
            if not character_id:
                continue
            name = str(character.get("name") or character_id)
            names[character_id] = name
            steps.append(
                MasterPlanStep(
                    step_id=f"character_growth_arc:{character_id}",
                    label=f"人物成长弧：{name}",
                    asset_id=f"master.story.character_growth_arcs.{_slug(character_id)}",
                    kind="character_arc",
                    field="character_growth_arcs",
                    output_key="character_growth_arc",
                    character_id=character_id,
                    token_budget_low=3000,
                    token_budget_medium=4000,
                    token_budget_high=5000,
                )
            )
    steps.append(_RELATION_INDEX)
    room = (master_content or {}).get("story_room", {})
    room = room if isinstance(room, dict) else {}
    relation_index = room.get("ensemble_relationship_index")
    if not isinstance(relation_index, list):
        # Backward compatibility: an old completed collection acts as its own
        # index so existing projects do not become incomplete after migration.
        relation_index = room.get("ensemble_relationship_arcs", [])
    if isinstance(relation_index, list):
        for index, relation in enumerate(relation_index, start=1):
            if not isinstance(relation, dict):
                continue
            relationship_id = str(relation.get("relationship_id") or "").strip()
            ids = relation.get("character_ids", [])
            if not relationship_id or not isinstance(ids, list) or len(ids) != 2:
                continue
            left, right = str(ids[0]), str(ids[1])
            label = str(
                relation.get("name") or f"{names.get(left, left)} ↔ {names.get(right, right)}"
            )
            steps.append(
                MasterPlanStep(
                    step_id=f"ensemble_relationship_arc:{relationship_id}",
                    label=f"关系弧：{label}",
                    asset_id=f"master.story.ensemble_relationship_arcs.{_slug(relationship_id)}",
                    kind="relationship_arc",
                    field="ensemble_relationship_arcs",
                    output_key="ensemble_relationship_arc",
                    relationship_id=relationship_id,
                    character_ids=(left, right),
                    token_budget_low=2500,
                    token_budget_medium=3500,
                    token_budget_high=4500,
                )
            )
    steps.append(_LINE_INDEX)
    line_index = room.get("narrative_line_index")
    if not isinstance(line_index, list):
        line_index = room.get("narrative_line_registry", [])
    for line in line_index if isinstance(line_index, list) else []:
        if not isinstance(line, dict):
            continue
        line_id = str(line.get("line_id") or "").strip()
        if not line_id:
            continue
        label = str(line.get("name") or line_id)
        steps.append(
            MasterPlanStep(
                step_id=f"narrative_line:{line_id}",
                label=f"故事线：{label}",
                asset_id=f"master.story.narrative_line_registry.{_slug(line_id)}",
                kind="narrative_line",
                field="narrative_line_registry",
                output_key="narrative_line",
                entry_id=line_id,
                token_budget_low=2800,
                token_budget_medium=3800,
                token_budget_high=5000,
            )
        )

    steps.append(_ITEM_INDEX)
    item_index = room.get("key_item_index")
    if not isinstance(item_index, list):
        item_index = room.get("key_item_arcs", [])
    for item in item_index if isinstance(item_index, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            continue
        label = str(item.get("name") or item_id)
        steps.append(
            MasterPlanStep(
                step_id=f"key_item_arc:{item_id}",
                label=f"关键物品弧：{label}",
                asset_id=f"master.story.key_item_arcs.{_slug(item_id)}",
                kind="key_item_arc",
                field="key_item_arcs",
                output_key="key_item_arc",
                entry_id=item_id,
                token_budget_low=2400,
                token_budget_medium=3200,
                token_budget_high=4300,
            )
        )

    steps.append(_SET_PIECE_INDEX)
    set_piece_index = room.get("major_set_piece_index")
    if not isinstance(set_piece_index, list):
        set_piece_index = room.get("major_set_piece_seeds", [])
    for set_piece in set_piece_index if isinstance(set_piece_index, list) else []:
        if not isinstance(set_piece, dict):
            continue
        set_piece_id = str(set_piece.get("set_piece_id") or "").strip()
        if not set_piece_id:
            continue
        label = str(set_piece.get("name") or set_piece_id)
        steps.append(
            MasterPlanStep(
                step_id=f"major_set_piece_seed:{set_piece_id}",
                label=f"大场面：{label}",
                asset_id=f"master.story.major_set_piece_seeds.{_slug(set_piece_id)}",
                kind="set_piece_seed",
                field="major_set_piece_seeds",
                output_key="major_set_piece_seed",
                entry_id=set_piece_id,
                token_budget_low=2600,
                token_budget_medium=3500,
                token_budget_high=4700,
            )
        )

    steps.extend(_FINAL_STEPS)
    return steps


def master_plan_step_complete(content: dict[str, Any], step: MasterPlanStep) -> bool:
    room = content.get("story_room", {})
    if not isinstance(room, dict):
        room = {}
    if step.kind == "longline":
        return bool(content.get("dq_promise")) and isinstance(content.get("stage_nodes"), list)
    if step.kind == "character_arc":
        arcs = room.get("character_growth_arcs", [])
        return isinstance(arcs, list) and any(
            isinstance(item, dict) and str(item.get("character_id")) == step.character_id
            for item in arcs
        )
    if step.kind == "relationship_index":
        index = room.get("ensemble_relationship_index")
        legacy_arcs = room.get("ensemble_relationship_arcs")
        return (isinstance(index, list) and bool(index)) or (
            isinstance(legacy_arcs, list) and bool(legacy_arcs)
        )
    if step.kind == "relationship_arc":
        arcs = room.get("ensemble_relationship_arcs", [])
        return isinstance(arcs, list) and any(
            isinstance(item, dict) and str(item.get("relationship_id")) == step.relationship_id
            for item in arcs
        )
    index_fields = {
        "narrative_line_index": ("narrative_line_index", "narrative_line_registry"),
        "key_item_index": ("key_item_index", "key_item_arcs"),
        "set_piece_index": ("major_set_piece_index", "major_set_piece_seeds"),
    }
    if step.kind in index_fields:
        index_field, legacy_field = index_fields[step.kind]
        index = room.get(index_field)
        legacy = room.get(legacy_field)
        return (isinstance(index, list) and bool(index)) or (
            isinstance(legacy, list) and bool(legacy)
        )
    collection_specs = {
        "narrative_line": ("narrative_line_registry", "line_id"),
        "key_item_arc": ("key_item_arcs", "item_id"),
        "set_piece_seed": ("major_set_piece_seeds", "set_piece_id"),
    }
    if step.kind in collection_specs:
        collection_field, identity_field = collection_specs[step.kind]
        items = room.get(collection_field, [])
        return isinstance(items, list) and any(
            isinstance(item, dict) and str(item.get(identity_field)) == step.entry_id
            for item in items
        )
    return step.field in room


def next_master_plan_step(
    content: dict[str, Any],
    cast_content: dict[str, Any] | None,
) -> MasterPlanStep | None:
    return next(
        (
            step
            for step in master_plan_steps(cast_content, content)
            if not master_plan_step_complete(content, step)
        ),
        None,
    )


def merge_master_plan_step(
    content: dict[str, Any],
    step: MasterPlanStep,
    generated: Any,
) -> dict[str, Any]:
    """Merge one approved logical file without granting it sibling ownership."""
    merged = deepcopy(content)
    if step.kind == "longline":
        room = (
            deepcopy(merged.get("story_room"))
            if isinstance(merged.get("story_room"), dict)
            else None
        )
        merged = deepcopy(generated)
        if room is not None:
            merged["story_room"] = room
        return merged

    room = merged.setdefault("story_room", {})
    if not isinstance(room, dict):
        room = {}
        merged["story_room"] = room
    collection_specs = {
        "character_arc": ("character_growth_arcs", "character_id", step.character_id),
        "relationship_arc": (
            "ensemble_relationship_arcs",
            "relationship_id",
            step.relationship_id,
        ),
        "narrative_line": ("narrative_line_registry", "line_id", step.entry_id),
        "key_item_arc": ("key_item_arcs", "item_id", step.entry_id),
        "set_piece_seed": ("major_set_piece_seeds", "set_piece_id", step.entry_id),
    }
    if step.kind in collection_specs:
        collection_field, identity_field, identity_value = collection_specs[step.kind]
        arcs = room.get(collection_field, [])
        arcs = list(arcs) if isinstance(arcs, list) else []
        replacement = deepcopy(generated)
        position = next(
            (
                index
                for index, item in enumerate(arcs)
                if isinstance(item, dict) and str(item.get(identity_field)) == identity_value
            ),
            None,
        )
        if position is None:
            arcs.append(replacement)
        else:
            arcs[position] = replacement
        room[collection_field] = arcs
    else:
        room[step.field] = deepcopy(generated)
    return merged


@dataclass
class Graph2Input:
    run_id: str
    project_id: str
    spec00: AuthObject
    world_a: AuthObject
    cast: AuthObject | None = None
    commit: bool = True
    complexity_profile: dict[str, Any] | None = None


@dataclass
class Graph2Output:
    longline: AuthObject
    commit_receipt: CommitReceipt
    aborted: bool = False
    abort_reason: str = ""


class Graph2:
    """Generate Graph 2 as independently reviewable logical files."""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._runner = StepRunner(deps)
        self._auth_store = AuthStore(layout)
        self._layout = layout

    def run(self, inp: Graph2Input) -> Graph2Output:
        """Compatibility full-graph entrypoint; the interactive UI uses generate_step."""
        content: dict[str, Any] = {}
        cast_content = inp.cast.content if inp.cast else {}
        generated_steps = 0
        while (step := next_master_plan_step(content, cast_content)) is not None:
            generated = self.generate_step(inp, step.step_id, content)
            content = merge_master_plan_step(content, step, generated)
            generated_steps += 1
            if generated_steps > 100:
                raise RuntimeError("全书规划动态步骤异常膨胀，已中止")

        now = utcnow()
        longline = AuthObject(
            object_id="longline",
            project_id=inp.project_id,
            object_type=AuthObjectType.CONTRACT,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id=inp.run_id,
        )
        if inp.commit:
            longline = self._auth_store.commit(longline)
        receipt = CommitReceipt(
            receipt_id=new_receipt_id(),
            run_id=inp.run_id,
            staging_id=f"stg_longline_{inp.run_id}",
            commit_type="auth_patch",
            committed_objects=["longline"],
            committed_at=now,
        )
        _logger.info(f"graph2_done run={inp.run_id} steps={generated_steps}")
        return Graph2Output(longline=longline, commit_receipt=receipt)

    def generate_step(
        self,
        inp: Graph2Input,
        step_id: str,
        approved_content: dict[str, Any] | None = None,
    ) -> Any:
        """Generate exactly one master-plan logical file from approved predecessors."""
        cast_content = inp.cast.content if inp.cast else {}
        approved = deepcopy(approved_content or {})
        steps = master_plan_steps(cast_content, approved)
        step = next((item for item in steps if item.step_id == step_id), None)
        if step is None:
            raise ValueError(f"未知全书规划步骤：{step_id}")
        expected = next_master_plan_step(approved, cast_content)
        if expected is not None and expected.step_id != step.step_id:
            raise ValueError(f"请先批准前序文件：{expected.label}")

        level = str((inp.complexity_profile or {}).get("level") or "medium")
        max_tokens = step.max_tokens(level)
        llm_overrides = {
            "best_of_n": 1,
            "max_tokens": max_tokens,
            "thinking": "disabled",
            "reasoning_effort": "high",
        }
        known_ids = {
            str(item.get("id"))
            for item in cast_content.get("characters", [])
            if isinstance(item, dict) and item.get("id")
        }

        def validator(value: Any) -> bool:
            candidate = (
                value
                if step.kind == "longline"
                else (value.get(step.output_key) if isinstance(value, dict) else None)
            )
            return not self.validate_step_content(step, candidate, known_ids)

        if step.kind == "longline":
            step_key = "graph2.longline.core"
            input_pack: dict[str, Any] = {
                "spec00_content": inp.spec00.content,
                "world_a_content": inp.world_a.content,
                "complexity_profile": inp.complexity_profile or {},
            }
        elif step.kind == "map":
            step_key = "graph2.map.room"
            input_pack = {
                "spec00_content": inp.spec00.content,
                "world_a_content": inp.world_a.content,
                "cast_content": deepcopy(cast_content),
                "longline_core": self._longline_core(approved),
                "story_room_core": self._story_context(step, approved),
                "complexity_profile": inp.complexity_profile or {},
            }
        else:
            step_key = "graph2.story.field"
            focus_character = next(
                (
                    item
                    for item in cast_content.get("characters", [])
                    if isinstance(item, dict) and str(item.get("id")) == step.character_id
                ),
                {},
            )
            cast_view, room_view, target_entry = self._story_inputs(step, approved, cast_content)
            input_pack = {
                "spec00_content": inp.spec00.content,
                "world_a_content": inp.world_a.content,
                "cast_content": cast_view,
                "longline_core": self._longline_core(approved),
                "approved_story_room": room_view,
                "complexity_profile": inp.complexity_profile or {},
                "target_key": step.output_key,
                "target_label": step.label,
                "target_character": focus_character,
                "target_relation": target_entry if step.kind == "relationship_arc" else {},
                "target_entry": target_entry,
            }

        _logger.info(
            f"graph2_step {step.step_id} run={inp.run_id} max_tokens={max_tokens} level={level}"
        )
        parsed = self._run_structured_step(
            step_key=step_key,
            input_pack=input_pack,
            run_id=inp.run_id,
            diagnostic_key=_slug(step.step_id),
            validator=validator,
            llm_overrides=llm_overrides,
        )
        if step.kind == "longline":
            generated = parsed
        else:
            generated = parsed.get(step.output_key) or {}
        errors = self.validate_step_content(step, generated, known_ids)
        if errors:
            path = self._persist_failure(
                run_id=inp.run_id,
                diagnostic_key=_slug(step.step_id),
                step_key=step_key,
                error="步骤字段提取后校验失败",
                validation_errors=errors,
                parsed=parsed,
            )
            raise ValueError(f"{step.label}结构不完整：{'；'.join(errors)}；失败记录：{path.name}")
        return generated

    @staticmethod
    def validate_step_content(
        step: MasterPlanStep,
        value: Any,
        known_character_ids: set[str] | None = None,
    ) -> list[str]:
        known = known_character_ids or set()
        errors: list[str] = []
        if step.kind == "longline":
            if not isinstance(value, dict):
                return ["长线骨架必须是JSON对象"]
            if not str(value.get("dq_promise") or "").strip():
                errors.append("缺少dq_promise")
            stages = value.get("stage_nodes")
            if not isinstance(stages, list) or not stages:
                errors.append("stage_nodes必须是非空数组")
            return errors
        if step.kind == "map":
            return (
                []
                if Graph2._valid_map_system(value)
                else ["主要地图缺少有效且唯一的区域ID或路线引用失效"]
            )
        if step.kind == "character_arc":
            if not isinstance(value, dict):
                return ["单角色成长弧必须是JSON对象"]
            if str(value.get("character_id") or "") != step.character_id:
                errors.append(f"character_id必须保持为{step.character_id}")
            if not isinstance(value.get("growth_stages"), list) or not value.get("growth_stages"):
                errors.append("growth_stages必须是非空数组")
            for anchor in value.get("relationship_anchors", []):
                if not isinstance(anchor, dict) or (
                    known and str(anchor.get("other_character_id")) not in known
                ):
                    errors.append("relationship_anchors包含未知角色ID")
                    break
            return errors
        if step.kind == "relationship_index":
            if not isinstance(value, list) or not value:
                return ["核心关系索引必须是非空JSON数组"]
            relationship_ids: list[str] = []
            pairs: list[tuple[str, str]] = []
            for relation in value:
                if not isinstance(relation, dict):
                    errors.append("关系索引条目必须是JSON对象")
                    continue
                relationship_id = str(relation.get("relationship_id") or "").strip()
                character_ids = relation.get("character_ids", [])
                if not relationship_id:
                    errors.append("关系索引缺少relationship_id")
                relationship_ids.append(relationship_id)
                if not isinstance(character_ids, list) or len(character_ids) != 2:
                    errors.append("每条核心关系必须精确引用两个角色")
                    continue
                pair = (min(map(str, character_ids)), max(map(str, character_ids)))
                pairs.append(pair)
                if pair[0] == pair[1] or (known and not set(pair) <= known):
                    errors.append("核心关系索引包含未知或重复角色")
            if len(relationship_ids) != len(set(relationship_ids)):
                errors.append("relationship_id必须唯一")
            if len(pairs) != len(set(pairs)):
                errors.append("同一无向角色对只能出现一次")
            return errors
        if step.kind == "relationship_arc":
            if not isinstance(value, dict):
                return ["单组关系弧必须是JSON对象"]
            if str(value.get("relationship_id") or "") != step.relationship_id:
                errors.append(f"relationship_id必须保持为{step.relationship_id}")
            character_ids = value.get("character_ids", [])
            if (
                not isinstance(character_ids, list)
                or set(map(str, character_ids)) != set(step.character_ids)
                or len(character_ids) != 2
            ):
                errors.append("character_ids必须保持为关系索引指定的两个角色")
            if not isinstance(value.get("turning_stages"), list) or not value.get("turning_stages"):
                errors.append("turning_stages必须是非空数组")
            return errors
        index_specs = {
            "narrative_line_index": "line_id",
            "key_item_index": "item_id",
            "set_piece_index": "set_piece_id",
        }
        if step.kind in index_specs:
            if not isinstance(value, list) or not value:
                return [f"{step.field}必须是非空JSON数组"]
            identity_field = index_specs[step.kind]
            identities: list[str] = []
            for item in value:
                if not isinstance(item, dict):
                    errors.append("索引条目必须是JSON对象")
                    continue
                identity = str(item.get(identity_field) or "").strip()
                identities.append(identity)
                if not identity:
                    errors.append(f"索引条目缺少{identity_field}")
                if step.kind == "narrative_line_index":
                    owner_ids = item.get("owner_ids", [])
                    if not isinstance(owner_ids, list) or (
                        known and not set(map(str, owner_ids)) <= known
                    ):
                        errors.append("故事线索引包含未知owner_ids")
            if len(identities) != len(set(identities)):
                errors.append(f"{identity_field}必须唯一")
            return errors
        entry_specs = {
            "narrative_line": ("line_id", "progression_stages"),
            "key_item_arc": ("item_id", "custody_chain"),
            "set_piece_seed": ("set_piece_id", "build_up_requirements"),
        }
        if step.kind in entry_specs:
            if not isinstance(value, dict):
                return ["单条规划资产必须是JSON对象"]
            identity_field, required_list = entry_specs[step.kind]
            if str(value.get(identity_field) or "") != step.entry_id:
                errors.append(f"{identity_field}必须保持为{step.entry_id}")
            if not isinstance(value.get(required_list), list) or not value.get(required_list):
                errors.append(f"{required_list}必须是非空数组")
            if step.kind == "narrative_line" and known:
                owner_ids = value.get("owner_ids", [])
                if not isinstance(owner_ids, list) or not set(map(str, owner_ids)) <= known:
                    errors.append("owner_ids包含未知角色ID")
            return errors
        if step.field in {"master_story_design", "asset_lifecycle_policy", "story_room_rules"}:
            if not isinstance(value, dict) or not value:
                return [f"{step.field}必须是非空JSON对象"]
            if step.field == "master_story_design":
                for key in (
                    "central_dramatic_question",
                    "story_engine",
                    "active_goal_chain",
                    "ending_state",
                ):
                    if key not in value or value.get(key) in (None, "", []):
                        errors.append(f"缺少{key}")
            elif step.field == "story_room_rules":
                for key in ("must_preserve", "flexible_zones", "anti_bloat_rules"):
                    if not isinstance(value.get(key), list) or not value.get(key):
                        errors.append(f"{key}必须是非空数组")
            return errors
        if not isinstance(value, list):
            return [f"{step.field}必须是JSON数组"]
        if (
            step.field
            in {"major_foreshadowing", "narrative_line_registry", "entity_autonomy_rules"}
            and not value
        ):
            errors.append(f"{step.field}不能为空")
        identity_fields = {
            "major_foreshadowing": "hook_id",
            "ensemble_relationship_arcs": "relationship_id",
            "narrative_line_registry": "line_id",
            "key_item_arcs": "item_id",
            "major_set_piece_seeds": "set_piece_id",
        }
        identity = identity_fields.get(step.field, "")
        if identity:
            ids = [
                str(item.get(identity) or "").strip() for item in value if isinstance(item, dict)
            ]
            if len(ids) != len(value) or any(not item for item in ids) or len(ids) != len(set(ids)):
                errors.append(f"{identity}必须存在且唯一")
        if known and step.field == "major_foreshadowing":
            for hook in value:
                involved = hook.get("involved_character_ids", []) if isinstance(hook, dict) else []
                if not isinstance(involved, list) or not set(map(str, involved)) <= known:
                    errors.append("伏笔包含未知角色ID")
                    break
        if known and step.field == "ensemble_relationship_arcs":
            for relation in value:
                character_ids = (
                    relation.get("character_ids", []) if isinstance(relation, dict) else []
                )
                if (
                    not isinstance(character_ids, list)
                    or len(character_ids) < 2
                    or not set(map(str, character_ids)) <= known
                ):
                    errors.append("群像关系弧必须引用至少两个已知角色")
                    break
        return errors

    def _run_structured_step(
        self,
        *,
        step_key: str,
        input_pack: dict[str, Any],
        run_id: str,
        diagnostic_key: str,
        validator: Callable[[Any], bool],
        llm_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            result = self._runner.run(
                step_key=step_key,
                input_pack=input_pack,
                run_id=run_id,
                parsed_validator=validator,
                llm_overrides=llm_overrides,
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            path = self._persist_failure(
                run_id=run_id,
                diagnostic_key=diagnostic_key,
                step_key=step_key,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise RuntimeError(f"{exc}；失败记录：{path.name}") from exc
        if not result.ok or not isinstance(result.parsed, dict):
            path = self._persist_failure(
                run_id=run_id,
                diagnostic_key=diagnostic_key,
                step_key=step_key,
                error="结构化输出校验失败",
                validation_errors=["模型重试后仍未返回当前文件所需的完整JSON"],
                parsed=result.parsed,
                raw_text=result.text,
                call_records=[item.model_dump(mode="json") for item in result.call_records],
                candidates=[item.model_dump(mode="json") for item in result.candidates],
            )
            raise ValueError(f"当前全书规划文件生成失败；失败记录：{path.name}")
        return result.parsed

    def _persist_failure(
        self,
        *,
        run_id: str,
        diagnostic_key: str,
        step_key: str,
        error: str,
        validation_errors: list[str] | None = None,
        parsed: Any = None,
        raw_text: str = "",
        call_records: list[dict[str, Any]] | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> Path:
        path = self._layout.run_failure_path(run_id, f"master_{diagnostic_key}")
        atomic_write_json(
            path,
            {
                "run_id": run_id,
                "project_id": self._layout.project_id,
                "diagnostic_key": diagnostic_key,
                "step_key": step_key,
                "failed_at": utcnow().isoformat(),
                "error": error,
                "validation_errors": validation_errors or [],
                "raw_text": raw_text,
                "parsed": parsed,
                "call_records": call_records or [],
                "candidates": candidates or [],
            },
        )
        _logger.error(f"master_plan_failure_saved run={run_id} step={step_key} path={path}")
        return path

    @staticmethod
    def _longline_core(content: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(value) for key, value in content.items() if key != "story_room"}

    @classmethod
    def _story_inputs(
        cls,
        step: MasterPlanStep,
        content: dict[str, Any],
        cast_content: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Pass every approved predecessor verbatim while keeping output target-scoped.

        The current long-context model can safely carry the complete approved cast and
        StoryRoom.  Output splitting is an audit/structure boundary, not permission to
        silently summarize or discard predecessor fields.  If compression is added in
        the future it must be a separate model-reviewed, user-visible workflow.
        """
        room = content.get("story_room", {})
        room = room if isinstance(room, dict) else {}
        target_specs = {
            "relationship_arc": (
                "ensemble_relationship_index",
                "relationship_id",
                step.relationship_id,
            ),
            "narrative_line": ("narrative_line_index", "line_id", step.entry_id),
            "key_item_arc": ("key_item_index", "item_id", step.entry_id),
            "set_piece_seed": (
                "major_set_piece_index",
                "set_piece_id",
                step.entry_id,
            ),
        }
        target: dict[str, Any] = {}
        if step.kind in target_specs:
            field, identity_field, identity_value = target_specs[step.kind]
            values = room.get(field, [])
            target = cls._find_entry(
                values if isinstance(values, list) else [],
                identity_field,
                identity_value,
            )
        return (
            deepcopy(cast_content),
            cls._story_context(step, content),
            target,
        )

    @staticmethod
    def _find_entry(
        values: list[Any],
        identity_field: str,
        identity_value: str,
    ) -> dict[str, Any]:
        return next(
            (
                deepcopy(item)
                for item in values
                if isinstance(item, dict) and str(item.get(identity_field)) == identity_value
            ),
            {},
        )

    @staticmethod
    def _story_context(step: MasterPlanStep, content: dict[str, Any]) -> dict[str, Any]:
        room = content.get("story_room", {})
        if not isinstance(room, dict):
            return {}
        # Every value here has crossed an approval boundary.  The map is excluded
        # only because it is the final target itself; sibling entries in a dynamic
        # collection remain visible so each later file can stay consistent with all
        # earlier human-approved files.
        excluded = {"major_map_system"}
        return {key: deepcopy(value) for key, value in room.items() if key not in excluded}

    @staticmethod
    def _valid_story_room(
        parsed: object,
        *,
        known_character_ids: set[str] | None = None,
    ) -> bool:
        if not isinstance(parsed, dict):
            return False
        required = {
            "master_story_design": dict,
            "major_foreshadowing": list,
            "character_growth_arcs": list,
            "ensemble_relationship_arcs": list,
            "narrative_line_registry": list,
            "key_item_arcs": list,
            "major_set_piece_seeds": list,
            "asset_lifecycle_policy": dict,
            "entity_autonomy_rules": list,
        }
        if any(not isinstance(parsed.get(key), kind) for key, kind in required.items()):
            return False
        if (
            not parsed["major_foreshadowing"]
            or not parsed["character_growth_arcs"]
            or not parsed["narrative_line_registry"]
        ):
            return False
        known = known_character_ids or set()
        arc_ids = [
            str(item.get("character_id") or "")
            for item in parsed["character_growth_arcs"]
            if isinstance(item, dict)
        ]
        return (
            len(arc_ids) == len(parsed["character_growth_arcs"])
            and len(arc_ids) == len(set(arc_ids))
            and (not known or set(arc_ids) <= known)
        )

    @staticmethod
    def _valid_map_system(map_system: object) -> bool:
        if not isinstance(map_system, dict):
            return False
        regions = map_system.get("major_regions")
        if not isinstance(regions, list) or not regions:
            return False
        map_ids = [
            str(item.get("map_id") or "").strip() for item in regions if isinstance(item, dict)
        ]
        if (
            len(map_ids) != len(regions)
            or any(not value for value in map_ids)
            or len(map_ids) != len(set(map_ids))
        ):
            return False
        known_maps = set(map_ids)
        for region in regions:
            parent_id = str(region.get("parent_map_id") or "").strip()
            connected = region.get("connected_map_ids", [])
            if parent_id and parent_id not in known_maps:
                return False
            if not isinstance(connected, list) or not set(map(str, connected)) <= known_maps:
                return False
        routes = map_system.get("major_routes", [])
        return isinstance(routes, list) and all(
            isinstance(route, dict)
            and str(route.get("from_map_id")) in known_maps
            and str(route.get("to_map_id")) in known_maps
            for route in routes
        )

    @staticmethod
    def _valid_map_room(parsed: object) -> bool:
        return isinstance(parsed, dict) and Graph2._valid_map_system(parsed.get("major_map_system"))


def _slug(value: str) -> str:
    return (
        "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")
        or "step"
    )
