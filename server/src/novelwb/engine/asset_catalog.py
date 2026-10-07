"""Layer-aware logical asset catalog for the editable workbench.

Authority documents stay physically atomic, while the UI addresses stable logical
sub-assets such as ``story_room.major_foreshadowing`` or one event design.  Every
write is merged back into its owning authority document through a staged review.
Derived runtime projections are exposed as read-only assets.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from novelwb.core.schemas.domain_models import AuthObject
from novelwb.storage import AuthStore, ContextStore, SnapshotsStore
from novelwb.storage.workspace_layout import WorkspaceLayout

PathPart = str | int
EditorKind = Literal["object", "collection", "text", "readonly"]


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    group_id: str
    group_label: str
    label: str
    scope: str
    artifact_key: str | None
    path: tuple[PathPart, ...] = ()
    exclude_keys: tuple[str, ...] = ()
    editor_kind: EditorKind = "object"
    description: str = ""
    editable: bool = True
    derived: bool = False
    owner_stage: str = ""
    dependencies: tuple[str, ...] = ()
    downstream: tuple[str, ...] = ()
    source_asset_id: str | None = None
    projection_key: str | None = None
    identity_field: str | None = None
    identity_value: str | None = None


class LayeredAssetCatalog:
    """Expose logical layer files without weakening authority boundaries."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._auth = AuthStore(layout)
        self._contexts = ContextStore(layout)
        self._snapshots = SnapshotsStore(layout)

    def list_catalog(self) -> dict[str, Any]:
        objects = self._authority_objects()
        specs = self._build_specs(objects)
        summaries = [self._summary(spec, objects) for spec in specs]
        groups: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in summaries:
            group_id = item["group_id"]
            if group_id in seen:
                continue
            seen.add(group_id)
            group_assets = [row["asset_id"] for row in summaries if row["group_id"] == group_id]
            groups.append(
                {
                    "group_id": group_id,
                    "label": item["group_label"],
                    "scope": item["scope"],
                    "asset_ids": group_assets,
                }
            )
        return {"groups": groups, "assets": summaries}

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        objects = self._authority_objects()
        spec = self._require_spec(asset_id, objects)
        summary = self._summary(spec, objects)
        summary["content"] = self._content(spec, objects)
        return summary

    def authority_edit_base(self, asset_id: str) -> tuple[AssetSpec, AuthObject, Any]:
        objects = self._authority_objects()
        spec = self._require_spec(asset_id, objects)
        if spec.derived or not spec.editable or not spec.artifact_key:
            raise ValueError("派生投影不能直接修改；请编辑其来源资产并重新生成投影")
        obj = objects.get(spec.artifact_key)
        if obj is None:
            raise ValueError(f"资产所属权威文件尚不存在: {spec.artifact_key}")
        return spec, obj, self._read_authority_content(spec, obj.content)

    def merge_authority_edit(
        self,
        asset_id: str,
        edited_content: Any,
        *,
        expected_version: int,
    ) -> tuple[AssetSpec, AuthObject, dict[str, Any]]:
        spec, obj, original = self.authority_edit_base(asset_id)
        if obj.version != expected_version:
            raise ValueError(
                f"权威文件版本已从 v{expected_version} 更新到 v{obj.version}；"
                "请重新载入后再提交，避免覆盖他人修改"
            )
        self._validate_edited_content(spec, original, edited_content)
        merged = self._replace_authority_content(spec, obj.content, edited_content)
        return spec, obj, merged

    def _authority_objects(self) -> dict[str, AuthObject]:
        return {self._auth.artifact_key(obj): obj for obj in self._auth.load_bundle()}

    def _build_specs(self, objects: dict[str, AuthObject]) -> list[AssetSpec]:
        specs = [
            *self._foundation_specs(),
            *self._cast_file_specs(objects.get("cast")),
            *self._master_specs(objects.get("longline")),
        ]
        volume_objects = [
            (key, obj)
            for key, obj in objects.items()
            if key.startswith("volume_") and isinstance(obj.content.get("event_slots"), list)
        ]
        volume_objects.sort(key=lambda item: (str(item[1].content.get("volume_id", "")), item[0]))
        for position, (artifact_key, obj) in enumerate(volume_objects, start=1):
            specs.extend(self._volume_specs(artifact_key, obj, position))
        specs.extend(self._projection_specs())
        return specs

    @staticmethod
    def _foundation_specs() -> list[AssetSpec]:
        rows = [
            (
                "spec00",
                "规格与契约",
                "作品承诺、复杂度、Lens、禁忌与预算",
                (),
                ("world_a", "cast", "longline"),
            ),
            (
                "world_a",
                "世界A：硬锚",
                "世界核心冲突、意义系统与意象种子",
                ("spec00",),
                ("world_b", "opp_eco", "longline"),
            ),
            (
                "world_b",
                "世界B：宏观生态",
                "区域、制度、交通与冲突供给",
                ("spec00", "world_a"),
                ("opp_eco", "longline"),
            ),
            (
                "opp_eco",
                "对手生态",
                "对手层级、压迫谱系与自主目标",
                ("world_a", "world_b"),
                ("longline",),
            ),
            ("cast", "核心角色", "核心角色、关系与基础身份", ("spec00", "world_a"), ("longline",)),
            (
                "pow_l",
                "力量定律层",
                "守恒、阈值、代价与反制",
                ("spec00", "world_a"),
                ("pow_s", "pow_e"),
            ),
            ("pow_s", "力量结构层", "源、路、阀、载体、损伤与成长结构", ("pow_l",), ("pow_e",)),
            (
                "pow_e",
                "力量表现层",
                "文化、流派、装备与画面化接口",
                ("pow_l", "pow_s", "world_b"),
                ("longline",),
            ),
        ]
        return [
            AssetSpec(
                asset_id=f"foundation.{key}",
                group_id="foundation",
                group_label="作品基座",
                label=label,
                scope="foundation",
                artifact_key=key,
                description=description,
                owner_stage="foundation",
                dependencies=dependencies,
                downstream=downstream,
            )
            for key, label, description, dependencies, downstream in rows
        ]

    @classmethod
    def _cast_file_specs(cls, cast: AuthObject | None) -> list[AssetSpec]:
        """Expose the assembled cast as independently editable logical files."""
        if cast is None:
            return []
        common: dict[str, Any] = {
            "group_id": "foundation.cast_files",
            "group_label": "核心角色文件",
            "scope": "foundation",
            "artifact_key": "cast",
            "owner_stage": "foundation",
        }
        specs: list[AssetSpec] = [
            AssetSpec(
                asset_id="foundation.cast.characters",
                label="角色阵容索引",
                path=("characters",),
                editor_kind="collection",
                description="核心角色顺序、身份与完整档案集合",
                dependencies=("foundation.spec00", "foundation.world_b", "foundation.opp_eco"),
                downstream=("foundation.cast.relationships", "master.longline_core"),
                **common,
            ),
            AssetSpec(
                asset_id="foundation.cast.relationships",
                label="角色关系边界",
                path=("relationships",),
                editor_kind="collection",
                description="当前关系、张力与禁止无铺垫跳变的边界",
                dependencies=("foundation.cast.characters",),
                downstream=("master.story.ensemble_relationship_arcs",),
                **common,
            ),
            AssetSpec(
                asset_id="foundation.cast.knowledge_boundaries",
                label="角色知识边界",
                path=("knowledge_boundaries",),
                editor_kind="collection",
                description="受控事实的已知者、未知者与揭示条件",
                dependencies=("foundation.cast.characters",),
                downstream=("ContextPackage", "Graph4"),
                **common,
            ),
            AssetSpec(
                asset_id="foundation.cast.ensemble_balance",
                label="群像功能平衡",
                path=("ensemble_balance",),
                editor_kind="collection",
                description="每名角色的独有故事价值与自主行动来源",
                dependencies=("foundation.cast.characters",),
                downstream=("master.story.character_growth_arcs",),
                **common,
            ),
        ]
        characters = cast.content.get("characters")
        if not isinstance(characters, list):
            return specs
        for index, character in enumerate(characters):
            if not isinstance(character, dict):
                continue
            char_id = str(character.get("id") or f"character_{index + 1}")
            char_name = str(character.get("name") or char_id)
            specs.append(
                AssetSpec(
                    asset_id=f"foundation.cast.character.{cls._slug(char_id)}",
                    label=f"角色：{char_name}",
                    path=("characters", index),
                    editor_kind="object",
                    description="单角色背景、欲望、能力边界、表演锚点与场景引擎",
                    dependencies=("foundation.cast.characters",),
                    downstream=("foundation.cast.relationships", "master.longline_core"),
                    identity_field="id",
                    identity_value=char_id,
                    **common,
                )
            )
        return specs

    @classmethod
    def _master_specs(cls, longline: AuthObject | None) -> list[AssetSpec]:
        group: dict[str, Any] = {
            "group_id": "master",
            "group_label": "全书规划",
            "scope": "master",
            "artifact_key": "longline",
            "owner_stage": "master_plan",
        }
        specs = [
            AssetSpec(
                asset_id="master.longline_core",
                label="长线骨架",
                path=(),
                exclude_keys=("story_room",),
                editor_kind="object",
                description="全书DQ、阶段节点、波形、动量债与不可回头选择",
                dependencies=("foundation.spec00", "foundation.world_a", "foundation.cast"),
                downstream=(
                    "master.story.master_story_design",
                    "master.map.major_map_system",
                    "volume.*",
                ),
                **group,
            )
        ]
        story_rows = [
            ("master_story_design", "全书总纲", "object", "总纲因果、主动目标链、高潮与结局状态"),
            (
                "major_foreshadowing",
                "主要伏笔",
                "collection",
                "伏笔载体、递进信息、揭示边界与回收窗口",
            ),
            (
                "character_growth_arcs",
                "核心角色成长弧",
                "collection",
                "选择、失败、关系与能力代价形成的成长",
            ),
            (
                "ensemble_relationship_index",
                "核心关系索引",
                "collection",
                "需要长期追踪的角色对、关系职能与优先级",
            ),
            (
                "ensemble_relationship_arcs",
                "群像关系弧",
                "collection",
                "核心关系的起点、摩擦、转折与禁止跳变",
            ),
            (
                "narrative_line_index",
                "故事线索引",
                "collection",
                "逐条故事线生成前的稳定ID、归属角色、阶段跨度与碰撞提示",
            ),
            (
                "narrative_line_registry",
                "全书故事线",
                "collection",
                "主线、支线、暗线、关系线、势力线和生态线生命周期",
            ),
            (
                "key_item_index",
                "关键物品索引",
                "collection",
                "逐物品弧生成前的稳定ID、故事职能与关联故事线",
            ),
            ("key_item_arcs", "关键物品弧", "collection", "物品持有链、揭示、限制和最终作用"),
            (
                "major_set_piece_index",
                "大场面索引",
                "collection",
                "逐大场面生成前的稳定ID、阶段窗口与空间要求",
            ),
            (
                "major_set_piece_seeds",
                "全书大场面种子",
                "collection",
                "跨事件铺垫、参与故事线和多实体后果",
            ),
            (
                "asset_lifecycle_policy",
                "资产生命周期策略",
                "object",
                "长期、卷级和临时资产的升级与退场规则",
            ),
            (
                "entity_autonomy_rules",
                "实体自治规则",
                "collection",
                "人物、势力、物件和环境脱离主角仍会行动的规则",
            ),
            (
                "story_room_rules",
                "StoryRoom 继承规则",
                "object",
                "不可破坏的核心、可调整区与防膨胀约束",
            ),
        ]
        for key, label, editor_kind, description in story_rows:
            specs.append(
                AssetSpec(
                    asset_id=f"master.story.{key}",
                    label=label,
                    path=("story_room", key),
                    editor_kind=editor_kind,  # type: ignore[arg-type]
                    description=description,
                    dependencies=("master.longline_core",),
                    downstream=("master.map.major_map_system", "volume.*"),
                    **group,
                )
            )
        specs.append(
            AssetSpec(
                asset_id="master.map.major_map_system",
                label="全书主要地图",
                path=("story_room", "major_map_system"),
                editor_kind="object",
                description="区域层级、连接、交通成本、势力与人物联系",
                dependencies=("master.longline_core", "master.story.master_story_design"),
                downstream=("volume.*.map",),
                **group,
            )
        )
        room = (
            longline.content.get("story_room", {})
            if longline is not None and isinstance(longline.content, dict)
            else {}
        )
        if not isinstance(room, dict):
            return specs
        item_rows = (
            ("major_foreshadowing", "hook_id", "伏笔"),
            ("character_growth_arcs", "character_id", "人物成长弧"),
            ("ensemble_relationship_index", "relationship_id", "关系索引"),
            ("ensemble_relationship_arcs", "relationship_id", "关系弧"),
            ("narrative_line_index", "line_id", "故事线索引"),
            ("narrative_line_registry", "line_id", "故事线"),
            ("key_item_index", "item_id", "关键物品索引"),
            ("key_item_arcs", "item_id", "关键物品"),
            ("major_set_piece_index", "set_piece_id", "大场面索引"),
            ("major_set_piece_seeds", "set_piece_id", "大场面"),
        )
        for field, identity_field, label_prefix in item_rows:
            items = room.get(field, [])
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                identity = str(item.get(identity_field) or "").strip()
                if not identity:
                    continue
                display = str(item.get("name") or identity)
                specs.append(
                    AssetSpec(
                        asset_id=f"master.story.{field}.{cls._slug(identity)}",
                        label=f"{label_prefix}：{display}",
                        path=("story_room", field, index),
                        editor_kind="object",
                        description=f"{label_prefix}的单条可审核逻辑文件",
                        dependencies=(f"master.story.{field}",),
                        downstream=("master.map.major_map_system", "volume.*"),
                        identity_field=identity_field,
                        identity_value=identity,
                        **group,
                    )
                )
        return specs

    def _volume_specs(self, artifact_key: str, obj: AuthObject, position: int) -> list[AssetSpec]:
        content = obj.content
        volume_id = str(content.get("volume_id") or artifact_key)
        group_id = f"volume.{artifact_key}"
        group_label = str(content.get("title") or f"第{position}卷 · {volume_id}")
        base: dict[str, Any] = {
            "group_id": group_id,
            "group_label": group_label,
            "scope": "volume",
            "artifact_key": artifact_key,
            "owner_stage": "volume_plan",
        }
        prefix = f"volume.{artifact_key}"
        specs: list[AssetSpec] = [
            AssetSpec(
                asset_id=f"{prefix}.plan",
                label="卷纲骨架",
                exclude_keys=(
                    "story_room",
                    "event_slots",
                    "event_plans",
                    "_volume_workflow",
                    "volume_fatigue_report",
                ),
                description="卷定位、卷契约、波形、结算和承接信息",
                dependencies=("master.longline_core",),
                downstream=(f"{prefix}.story.*", f"{prefix}.event_slots"),
                **base,
            ),
            AssetSpec(
                asset_id=f"{prefix}.event_slots",
                label="事件槽位表",
                path=("event_slots",),
                editor_kind="collection",
                description="本卷事件队列与每个事件的目标、结果和约束",
                dependencies=(f"{prefix}.plan",),
                downstream=(f"{prefix}.event_designs", "event.*"),
                **base,
            ),
        ]
        story_rows = [
            ("volume_story_engine", "卷故事引擎", "object"),
            ("volume_foreshadowing", "卷伏笔", "collection"),
            ("volume_character_arcs", "卷角色成长弧", "collection"),
            ("volume_cast_cards", "卷角色卡", "collection"),
            ("relationship_tracks", "关系轨迹", "collection"),
            ("volume_line_ledger", "卷故事线账", "collection"),
            ("entity_agendas", "实体议程", "collection"),
            ("key_item_tracks", "关键物品轨迹", "collection"),
            ("set_piece_plans", "大场面计划", "collection"),
            ("transient_assets", "临时资产", "collection"),
        ]
        for key, label, editor_kind in story_rows:
            specs.append(
                AssetSpec(
                    asset_id=f"{prefix}.story.{key}",
                    label=label,
                    path=("story_room", key),
                    editor_kind=editor_kind,  # type: ignore[arg-type]
                    description=f"{group_label}的{label}",
                    dependencies=(f"{prefix}.plan", "master.*"),
                    downstream=(f"{prefix}.event_designs", "event.*"),
                    **base,
                )
            )
        story_room = content.get("story_room", {})
        story_room = story_room if isinstance(story_room, dict) else {}
        relationship_tracks = story_room.get("relationship_tracks", [])
        for index, relationship in enumerate(
            relationship_tracks if isinstance(relationship_tracks, list) else []
        ):
            if not isinstance(relationship, dict):
                continue
            relationship_id = str(relationship.get("relationship_id") or "").strip()
            if not relationship_id:
                continue
            display = str(relationship.get("name") or relationship_id)
            specs.append(
                AssetSpec(
                    asset_id=(f"{prefix}.story.relationship_tracks.{self._slug(relationship_id)}"),
                    label=f"卷关系轨迹：{display}",
                    path=("story_room", "relationship_tracks", index),
                    editor_kind="object",
                    description="从全书关系弧继承并在本卷推进的单组关系轨迹",
                    dependencies=(
                        f"{prefix}.story.relationship_tracks",
                        f"master.story.ensemble_relationship_arcs.{self._slug(relationship_id)}",
                    ),
                    downstream=(f"{prefix}.event_designs", "event.*.reading_assets"),
                    identity_field="relationship_id",
                    identity_value=relationship_id,
                    **base,
                )
            )
        specs.extend(
            [
                AssetSpec(
                    asset_id=f"{prefix}.map.volume_map_system",
                    label="卷地图",
                    path=("story_room", "volume_map_system"),
                    description="本卷地点、路线、开放条件与地图人物进程",
                    dependencies=(
                        "master.map.major_map_system",
                        f"{prefix}.story.volume_story_engine",
                    ),
                    downstream=(f"{prefix}.map.scene_assets", f"{prefix}.event_designs"),
                    **base,
                ),
                AssetSpec(
                    asset_id=f"{prefix}.map.scene_assets",
                    label="卷场景资产",
                    path=("story_room", "scene_assets"),
                    editor_kind="collection",
                    description="可复用场景的空间、压力、人物与叙事功能",
                    dependencies=(f"{prefix}.map.volume_map_system",),
                    downstream=(f"{prefix}.map.schedule", f"{prefix}.event_designs"),
                    **base,
                ),
                AssetSpec(
                    asset_id=f"{prefix}.map.schedule",
                    label="逐事件地图排期",
                    path=("story_room", "volume_map_schedule"),
                    editor_kind="collection",
                    description="每个事件实际使用的地点、场景与人物空间压力",
                    dependencies=(
                        f"{prefix}.event_slots",
                        f"{prefix}.map.volume_map_system",
                        f"{prefix}.map.scene_assets",
                    ),
                    downstream=(f"{prefix}.event_designs", "event.*.reading_assets"),
                    **base,
                ),
                AssetSpec(
                    asset_id=f"{prefix}.event_designs",
                    label="逐事件设计合集",
                    path=("story_room", "event_designs"),
                    editor_kind="collection",
                    description="每个事件的戏剧中心、显式资产引用与展开路线",
                    dependencies=(f"{prefix}.event_slots", f"{prefix}.story.*", f"{prefix}.map.*"),
                    downstream=("event.*.reading_assets", "event.*.plan"),
                    **base,
                ),
                AssetSpec(
                    asset_id=f"{prefix}.fatigue_report",
                    label="卷级疲劳检查",
                    path=("volume_fatigue_report",),
                    description="冲突、钩子、缓冲与动量债的卷级检查结果",
                    dependencies=(f"{prefix}.event_designs",),
                    downstream=("event.*.route",),
                    **base,
                ),
            ]
        )

        slots = content.get("event_slots", [])
        designs = (
            content.get("story_room", {}).get("event_designs", [])
            if isinstance(content.get("story_room"), dict)
            else []
        )
        design_index = {
            str(item.get("slot_id")): index
            for index, item in enumerate(designs if isinstance(designs, list) else [])
            if isinstance(item, dict) and item.get("slot_id")
        }
        if isinstance(slots, list):
            for index, slot in enumerate(slots):
                if not isinstance(slot, dict):
                    continue
                slot_id = str(slot.get("slot_id") or f"slot_{index + 1:03d}")
                safe_slot = self._slug(slot_id)
                event_prefix = f"event.{artifact_key}.{safe_slot}"
                specs.append(
                    AssetSpec(
                        asset_id=f"{event_prefix}.slot",
                        group_id=group_id,
                        group_label=group_label,
                        label=f"事件 {index + 1} · 槽位",
                        scope="event",
                        artifact_key=artifact_key,
                        path=("event_slots", index),
                        exclude_keys=("chapter_design",),
                        description="事件目标、结果、允许/禁止变化与关键交付",
                        owner_stage="volume_plan",
                        dependencies=(f"{prefix}.event_slots",),
                        downstream=(f"{event_prefix}.design", f"{event_prefix}.reading_assets"),
                        identity_field="slot_id",
                        identity_value=slot_id,
                    )
                )
                design_position = design_index.get(slot_id)
                design_asset_id = f"{event_prefix}.design"
                if design_position is not None:
                    specs.append(
                        AssetSpec(
                            asset_id=design_asset_id,
                            group_id=group_id,
                            group_label=group_label,
                            label=f"事件 {index + 1} · 逐事件设计",
                            scope="event",
                            artifact_key=artifact_key,
                            path=("story_room", "event_designs", design_position),
                            description="戏剧中心、人物/地点/场景/伏笔ID、展开路线与结束要求",
                            owner_stage="volume_plan",
                            dependencies=(
                                f"{event_prefix}.slot",
                                f"{prefix}.story.*",
                                f"{prefix}.map.*",
                            ),
                            downstream=(f"{event_prefix}.reading_assets", "event_plan"),
                            identity_field="slot_id",
                            identity_value=slot_id,
                        )
                    )
                event_plans = content.get("event_plans", {})
                plan_record = event_plans.get(slot_id, {}) if isinstance(event_plans, dict) else {}
                plan_files = plan_record.get("files", {}) if isinstance(plan_record, dict) else {}
                plan_rows = (
                    (
                        "constraints_route",
                        "事件约束与展开路线",
                        "预算、允许/禁止变化与本次展开维度",
                    ),
                    ("world_pulse", "世界脉冲", "人物、势力、物件与环境的自主行动"),
                    ("event_expansion", "多线事件展开", "因果、人物、关系与场面的候选碰撞"),
                    ("scene_plan", "连续场景方案", "已编织的场景顺序、变化护栏与覆盖关系"),
                    ("prewrite_assets", "正文前检查与临时资产", "一致性检查、命名检查与JIT素材卡"),
                )
                if isinstance(plan_files, dict):
                    previous_asset = design_asset_id
                    for plan_step, plan_label, plan_description in plan_rows:
                        if not isinstance(plan_files.get(plan_step), dict):
                            continue
                        plan_asset_id = f"{event_prefix}.plan.{plan_step}"
                        specs.append(
                            AssetSpec(
                                asset_id=plan_asset_id,
                                group_id=f"{group_id}.event_plan.{safe_slot}",
                                group_label=f"事件 {index + 1} · 展开规划",
                                label=plan_label,
                                scope="event",
                                artifact_key=artifact_key,
                                path=("event_plans", slot_id, "files", plan_step),
                                editor_kind="object",
                                description=plan_description,
                                owner_stage="event_plan",
                                dependencies=(previous_asset,),
                                downstream=("event.prose",),
                            )
                        )
                        previous_asset = plan_asset_id
                specs.append(
                    AssetSpec(
                        asset_id=f"{event_prefix}.reading_assets",
                        group_id=group_id,
                        group_label=group_label,
                        label=f"事件 {index + 1} · 按需读取资产",
                        scope="event",
                        artifact_key=artifact_key,
                        path=("event_slots", index, "chapter_design", "reading_assets"),
                        editor_kind="readonly",
                        description="由逐事件设计中的显式ID确定性解析，不可直接覆盖",
                        editable=False,
                        derived=True,
                        owner_stage="event_plan",
                        dependencies=(design_asset_id,),
                        downstream=("ContextPackage", "Graph4"),
                        source_asset_id=design_asset_id
                        if design_position is not None
                        else f"{prefix}.event_designs",
                    )
                )
        return specs

    @staticmethod
    def _projection_specs() -> list[AssetSpec]:
        common: dict[str, Any] = {
            "group_id": "runtime",
            "group_label": "运行投影（只读）",
            "scope": "runtime",
            "artifact_key": None,
            "editor_kind": "readonly",
            "editable": False,
            "derived": True,
            "owner_stage": "runtime",
        }
        return [
            AssetSpec(
                asset_id="runtime.latest_snapshot",
                label="最新状态快照",
                description="最近一次已提交事件形成的权威状态快照",
                projection_key="latest_snapshot",
                dependencies=("EVENT",),
                downstream=("runtime.latest_context", "Graph4"),
                **common,
            ),
            AssetSpec(
                asset_id="runtime.status_card_index",
                label="状态卡索引",
                description="由权威资产和已提交事件重建的读取投影",
                projection_key="status_card_index",
                dependencies=("AUTH", "EVENT"),
                downstream=("runtime.latest_context",),
                **common,
            ),
            AssetSpec(
                asset_id="runtime.latest_context",
                label="最新上下文包",
                description="最近事件实际读取的来源、状态卡、省略原因与指纹",
                projection_key="latest_context",
                dependencies=(
                    "reading_assets",
                    "runtime.status_card_index",
                    "runtime.latest_snapshot",
                ),
                downstream=("Graph4", "GraphE"),
                **common,
            ),
        ]

    def _summary(self, spec: AssetSpec, objects: dict[str, AuthObject]) -> dict[str, Any]:
        content = self._content(spec, objects)
        obj = objects.get(spec.artifact_key or "")
        exists = content is not None
        item_count = len(content) if isinstance(content, (list, dict)) else (1 if exists else 0)
        return {
            "asset_id": spec.asset_id,
            "group_id": spec.group_id,
            "group_label": spec.group_label,
            "label": spec.label,
            "scope": spec.scope,
            "artifact_key": spec.artifact_key,
            "json_path": self._json_pointer(spec.path),
            "excluded_keys": list(spec.exclude_keys),
            "editor_kind": spec.editor_kind,
            "description": spec.description,
            "editable": bool(spec.editable and not spec.derived and obj is not None),
            "derived": spec.derived,
            "exists": exists,
            "version": obj.version if obj is not None else 0,
            "item_count": item_count,
            "owner_stage": spec.owner_stage,
            "dependencies": list(spec.dependencies),
            "downstream": list(spec.downstream),
            "source_asset_id": spec.source_asset_id,
        }

    def _content(self, spec: AssetSpec, objects: dict[str, AuthObject]) -> Any:
        if spec.projection_key:
            return self._projection_content(spec.projection_key)
        obj = objects.get(spec.artifact_key or "")
        if obj is None:
            return None
        return self._read_authority_content(spec, obj.content)

    def _projection_content(self, key: str) -> Any:
        if key == "latest_snapshot":
            snapshot = self._snapshots.load_latest()
            return snapshot.model_dump(mode="json") if snapshot else None
        if key == "status_card_index":
            index = self._contexts.load_card_index()
            return index.model_dump(mode="json")
        if key == "latest_context":
            snapshot = self._snapshots.load_latest()
            package = (
                self._contexts.load_package(snapshot.event_id)
                if snapshot and snapshot.event_id
                else None
            )
            return package.model_dump(mode="json") if package else None
        raise ValueError(f"未知投影资产: {key}")

    def _require_spec(self, asset_id: str, objects: dict[str, AuthObject]) -> AssetSpec:
        by_id = {spec.asset_id: spec for spec in self._build_specs(objects)}
        spec = by_id.get(asset_id)
        if spec is None:
            raise ValueError(f"分层资产不存在: {asset_id}")
        return spec

    @staticmethod
    def _read_authority_content(spec: AssetSpec, root: dict[str, Any]) -> Any:
        try:
            value: Any = root
            for part in spec.path:
                value = value[part]
        except (KeyError, IndexError, TypeError):
            return [] if spec.editor_kind == "collection" else {}
        value = deepcopy(value)
        if spec.exclude_keys and isinstance(value, dict):
            return {key: item for key, item in value.items() if key not in spec.exclude_keys}
        return value

    @staticmethod
    def _replace_authority_content(
        spec: AssetSpec, root: dict[str, Any], edited: Any
    ) -> dict[str, Any]:
        updated = deepcopy(root)
        if not spec.path:
            if spec.exclude_keys:
                preserved = {
                    key: deepcopy(updated[key]) for key in spec.exclude_keys if key in updated
                }
                updated = deepcopy(edited)
                updated.update(preserved)
                return updated
            return deepcopy(edited)

        parent: Any = updated
        for position, part in enumerate(spec.path[:-1]):
            next_part = spec.path[position + 1]
            if isinstance(part, int):
                if not isinstance(parent, list) or part >= len(parent):
                    raise ValueError("资产路径已失效，请刷新目录")
                parent = parent[part]
            else:
                if not isinstance(parent, dict):
                    raise ValueError("资产路径已失效，请刷新目录")
                if part not in parent:
                    parent[part] = [] if isinstance(next_part, int) else {}
                parent = parent[part]

        leaf = spec.path[-1]
        current: Any = None
        if isinstance(parent, list):
            if not isinstance(leaf, int) or leaf >= len(parent):
                raise ValueError("资产路径已失效，请刷新目录")
            current = parent[leaf]
        elif isinstance(parent, dict):
            current = parent.get(leaf)
        else:
            raise ValueError("资产路径已失效，请刷新目录")

        replacement = deepcopy(edited)
        if spec.exclude_keys and isinstance(current, dict):
            preserved = {key: deepcopy(current[key]) for key in spec.exclude_keys if key in current}
            replacement.update(preserved)
        parent[leaf] = replacement
        return updated

    @staticmethod
    def _validate_edited_content(spec: AssetSpec, original: Any, edited: Any) -> None:
        if spec.editor_kind == "collection" and not isinstance(edited, list):
            raise ValueError("该资产必须保持为 JSON 数组")
        if spec.editor_kind == "object" and not isinstance(edited, dict):
            raise ValueError("该资产必须保持为 JSON 对象")
        if spec.editor_kind == "text" and not isinstance(edited, str):
            raise ValueError("该资产必须保持为文本")
        if spec.identity_field and isinstance(edited, dict):
            actual = str(edited.get(spec.identity_field) or "")
            if actual != str(spec.identity_value or ""):
                raise ValueError(f"标识字段 {spec.identity_field} 不允许在局部编辑中改名")
        if spec.exclude_keys and not isinstance(edited, dict):
            raise ValueError("局部对象资产必须保持为 JSON 对象")
        if original is None:
            raise ValueError("资产尚不存在，不能创建局部审核稿")

    @staticmethod
    def _json_pointer(path: tuple[PathPart, ...]) -> str:
        if not path:
            return "/"
        return "/" + "/".join(str(item).replace("~", "~0").replace("/", "~1") for item in path)

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_").lower()
        return slug or "slot"
