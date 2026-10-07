"""图1 — 舞台引擎（Stage Engine）。

步骤：
  1.1 spec00    — #00规格与契约基线
  1.2 world_A   — 世界A层（意义系统/意象种子/禁区反差）
  1.3 world_B   — 世界B层（生态/地图/派系框架）
  1.4 pow_L     — 力量定律层
  1.5 pow_S     — 力量结构层
  1.6 pow_E     — 力量表现层
  1.7 opp_eco   — 对手生态
  1.8 cast       — 核心角色

交互工作台在每个步骤后设置人工审核门；后一步只读取已批准的前序权威对象。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novelwb.core.constants import AuthObjectType
from novelwb.core.schemas.domain_models import AuthObject
from novelwb.core.schemas.patch_models import CommitReceipt
from novelwb.engine.foundation_validation import (
    format_validation_errors,
    validate_cast_relations,
    validate_cast_roster,
    validate_character_dossier,
    validate_foundation_content,
)
from novelwb.engine.step_runner import GraphDeps, PipelineCancelled, StepResult, StepRunner
from novelwb.storage import AuthStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_receipt_id
from novelwb.utils.io_atomic import atomic_write_json
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow

_logger = get_logger(__name__)

FOUNDATION_STEPS: tuple[tuple[str, str], ...] = (
    ("spec00", "规格与契约"),
    ("world_a", "世界A：硬锚"),
    ("world_b", "世界B：宏观生态"),
    ("pow_l", "力量定律层"),
    ("pow_s", "力量结构层"),
    ("pow_e", "力量表现层"),
    ("opp_eco", "对手生态"),
    ("cast", "核心角色"),
)
FOUNDATION_STEP_ORDER = tuple(key for key, _ in FOUNDATION_STEPS)
FOUNDATION_STEP_LABELS = dict(FOUNDATION_STEPS)


@dataclass
class Graph1Input:
    """图1 的输入。"""

    run_id: str
    project_id: str
    user_brief: str  # 用户输入的小说简介/设定
    commit: bool = True
    complexity_profile: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph1Output:
    """图1 的输出。"""

    spec00: AuthObject
    world_a: AuthObject
    world_b: AuthObject
    pow_l: AuthObject
    pow_s: AuthObject
    pow_e: AuthObject
    opp_eco: AuthObject
    cast: AuthObject
    commit_receipts: list[CommitReceipt] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""


class Graph1:
    """舞台引擎图执行器。"""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._runner = StepRunner(deps)
        self._auth_store = AuthStore(layout)
        self._layout = layout

    def run(self, inp: Graph1Input) -> Graph1Output:
        """Legacy full-graph entrypoint.

        Interactive workflow code must call :meth:`generate_step` and place a
        human approval boundary between steps.  This method remains for CLI and
        compatibility pipelines that intentionally request the complete graph.
        """
        receipts: list[CommitReceipt] = []
        artifacts: dict[str, AuthObject] = {}
        for artifact_key in FOUNDATION_STEP_ORDER:
            artifact = self.generate_step(inp, artifact_key, artifacts)
            if inp.commit:
                artifact = self._auth_store.commit(artifact)
            artifacts[artifact_key] = artifact
            receipts.append(self._make_receipt(inp.run_id, artifact_key))

        _logger.info(f"graph1_done run={inp.run_id} steps={len(receipts)}")
        return Graph1Output(
            spec00=artifacts["spec00"],
            world_a=artifacts["world_a"],
            world_b=artifacts["world_b"],
            pow_l=artifacts["pow_l"],
            pow_s=artifacts["pow_s"],
            pow_e=artifacts["pow_e"],
            opp_eco=artifacts["opp_eco"],
            cast=artifacts["cast"],
            commit_receipts=receipts,
        )

    def generate_step(
        self,
        inp: Graph1Input,
        artifact_key: str,
        approved: dict[str, AuthObject],
    ) -> AuthObject:
        """Generate exactly one foundation artifact from approved predecessors."""
        if artifact_key not in FOUNDATION_STEP_ORDER:
            raise ValueError(f"未知作品基座步骤: {artifact_key}")

        def require(key: str) -> dict[str, Any]:
            artifact = approved.get(key)
            if artifact is None:
                raise ValueError(
                    f"生成 {FOUNDATION_STEP_LABELS[artifact_key]} 前必须先批准 "
                    f"{FOUNDATION_STEP_LABELS[key]}"
                )
            return artifact.content

        profile = inp.complexity_profile
        if artifact_key != "spec00" and "spec00" in approved:
            approved_profile = approved["spec00"].content.get("complexity_profile")
            if isinstance(approved_profile, dict):
                profile = approved_profile

        if artifact_key == "spec00":
            step_key = "graph1.stage.spec00"
            object_type = AuthObjectType.BIBLE
            input_pack = {"user_brief": inp.user_brief, "complexity_profile": profile}
        elif artifact_key == "world_a":
            step_key = "graph1.world.A"
            object_type = AuthObjectType.BIBLE
            input_pack = {
                "user_brief": inp.user_brief,
                "spec00_content": require("spec00"),
                "complexity_profile": profile,
            }
        elif artifact_key == "world_b":
            step_key = "graph1.world.B"
            object_type = AuthObjectType.BIBLE
            input_pack = {
                "user_brief": inp.user_brief,
                "spec00_content": require("spec00"),
                "world_a_content": require("world_a"),
                "complexity_profile": profile,
            }
        elif artifact_key == "pow_l":
            step_key = "graph1.pow.L"
            object_type = AuthObjectType.REG
            input_pack = {
                "spec00_content": require("spec00"),
                "world_a_content": require("world_a"),
                "complexity_profile": profile,
            }
        elif artifact_key == "pow_s":
            step_key = "graph1.pow.S"
            object_type = AuthObjectType.REG
            input_pack = {
                "spec00_content": require("spec00"),
                "world_a_content": require("world_a"),
                "world_b_content": require("world_b"),
                "pow_l_content": require("pow_l"),
                "complexity_profile": profile,
            }
        elif artifact_key == "pow_e":
            step_key = "graph1.pow.E"
            object_type = AuthObjectType.REG
            input_pack = {
                "spec00_content": require("spec00"),
                "world_a_content": require("world_a"),
                "pow_l_content": require("pow_l"),
                "pow_s_content": require("pow_s"),
                "complexity_profile": profile,
            }
        elif artifact_key == "opp_eco":
            step_key = "graph1.opp.eco"
            object_type = AuthObjectType.CHAR
            input_pack = {
                "spec00_content": require("spec00"),
                "world_a_content": require("world_a"),
                "world_b_content": require("world_b"),
                "pow_l_content": require("pow_l"),
                "pow_s_content": require("pow_s"),
                "pow_e_content": require("pow_e"),
                "complexity_profile": profile,
            }
        else:
            step_key = "graph1.cast.core"
            object_type = AuthObjectType.CHAR
            input_pack = {
                "user_brief": inp.user_brief,
                "spec00_content": require("spec00"),
                "world_b_content": require("world_b"),
                "opp_eco_content": require("opp_eco"),
                "complexity_profile": profile,
            }

        if artifact_key == "cast":
            return self._generate_cast(inp, input_pack)

        _logger.info(f"graph1_step {artifact_key} run={inp.run_id}")
        parsed = self._run_structured_step(
            step_key=step_key,
            input_pack=input_pack,
            run_id=inp.run_id,
            diagnostic_key=artifact_key,
            validator=lambda value: validate_foundation_content(
                artifact_key,
                value,
                complexity_level=str(profile.get("level") or "medium"),
            ),
        )
        artifact = self._make_auth_object(
            run_id=inp.run_id,
            project_id=inp.project_id,
            object_id=artifact_key,
            object_type=object_type,
            result_parsed=parsed,
            fallback_label=artifact_key,
        )
        if artifact_key == "spec00":
            generated_profile = artifact.content.get("complexity_profile", {})
            artifact.content["complexity_profile"] = {
                **(generated_profile if isinstance(generated_profile, dict) else {}),
                **inp.complexity_profile,
            }
        return artifact

    def _generate_cast(self, inp: Graph1Input, base_input: dict[str, Any]) -> AuthObject:
        """Build the eighth file as roster -> dossiers -> relationship boundaries.

        Each model response stays small and independently validated.  The final
        authority file remains compatible with downstream code while the asset
        catalog exposes every character as its own editable logical file.
        """
        level = str(base_input.get("complexity_profile", {}).get("level") or "medium")
        _logger.info(f"graph1_step cast.roster run={inp.run_id}")
        roster_output = self._run_structured_step(
            step_key="graph1.cast.roster",
            input_pack=base_input,
            run_id=inp.run_id,
            diagnostic_key="cast_roster",
            validator=lambda value: validate_cast_roster(value, level),
        )
        roster = list(roster_output["roster"])

        characters: list[dict[str, Any]] = []
        for index, roster_entry in enumerate(roster, start=1):
            expected_id = str(roster_entry["id"])
            _logger.info(
                f"graph1_step cast.dossier {index}/{len(roster)} "
                f"character={expected_id} run={inp.run_id}"
            )
            dossier_output = self._run_structured_step(
                step_key="graph1.cast.dossier",
                input_pack={
                    **base_input,
                    "roster": roster,
                    "roster_entry": roster_entry,
                    "completed_characters": characters,
                    "character_index": index,
                    "character_total": len(roster),
                },
                run_id=inp.run_id,
                diagnostic_key=f"cast_dossier_{expected_id}",
                validator=lambda value: validate_character_dossier(value, expected_id),
            )
            characters.append(dict(dossier_output["character"]))

        character_ids = {str(item["id"]) for item in characters}
        _logger.info(f"graph1_step cast.relations run={inp.run_id}")
        relation_output = self._run_structured_step(
            step_key="graph1.cast.relations",
            input_pack={
                **base_input,
                "characters": characters,
            },
            run_id=inp.run_id,
            diagnostic_key="cast_relations",
            validator=lambda value: validate_cast_relations(value, character_ids),
        )
        content = {
            "characters": characters,
            "relationships": relation_output["relationships"],
            "knowledge_boundaries": relation_output["knowledge_boundaries"],
            "ensemble_balance": relation_output["ensemble_balance"],
        }
        final_errors = validate_foundation_content("cast", content, complexity_level=level)
        if final_errors:
            path = self._persist_failure(
                run_id=inp.run_id,
                diagnostic_key="cast_assembly",
                step_key="graph1.cast.assembly",
                error="最终角色文件组装校验失败",
                validation_errors=final_errors,
                parsed=content,
            )
            raise ValueError(
                "初始化步骤 cast 结构不完整："
                f"{format_validation_errors(final_errors)}；失败记录：{path.name}"
            )
        return self._make_auth_object(
            run_id=inp.run_id,
            project_id=inp.project_id,
            object_id="cast",
            object_type=AuthObjectType.CHAR,
            result_parsed=content,
            fallback_label="cast",
        )

    def _run_structured_step(
        self,
        *,
        step_key: str,
        input_pack: dict[str, Any],
        run_id: str,
        diagnostic_key: str,
        validator: Callable[[Any], list[str]],
    ) -> dict[str, Any]:
        """Run one JSON step, retry invalid shapes, and persist every final failure."""
        try:
            result = self._runner.run(
                step_key=step_key,
                input_pack=input_pack,
                run_id=run_id,
                parsed_validator=lambda value: not validator(value),
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

        validation_errors = validator(result.parsed)
        if not result.ok or not isinstance(result.parsed, dict) or validation_errors:
            if not validation_errors:
                validation_errors = ["模型重试后仍未返回可用的 JSON 对象"]
            path = self._persist_failure(
                run_id=run_id,
                diagnostic_key=diagnostic_key,
                step_key=step_key,
                error="结构化输出校验失败",
                validation_errors=validation_errors,
                parsed=result.parsed,
                raw_text=result.text,
                call_records=[item.model_dump(mode="json") for item in result.call_records],
                candidates=[item.model_dump(mode="json") for item in result.candidates],
            )
            raise ValueError(
                f"初始化步骤 {diagnostic_key} 结构不完整："
                f"{format_validation_errors(validation_errors)}；失败记录：{path.name}"
            )
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
        path = self._layout.run_failure_path(run_id, diagnostic_key)
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
        _logger.error(f"foundation_failure_saved run={run_id} step={step_key} path={path}")
        return path

    # ── 内部工具 ──────────────────────────────────────────────────────────

    @staticmethod
    def _make_auth_object(
        run_id: str,
        project_id: str,
        object_id: str,
        object_type: AuthObjectType,
        result_parsed: object,
        fallback_label: str,
    ) -> AuthObject:
        now = utcnow()
        content: dict[str, Any] = {}
        if isinstance(result_parsed, dict):
            content = result_parsed
        else:
            content = {"_label": fallback_label, "_raw": str(result_parsed)}
        return AuthObject(
            object_id=object_id,
            project_id=project_id,
            object_type=object_type,
            version=1,
            content=content,
            created_at=now,
            updated_at=now,
            committed_by_run_id=run_id,
        )

    @staticmethod
    def _make_receipt(run_id: str, label: str) -> CommitReceipt:
        now = utcnow()
        return CommitReceipt(
            receipt_id=new_receipt_id(),
            run_id=run_id,
            staging_id=f"stg_{label}_{run_id}",
            commit_type="auth_patch",
            committed_objects=[label],
            committed_at=now,
        )

    @staticmethod
    def _require_object_result(result: StepResult, label: str) -> None:
        if not result.ok or not isinstance(result.parsed, dict) or set(result.parsed) == {"_raw"}:
            raise ValueError(f"初始化步骤 {label} 未返回合法 JSON 对象")
