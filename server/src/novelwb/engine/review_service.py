"""Orchestrator — 顶层调度器。

职责：
- 组装 GraphDeps（LLM adapter + PromptRegistry + StepSpecs）
- 路由到对应的图执行器
- 提供高层 pipeline 入口：run_event_pipeline / run_auth_pipeline / run_regression
"""

from __future__ import annotations

from typing import Any

from novelwb.core.constants import AuthObjectType, Defaults, StagingType
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ChapterSpec,
    ContextPackage,
    DiffReport,
    EventDraft,
    FatigueReport,
    ObservedDelta,
    ReviewAuditIssue,
    ReviewAuditResult,
    ReviewRevisionResult,
    StateSnapshot,
)
from novelwb.core.schemas.patch_models import StagingPacket, VerifyResult
from novelwb.engine.foundation_validation import (
    format_validation_errors,
    validate_foundation_content,
)
from novelwb.engine.graphs import (
    FOUNDATION_STEP_LABELS,
    FOUNDATION_STEP_ORDER,
    Graph2,
    Graph4,
    Graph5Input,
    GraphEInput,
    event_plan_steps,
    execution_report_from_event_plan,
    invalidate_event_plan_downstream,
    master_plan_steps,
    merge_event_plan_step,
    merge_legacy_event_plan,
    merge_master_plan_step,
    next_event_plan_step,
    next_master_plan_step,
    next_volume_plan_step,
    reopen_event_plan_from_step,
    volume_plan_steps,
)
from novelwb.engine.graphs.graph_2 import MasterPlanStep
from novelwb.engine.graphs.graph_3 import VolumePlanStep
from novelwb.engine.graphs.graph_4 import EventPlanStep
from novelwb.engine.prose_quality import ProseQualityEvaluator
from novelwb.engine.status_card_projector import project_initial_status_cards
from novelwb.utils.ids import new_staging_id
from novelwb.utils.timeutil import utcnow
from novelwb.utils.transactions import atomic_method


class ReviewService:
    """Audit, revision and human approval operations for one project."""

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._orchestrator, name)

    @atomic_method
    def approve_workflow_review(
        self, staging_id: str, edited: dict[str, Any], run_id: str = ""
    ) -> dict[str, Any]:
        packet = self._staging_store.load_optional(staging_id)
        if packet is None or not packet.content.get("review_kind"):
            raise ValueError("审核任务不存在")
        status = packet.content.get("status", "pending")
        if status == "approved":
            return packet.content.get("approval_result") or {
                "approved": True,
                "review_kind": packet.content["review_kind"],
                "already_approved": True,
            }
        if status != "pending":
            raise ValueError("该审核任务已驳回，不能批准")
        result = self._approve_pending(staging_id, edited, run_id)
        fresh = self._staging_store.load(staging_id)
        self._staging_store.save(
            fresh.model_copy(
                update={
                    "content": {
                        **fresh.content,
                        "approval_result": result,
                    }
                }
            )
        )
        return result

    def audit_workflow_review(
        self,
        staging_id: str,
        edited: dict[str, Any],
        run_id: str = "",
    ) -> dict[str, Any]:
        """Audit the current complete staging draft and generate revision feedback only."""
        with self._review_revision_lock:
            packet = self._staging_store.load_optional(staging_id)
            if packet is None or not packet.content.get("review_kind"):
                raise ValueError("审核任务不存在")
            if packet.content.get("status", "pending") != "pending":
                raise ValueError("只有待审核稿可以执行 AI 审核")

            kind = str(packet.content.get("review_kind") or "")
            if kind not in {"event_plan", "prose"}:
                raise ValueError("当前版本仅支持审核事件规划文件和正文草稿")

            content = dict(packet.content)
            internal = dict(content.get("internal") or {})
            baseline = dict(edited or content.get("editable") or {})
            rid = run_id or packet.run_id
            original_packet_editable = dict(content.get("editable") or {})
            full_context: dict[str, Any] = {
                "authority_bundle": [
                    item.model_dump(mode="json") for item in self._auth_store.load_bundle()
                ],
                "context_package": internal.get("context_package") or {},
                "event_slot": internal.get("event_slot") or {},
                "execution_report": internal.get("execution_report") or {},
            }
            mechanical_quality = None

            if kind == "event_plan":
                original_content = baseline.get("content")
                if not isinstance(original_content, dict):
                    raise ValueError("当前事件规划文件必须是 JSON 对象")
                step_id = str(internal.get("event_plan_step") or "")
                step = next(
                    (item for item in event_plan_steps() if item.step_id == step_id),
                    None,
                )
                if step is None:
                    raise ValueError("旧版整包事件方案暂不支持独立审核")
                volume_index = max(1, int(internal.get("volume_index") or 1))
                current = self._load_volume_contract(volume_index) or self._auth_store.load_latest(
                    "CONTRACT"
                )
                if current is None:
                    raise ValueError("当前卷契约不存在，无法审核事件规划")
                expected_version = int(internal.get("base_version") or 0)
                if current.version != expected_version:
                    raise ValueError(
                        f"事件规划所属卷版本已从 v{expected_version} "
                        f"更新到 v{current.version}；"
                        "请刷新后重新生成当前文件"
                    )
                event_id = str(internal.get("event_id") or "")
                expected_step = next_event_plan_step(current.content, event_id)
                if expected_step is None or expected_step.step_id != step.step_id:
                    raise ValueError("当前审核文件已不再是下一可处理步骤，请刷新工作流")
                full_context["approved_event_files"] = execution_report_from_event_plan(
                    current.content, event_id
                )
                constraints: dict[str, Any] = {
                    "file_type": "json_object",
                    "step_id": step.step_id,
                    "step_label": step.label,
                    "required_fields": list(step.required_fields),
                    "event_id": event_id,
                }
            else:
                original_content = str(baseline.get("draft_text") or "").strip()
                if not original_content:
                    raise ValueError("当前正文不能为空")
                expected_volume_version = int(internal.get("volume_version") or 0)
                if expected_volume_version:
                    volume_index = max(1, int(internal.get("volume_index") or 1))
                    current = self._load_volume_contract(volume_index)
                    if current is None or current.version != expected_volume_version:
                        actual = current.version if current is not None else 0
                        raise ValueError(
                            f"正文依据的事件规划版本已从 v{expected_volume_version} "
                            f"更新到 v{actual}；"
                            "请根据最新规划重新生成正文"
                        )
                target_chars = int(
                    dict(internal.get("budget_report") or {}).get("total_chars") or 0
                )
                evaluator = ProseQualityEvaluator(Defaults.MIN_EVENT_PROSE_SCORE)
                mechanical_quality = evaluator.evaluate(original_content, target_chars=target_chars)
                mechanical_quality_report = {
                    **mechanical_quality.to_dict(),
                    "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                    "audited_rechecked": True,
                }
                full_context["mechanical_quality_report"] = mechanical_quality_report
                constraints = {
                    "file_type": "plain_prose_string",
                    "return_feedback_only": True,
                    "target_chars": target_chars,
                    "minimum_quality_score": Defaults.MIN_EVENT_PROSE_SCORE,
                    "mechanical_quality_passed": mechanical_quality.passed,
                }

            def valid_audit(value: Any) -> bool:
                try:
                    report = ReviewAuditResult.model_validate(value)
                except Exception:
                    return False
                verdict = report.verdict.strip().lower()
                return verdict in {"pass", "revise"} and bool(report.summary.strip())

            result = self._review_runner.run(
                "graphR.workflow.audit",
                {
                    "review_kind": kind,
                    "file_label": str(content.get("title") or "审核稿"),
                    "review_feedback": "",
                    "original_content": original_content,
                    "required_constraints": constraints,
                    "full_context": full_context,
                },
                run_id=rid,
                parsed_validator=valid_audit,
            )
            if not result.ok:
                raise ValueError("模型未返回结构完整的审核报告，请稍后重试")
            report = ReviewAuditResult.model_validate(result.parsed)
            if mechanical_quality is not None and not mechanical_quality.passed:
                problem = "；".join(mechanical_quality.issues) or "机械质量检查未通过"
                mechanical_issue = ReviewAuditIssue(
                    severity="major",
                    category="机械质量",
                    location_anchor="全文",
                    problem=problem,
                    authority_basis=(
                        f"确定性正文质量分 {mechanical_quality.score:.2f}，"
                        f"批准阈值 {Defaults.MIN_EVENT_PROSE_SCORE:.0f}"
                    ),
                    revision_instruction="按机械质量报告修正长度、重复、句长节奏或段落问题，再重新审核当前稿",
                )
                existing_issues = list(report.issues)
                if not any(issue.category == "机械质量" for issue in existing_issues):
                    existing_issues.insert(0, mechanical_issue)
                quality_feedback = f"必须先处理机械质量问题：{problem}。{report.revision_feedback}"
                report = report.model_copy(
                    update={
                        "verdict": "revise",
                        "summary": f"机械质量门未通过；{report.summary}",
                        "issues": existing_issues,
                        "revision_feedback": quality_feedback,
                    }
                )

            fresh = self._staging_store.load_optional(staging_id)
            if (
                fresh is None
                or fresh.content.get("status", "pending") != "pending"
                or dict(fresh.content.get("editable") or {}) != original_packet_editable
            ):
                raise ValueError("审核稿在 AI 审核期间已发生变化，本次报告未保存；请刷新后重试")

            history = list(internal.get("audit_history") or [])
            audit_no = int(history[-1].get("audit_no") or 0) + 1 if history else 1
            history.append(
                {
                    "audit_no": audit_no,
                    "report": report.model_dump(mode="json"),
                    "audited_editable": baseline,
                    "basis_revision_count": len(internal.get("revision_history") or []),
                    "created_at": utcnow().isoformat(),
                    "input_tokens": sum(item.input_tokens for item in result.call_records),
                    "output_tokens": sum(item.output_tokens for item in result.call_records),
                }
            )
            internal["audit_history"] = history[-20:]
            if mechanical_quality is not None:
                internal["quality_report"] = {
                    **mechanical_quality.to_dict(),
                    "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                    "audited_rechecked": True,
                }
            updated_content = dict(fresh.content)
            updated_content["editable"] = baseline
            updated_content["internal"] = internal
            updated = fresh.model_copy(update={"content": updated_content})
            self._staging_store.save(updated)
            return self._review_payload(updated)

    def revise_workflow_review(
        self,
        staging_id: str,
        edited: dict[str, Any],
        feedback: str,
        run_id: str = "",
    ) -> dict[str, Any]:
        """Revise the current staging draft in place without rerunning prior workflow steps."""
        feedback = feedback.strip()
        if not feedback:
            raise ValueError("请填写具体修改意见")
        if len(feedback) > 8000:
            raise ValueError("修改意见不能超过 8000 个字符")

        with self._review_revision_lock:
            packet = self._staging_store.load_optional(staging_id)
            if packet is None or not packet.content.get("review_kind"):
                raise ValueError("审核任务不存在")
            if packet.content.get("status", "pending") != "pending":
                raise ValueError("只有待审核稿可以继续修订")

            kind = str(packet.content.get("review_kind") or "")
            if kind not in {"event_plan", "prose"}:
                raise ValueError("当前版本仅支持事件规划文件和正文草稿的定向修订")

            content = dict(packet.content)
            internal = dict(content.get("internal") or {})
            baseline = dict(edited or content.get("editable") or {})
            rid = run_id or packet.run_id
            original_packet_editable = dict(content.get("editable") or {})
            authority_bundle = [
                item.model_dump(mode="json") for item in self._auth_store.load_bundle()
            ]
            full_context: dict[str, Any] = {
                "authority_bundle": authority_bundle,
                "context_package": internal.get("context_package") or {},
                "event_slot": internal.get("event_slot") or {},
                "execution_report": internal.get("execution_report") or {},
            }
            constraints: dict[str, Any]

            if kind == "event_plan":
                original_content = baseline.get("content")
                if not isinstance(original_content, dict):
                    raise ValueError("当前事件规划文件必须是 JSON 对象")
                step_id = str(internal.get("event_plan_step") or "")
                step = next(
                    (item for item in event_plan_steps() if item.step_id == step_id),
                    None,
                )
                if step is None:
                    raise ValueError("旧版整包事件方案暂不支持定向修订")
                volume_index = max(1, int(internal.get("volume_index") or 1))
                current = self._load_volume_contract(volume_index) or self._auth_store.load_latest(
                    "CONTRACT"
                )
                if current is None:
                    raise ValueError("当前卷契约不存在，无法修订事件规划")
                expected_version = int(internal.get("base_version") or 0)
                if current.version != expected_version:
                    raise ValueError(
                        f"事件规划所属卷版本已从 v{expected_version} "
                        f"更新到 v{current.version}；"
                        "请刷新后重新生成当前文件"
                    )
                event_id = str(internal.get("event_id") or "")
                expected_step = next_event_plan_step(current.content, event_id)
                if expected_step is None or expected_step.step_id != step.step_id:
                    raise ValueError("当前审核文件已不再是下一可处理步骤，请刷新工作流")
                full_context["approved_event_files"] = execution_report_from_event_plan(
                    current.content, event_id
                )
                constraints = {
                    "file_type": "json_object",
                    "step_id": step.step_id,
                    "step_label": step.label,
                    "required_fields": list(step.required_fields),
                    "preserve_root_fields": list(original_content.keys()),
                    "event_id": event_id,
                }
            else:
                original_content = str(baseline.get("draft_text") or "").strip()
                if not original_content:
                    raise ValueError("当前正文不能为空")
                expected_volume_version = int(internal.get("volume_version") or 0)
                if expected_volume_version:
                    volume_index = max(1, int(internal.get("volume_index") or 1))
                    current = self._load_volume_contract(volume_index)
                    if current is None or current.version != expected_volume_version:
                        actual = current.version if current is not None else 0
                        raise ValueError(
                            f"正文依据的事件规划版本已从 v{expected_volume_version} "
                            f"更新到 v{actual}；"
                            "请根据最新规划重新生成正文"
                        )
                target_chars = int(
                    dict(internal.get("budget_report") or {}).get("total_chars") or 0
                )
                constraints = {
                    "file_type": "plain_prose_string",
                    "return_complete_text": True,
                    "forbid_internal_markers": True,
                    "target_chars": target_chars,
                    "minimum_quality_score": Defaults.MIN_EVENT_PROSE_SCORE,
                }

            def valid_revision(value: Any) -> bool:
                try:
                    result = ReviewRevisionResult.model_validate(value)
                except Exception:
                    return False
                revised = result.revised_content
                if kind == "event_plan":
                    return isinstance(revised, dict)
                return isinstance(revised, str) and bool(revised.strip())

            result = self._review_runner.run(
                "graphR.workflow.revise",
                {
                    "review_kind": kind,
                    "file_label": str(content.get("title") or "审核稿"),
                    "review_feedback": feedback,
                    "original_content": original_content,
                    "required_constraints": constraints,
                    "full_context": full_context,
                },
                run_id=rid,
                parsed_validator=valid_revision,
            )
            if not result.ok:
                raise ValueError("模型未返回结构完整的修订稿，请稍后重试")
            revision = ReviewRevisionResult.model_validate(result.parsed)

            if kind == "event_plan":
                assert step is not None
                revised_content = revision.revised_content
                errors = self._graph_4.validate_review_step(step, revised_content)
                if errors:
                    raise ValueError(f"修订后的{step.label}结构校验失败：{'；'.join(errors)}")
                revised_editable = {**baseline, "content": revised_content}
            else:
                revised_text = str(revision.revised_content).strip()
                revised_editable = {**baseline, "draft_text": revised_text}
                target_chars = int(
                    dict(internal.get("budget_report") or {}).get("total_chars") or 0
                )
                quality = ProseQualityEvaluator(Defaults.MIN_EVENT_PROSE_SCORE).evaluate(
                    revised_text, target_chars=target_chars
                )
                internal["quality_report"] = {
                    **quality.to_dict(),
                    "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                    "revised_from_review": True,
                }
                draft = EventDraft.model_validate(internal["draft"])
                internal["draft"] = draft.model_copy(
                    update={
                        "draft_text": revised_text,
                        "word_count": len(revised_text),
                    }
                ).model_dump(mode="json")

            fresh = self._staging_store.load_optional(staging_id)
            if (
                fresh is None
                or fresh.content.get("status", "pending") != "pending"
                or dict(fresh.content.get("editable") or {}) != original_packet_editable
            ):
                raise ValueError("审核稿在修订期间已发生变化，本次结果未覆盖；请刷新后重试")

            history = list(internal.get("revision_history") or [])
            revision_no = int(history[-1].get("revision_no") or 0) + 1 if history else 1
            history.append(
                {
                    "revision_no": revision_no,
                    "feedback": feedback,
                    "change_summary": revision.change_summary,
                    "preserved_summary": revision.preserved_summary,
                    "before_editable": baseline,
                    "created_at": utcnow().isoformat(),
                    "input_tokens": sum(item.input_tokens for item in result.call_records),
                    "output_tokens": sum(item.output_tokens for item in result.call_records),
                }
            )
            internal["revision_history"] = history[-20:]
            updated_content = dict(fresh.content)
            updated_content["editable"] = revised_editable
            updated_content["internal"] = internal
            updated = fresh.model_copy(update={"content": updated_content})
            self._staging_store.save(updated)
            return self._review_payload(updated)

    def _approve_pending(
        self, staging_id: str, edited: dict[str, Any], run_id: str = ""
    ) -> dict[str, Any]:
        step: MasterPlanStep | VolumePlanStep | EventPlanStep | None
        expected_step: MasterPlanStep | VolumePlanStep | EventPlanStep | None
        steps: list[MasterPlanStep] | list[VolumePlanStep] | list[EventPlanStep]
        packet = self._staging_store.load_optional(staging_id)
        if packet is None or not packet.content.get("review_kind"):
            raise ValueError("审核任务不存在")
        kind = str(packet.content["review_kind"])
        rid = run_id or packet.run_id
        content = dict(packet.content)
        editable = edited or dict(content.get("editable") or {})

        if kind == "asset_edit":
            if content.get("status", "pending") != "pending":
                raise ValueError("该资产审核任务已经处理")
            internal = dict(content.get("internal") or {})
            asset_id = str(internal.get("asset_id") or "")
            if str(editable.get("asset_id") or "") != asset_id:
                raise ValueError("审核稿不能切换到其他分层资产")
            if "content" not in editable:
                raise ValueError("审核稿缺少资产内容")
            spec, original, merged = self._asset_catalog.merge_authority_edit(
                asset_id,
                editable["content"],
                expected_version=int(internal.get("base_version") or 0),
            )
            if (
                spec.owner_stage == "event_plan"
                and len(spec.path) >= 4
                and spec.path[0] == "event_plans"
                and spec.path[2] == "files"
            ):
                merged = invalidate_event_plan_downstream(
                    merged,
                    event_id=str(spec.path[1]),
                    step_id=str(spec.path[3]),
                )
            if spec.artifact_key in FOUNDATION_STEP_ORDER:
                level = self._foundation_complexity_level(
                    spec.artifact_key,
                    merged,
                )
                errors = validate_foundation_content(
                    spec.artifact_key,
                    merged,
                    complexity_level=level,
                )
                if errors:
                    raise ValueError(
                        f"{spec.label} 结构校验失败：{format_validation_errors(errors)}"
                    )
            revised = original.model_copy(
                update={
                    "content": merged,
                    "updated_at": utcnow(),
                    "committed_by_run_id": rid,
                }
            )
            committed = self._auth_store.commit(revised)
            cards = project_initial_status_cards(self._auth_store.load_bundle())
            self._context_store.seed_authority_cards(cards, rid)
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "asset_id": asset_id,
                "artifact_key": spec.artifact_key,
                "committed": [committed.object_id],
                "version": committed.version,
                "downstream": list(spec.downstream),
            }

        if kind == "master_plan" and content.get("internal", {}).get("master_step"):
            if content.get("status", "pending") != "pending":
                raise ValueError("该全书规划审核任务已经处理")
            internal = dict(content.get("internal") or {})
            step_id = str(internal.get("master_step") or "")
            if "content" not in editable:
                raise ValueError("审核稿缺少当前逻辑文件内容")
            cast = self._auth_store.load_artifact("cast")
            if cast is None:
                raise ValueError("核心角色文件不存在，无法批准全书规划")
            current = self._auth_store.load_artifact("longline")
            current_version = current.version if current is not None else 0
            expected_version = int(internal.get("base_version") or 0)
            if current_version != expected_version:
                raise ValueError(
                    f"全书规划权威版本已从 v{expected_version} 更新到 v{current_version}；"
                    "请重新生成当前文件，避免覆盖前序修改"
                )
            current_content = current.content if current is not None else {}
            steps = master_plan_steps(cast.content, current_content)
            step = next((item for item in steps if item.step_id == step_id), None)
            if step is None:
                raise ValueError(f"未知全书规划步骤：{step_id}")
            expected_step = next_master_plan_step(current_content, cast.content)
            if expected_step is None or expected_step.step_id != step.step_id:
                raise ValueError("当前审核文件已不再是下一可批准步骤，请刷新工作流")
            known_ids = {
                str(item.get("id"))
                for item in cast.content.get("characters", [])
                if isinstance(item, dict) and item.get("id")
            }
            edited_content = editable["content"]
            errors = Graph2.validate_step_content(step, edited_content, known_ids)
            if errors:
                raise ValueError(f"{step.label}结构校验失败：{'；'.join(errors)}")
            merged = merge_master_plan_step(current_content, step, edited_content)
            now = utcnow()
            if current is None:
                revised = AuthObject(
                    object_id="longline",
                    project_id=self._cfg.project_id,
                    object_type=AuthObjectType.CONTRACT,
                    version=1,
                    content=merged,
                    created_at=now,
                    updated_at=now,
                    committed_by_run_id=rid,
                )
            else:
                revised = current.model_copy(
                    update={
                        "content": merged,
                        "updated_at": now,
                        "committed_by_run_id": rid,
                    }
                )
            committed = self._auth_store.commit(revised)
            cards = project_initial_status_cards(self._auth_store.load_bundle())
            self._context_store.seed_authority_cards(cards, rid)
            self._mark_review(packet, "approved", editable)
            completed = next_master_plan_step(committed.content, cast.content) is None
            return {
                "approved": True,
                "review_kind": kind,
                "master_step": step.step_id,
                "asset_id": step.asset_id,
                "committed": [committed.object_id],
                "version": committed.version,
                "master_plan_complete": completed,
            }

        if kind == "volume_plan" and content.get("internal", {}).get("volume_step"):
            if content.get("status", "pending") != "pending":
                raise ValueError("该卷规划审核任务已经处理")
            internal = dict(content.get("internal") or {})
            step_id = str(internal.get("volume_step") or "")
            volume_index = max(1, int(internal.get("volume_index") or 1))
            events_per_volume = max(1, int(internal.get("events_per_volume") or 30))
            if "content" not in editable:
                raise ValueError("审核稿缺少当前卷级逻辑文件内容")
            longline = self._load_latest_longline()
            if longline is None:
                raise ValueError("全书总纲不存在，无法批准卷规划")
            current = self._load_volume_contract(volume_index)
            current_version = current.version if current is not None else 0
            expected_version = int(internal.get("base_version") or 0)
            if current_version != expected_version:
                raise ValueError(
                    f"第{volume_index}卷权威版本已从 v{expected_version} "
                    f"更新到 v{current_version}；"
                    "请重新生成当前文件，避免覆盖前序修改"
                )
            current_content = current.content if current is not None else {}
            steps = volume_plan_steps(events_per_volume)
            step = next((item for item in steps if item.step_id == step_id), None)
            if step is None:
                raise ValueError(f"未知卷规划步骤：{step_id}")
            expected_step = next_volume_plan_step(current_content, events_per_volume)
            if expected_step is None or expected_step.step_id != step.step_id:
                raise ValueError("当前审核文件已不再是下一可批准步骤，请刷新工作流")
            edited_content = editable["content"]
            errors = self._graph_3.validate_review_step(
                step=step,
                generated=edited_content,
                approved_content=current_content,
                longline_content=longline.content,
                events_per_volume=events_per_volume,
            )
            if errors:
                raise ValueError(f"{step.label}结构校验失败：{'；'.join(errors)}")
            merged = self._graph_3.merge_review_step(
                step=step,
                generated=edited_content,
                approved_content=current_content,
                volume_index=volume_index,
                events_per_volume=events_per_volume,
            )
            now = utcnow()
            if current is None:
                revised = AuthObject(
                    object_id=f"volume_vol_{volume_index:03d}",
                    project_id=self._cfg.project_id,
                    object_type=AuthObjectType.CONTRACT,
                    version=1,
                    content=merged,
                    created_at=now,
                    updated_at=now,
                    committed_by_run_id=rid,
                )
            else:
                revised = current.model_copy(
                    update={
                        "content": merged,
                        "updated_at": now,
                        "committed_by_run_id": rid,
                    }
                )
            committed = self._auth_store.commit(revised)
            completed = next_volume_plan_step(committed.content, events_per_volume) is None
            if completed:
                cards = project_initial_status_cards(self._auth_store.load_bundle())
                self._context_store.seed_authority_cards(cards, rid)
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "volume_step": step.step_id,
                "asset_id": step.asset_id,
                "committed": [committed.object_id],
                "version": committed.version,
                "volume_plan_complete": completed,
            }

        if kind in {"foundation", "master_plan", "volume_plan"}:
            originals = {
                item["artifact_key"]: AuthObject.model_validate(item["object"])
                for item in content.get("internal", {}).get("artifacts", [])
            }
            edited_artifacts = editable.get("artifacts", [])
            edited_keys = {str(item.get("artifact_key") or "") for item in edited_artifacts}
            if edited_keys != set(originals):
                raise ValueError("审核稿必须保留该阶段的全部权威产物")
            committed_objects: list[AuthObject] = []
            for item in edited_artifacts:
                key = str(item.get("artifact_key") or "")
                original = originals.get(key)
                if original is None:
                    raise ValueError(f"未知权威产物: {key}")
                edited_content = dict(item.get("content") or {})
                if kind == "foundation":
                    errors = validate_foundation_content(
                        key,
                        edited_content,
                        complexity_level=self._foundation_complexity_level(
                            key,
                            edited_content,
                        ),
                    )
                    if errors:
                        raise ValueError(
                            f"{FOUNDATION_STEP_LABELS.get(key, key)} 结构校验失败："
                            f"{format_validation_errors(errors)}"
                        )
                revised = original.model_copy(
                    update={
                        "content": edited_content,
                        "updated_at": utcnow(),
                        "committed_by_run_id": rid,
                    }
                )
                committed_objects.append(self._auth_store.commit(revised))
            if kind in {"foundation", "master_plan", "volume_plan"}:
                cards = project_initial_status_cards(self._auth_store.load_bundle())
                self._context_store.seed_authority_cards(cards, rid)
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "committed": [item.object_id for item in committed_objects],
                "foundation_step": content.get("internal", {}).get("foundation_step"),
            }

        if kind == "event_plan":
            with self._event_approval_lock:
                fresh = self._staging_store.load_optional(staging_id)
                if fresh is None or fresh.content.get("status", "pending") != "pending":
                    raise ValueError("该事件规划审核任务已经处理")
                packet = fresh
                content = dict(packet.content)
                internal = dict(content.get("internal") or {})
                editable = edited or dict(content.get("editable") or {})
                event_index = max(1, int(internal.get("event_index") or 1))
                volume_index = max(1, int(internal.get("volume_index") or 1))
                current = self._load_volume_contract(volume_index) or self._auth_store.load_latest(
                    "CONTRACT"
                )
                if current is None:
                    raise ValueError("当前卷契约不存在，无法保存事件规划")

                step_id = str(internal.get("event_plan_step") or "")
                if step_id:
                    event_slot = dict(internal.get("event_slot") or {})
                    event_id = str(internal.get("event_id") or event_slot.get("slot_id") or "")
                    expected_version = int(internal.get("base_version") or 0)
                    if current.version != expected_version:
                        raise ValueError(
                            f"事件规划所属卷版本已从 v{expected_version} "
                            f"更新到 v{current.version}；"
                            "请重新生成当前文件，避免覆盖前序修改"
                        )
                    step = next(
                        (item for item in event_plan_steps() if item.step_id == step_id),
                        None,
                    )
                    if step is None:
                        raise ValueError(f"未知事件规划步骤：{step_id}")
                    expected_step = next_event_plan_step(current.content, event_id)
                    if expected_step is None or expected_step.step_id != step.step_id:
                        raise ValueError("当前审核文件已不再是下一可批准步骤，请刷新工作流")
                    generated = editable.get("content")
                    if not isinstance(generated, dict):
                        raise ValueError("事件规划内容必须是 JSON 对象")
                    errors = self._graph_4.validate_review_step(step, generated)
                    if errors:
                        raise ValueError(f"{step.label}结构校验失败：{'；'.join(errors)}")
                    merged = merge_event_plan_step(
                        current.content,
                        event_id=event_id,
                        event_index=event_index,
                        step=step,
                        generated=generated,
                    )
                else:
                    # v1 compatibility: approving an old aggregate plan now only
                    # saves its five files.  It never launches prose generation.
                    event_slot = dict(editable.get("event_slot") or {})
                    event_id = str(event_slot.get("slot_id") or f"evt_{event_index:03d}")
                    execution_report = dict(editable.get("execution_report") or {})
                    if not execution_report.get("scene_plan"):
                        raise ValueError("旧版事件展开方案缺少连续场景，无法迁移")
                    merged = merge_legacy_event_plan(
                        current.content,
                        event_id=event_id,
                        event_index=event_index,
                        execution_report=execution_report,
                    )
                    step = None

                revised = current.model_copy(
                    update={
                        "content": merged,
                        "updated_at": utcnow(),
                        "committed_by_run_id": rid,
                    }
                )
                committed = self._auth_store.commit(revised)
                self._mark_review(packet, "approved", editable)
                complete = next_event_plan_step(committed.content, event_id) is None
                return {
                    "approved": True,
                    "review_kind": kind,
                    "event_plan_step": step.step_id if step else "legacy_bundle",
                    "event_id": event_id,
                    "committed": [committed.object_id],
                    "version": committed.version,
                    "event_plan_complete": complete,
                }

        if kind == "prose":
            if content.get("status", "pending") != "pending":
                raise ValueError("该正文审核任务已经处理")
            internal = dict(content.get("internal") or {})
            expected_volume_version = int(internal.get("volume_version") or 0)
            if expected_volume_version:
                volume_index = max(1, int(internal.get("volume_index") or 1))
                current_volume = self._load_volume_contract(volume_index)
                if current_volume is None or current_volume.version != expected_volume_version:
                    actual = current_volume.version if current_volume is not None else 0
                    raise ValueError(
                        f"正文依据的事件规划版本已从 v{expected_volume_version} "
                        f"更新到 v{actual}；"
                        "请根据最新已批准规划重新生成正文"
                    )
            original = EventDraft.model_validate(internal["draft"])
            draft_text = str(editable.get("draft_text") or "").strip()
            if not draft_text:
                raise ValueError("正文不能为空")
            target_chars = int(dict(internal.get("budget_report") or {}).get("total_chars") or 0)
            manual_quality = ProseQualityEvaluator(Defaults.MIN_EVENT_PROSE_SCORE).evaluate(
                draft_text, target_chars=target_chars
            )
            if not manual_quality.passed:
                issues = "；".join(manual_quality.issues) or "机械质量检查未通过"
                actual_chars = int(manual_quality.metrics.get("char_count") or 0)
                raise ValueError(
                    f"正文质量仍未达标：{issues}；当前有效字符 {actual_chars}"
                    f"{f' / 目标 {target_chars}' if target_chars else ''}。"
                    "请继续修改，或驳回后重新生成。"
                )
            internal["quality_report"] = {
                **manual_quality.to_dict(),
                "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                "manually_rechecked": True,
            }
            draft = original.model_copy(
                update={"draft_text": draft_text, "word_count": len(draft_text)}
            )
            context_package = ContextPackage.model_validate(internal["context_package"])
            e_out = self._graph_e.run(
                GraphEInput(
                    run_id=rid,
                    event_id=draft.event_id,
                    draft=draft,
                    bible_auth=self._auth_store.load_artifact("spec00"),
                    context_package=context_package,
                    commit=False,
                    auto_repair=False,
                )
            )
            if e_out.aborted:
                failure_stage = getattr(e_out, "failure_stage", "")
                if failure_stage == "presnapshot":
                    stage_label = "事件前状态快照构建"
                    retry_label = "重试该提交"
                elif failure_stage == "reconcile":
                    stage_label = "事件事实对账与自动修复"
                    retry_label = "根据对账问题修改正文后重试"
                else:
                    stage_label = "事件状态差异提取"
                    retry_label = "直接重试状态差异提取"
                raise ValueError(
                    f"正文机械质量检查已通过；失败发生在下一阶段“{stage_label}”："
                    f"{e_out.abort_reason}。正文仍保留为待审核，可{retry_label}。"
                )
            next_packet = self._save_review_packet(
                run_id=rid,
                review_kind="state_delta",
                title="事件状态差异",
                staging_type=StagingType.STG_EVENT,
                editable={"observed_delta": e_out.observed_delta.model_dump(mode="json")},
                internal={
                    **internal,
                    "draft": draft.model_dump(mode="json"),
                    "pre_snapshot": e_out.pre_snapshot.model_dump(mode="json"),
                    "diff_report": e_out.diff_report.model_dump(mode="json"),
                    "context_package": context_package.model_dump(mode="json"),
                },
            )
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "next_review": self._review_payload(next_packet),
            }

        if kind == "state_delta":
            internal = dict(content.get("internal") or {})
            draft = EventDraft.model_validate(internal["draft"])
            observed_delta = ObservedDelta.model_validate(editable.get("observed_delta") or {})
            history = self._load_published_chapter_specs()
            c_out = self._graph_5.run(
                Graph5Input(
                    run_id=rid,
                    event_id=draft.event_id,
                    draft=draft,
                    history_chapter_specs=history,
                    project_id=self._cfg.project_id,
                    commit=False,
                )
            )
            next_packet = self._save_review_packet(
                run_id=rid,
                review_kind="chapter_plan",
                title="自然切章方案",
                staging_type=StagingType.STG_CHAPTER,
                editable={
                    "chapter_specs": [item.model_dump(mode="json") for item in c_out.chapter_specs],
                    "chapter_texts": c_out.chapter_texts,
                },
                internal={
                    **internal,
                    "observed_delta": observed_delta.model_dump(mode="json"),
                    "review_result": c_out.review_result.model_dump(mode="json"),
                    "fatigue_report": c_out.fatigue_report.model_dump(mode="json"),
                },
            )
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "next_review": self._review_payload(next_packet),
            }

        if kind == "chapter_plan":
            internal = dict(content.get("internal") or {})
            draft = EventDraft.model_validate(internal["draft"])
            context_package = ContextPackage.model_validate(internal["context_package"])
            chapter_specs = [
                ChapterSpec.model_validate(item) for item in editable.get("chapter_specs", [])
            ]
            chapter_texts = {
                str(key): str(value)
                for key, value in dict(editable.get("chapter_texts") or {}).items()
            }
            if not chapter_specs:
                raise ValueError("自然切章方案至少需要一章")
            missing_texts = [
                item.chapter_id
                for item in chapter_specs
                if not chapter_texts.get(item.chapter_id, "").strip()
            ]
            if missing_texts:
                raise ValueError(f"章节正文不能为空: {', '.join(missing_texts)}")
            e_out = self._graph_e.commit_reviewed(
                run_id=rid,
                event_id=draft.event_id,
                draft=draft,
                pre_snapshot=StateSnapshot.model_validate(internal["pre_snapshot"]),
                observed_delta=ObservedDelta.model_validate(internal["observed_delta"]),
                diff_report=DiffReport.model_validate(internal["diff_report"]),
                context_package=context_package,
            )
            self._context_store.apply_event_delta(e_out.observed_delta, draft.event_id)
            self._update_auth_from_event(e_out, draft.event_id, rid)
            c_out = self._graph_5.commit_reviewed(
                run_id=rid,
                event_id=draft.event_id,
                chapter_specs=chapter_specs,
                chapter_texts=chapter_texts,
                review_result=VerifyResult.model_validate(internal["review_result"]),
                fatigue_report=FatigueReport.model_validate(internal["fatigue_report"]),
            )
            self._mark_review(packet, "approved", editable)
            return {
                "approved": True,
                "review_kind": kind,
                "event_id": draft.event_id,
                "chapters": [item.model_dump(mode="json") for item in c_out.chapter_specs],
            }

        raise ValueError(f"不支持的审核类型: {kind}")

    def _foundation_complexity_level(
        self,
        artifact_key: str,
        edited_content: dict[str, Any],
    ) -> str:
        if artifact_key == "spec00":
            profile = edited_content.get("complexity_profile")
        else:
            spec00 = self._auth_store.load_artifact("spec00", include_invalidated=True)
            profile = spec00.content.get("complexity_profile") if spec00 else None
        level = (
            str(profile.get("level") or "medium").lower() if isinstance(profile, dict) else "medium"
        )
        return level if level in {"low", "medium", "high"} else "medium"

    @atomic_method
    def reject_workflow_review(self, staging_id: str) -> dict[str, Any]:
        packet = self._staging_store.load_optional(staging_id)
        if packet is None or not packet.content.get("review_kind"):
            raise ValueError("审核任务不存在")
        if packet.content.get("status", "pending") != "pending":
            raise ValueError("该审核任务已经处理")
        internal = dict(packet.content.get("internal") or {})
        editable = dict(packet.content.get("editable") or {})
        if packet.content.get("review_kind") == "prose":
            execution = dict(internal.get("execution_report") or {})
            prewrite = Graph4.normalize_prewrite_check(execution.get("prewrite_check"))
            if not bool(prewrite.get("passed")):
                with self._event_approval_lock:
                    fresh = self._staging_store.load_optional(staging_id)
                    if fresh is None or fresh.content.get("status", "pending") != "pending":
                        raise ValueError("该审核任务已经处理")
                    volume_index = max(1, int(internal.get("volume_index") or 1))
                    current = self._load_volume_contract(
                        volume_index
                    ) or self._auth_store.load_latest("CONTRACT")
                    if current is None:
                        raise ValueError("当前卷契约不存在，无法退回场景方案")
                    expected_version = int(internal.get("volume_version") or 0)
                    if expected_version and current.version != expected_version:
                        raise ValueError(
                            f"正文所属卷版本已从 v{expected_version} 更新到 v{current.version}；"
                            "请刷新后重新处理"
                        )
                    event_id = str(internal.get("event_id") or "")
                    merged = reopen_event_plan_from_step(
                        current.content,
                        event_id=event_id,
                        step_id="scene_plan",
                        revision_feedback=prewrite,
                    )
                    committed = self._auth_store.commit(
                        current.model_copy(
                            update={
                                "content": merged,
                                "updated_at": utcnow(),
                                "committed_by_run_id": packet.run_id,
                            }
                        )
                    )
                    self._mark_review(fresh, "rejected", editable)
                    return {
                        "rejected": True,
                        "review_kind": "prose",
                        "reopened_step": "scene_plan",
                        "event_id": event_id,
                        "version": committed.version,
                        "message": "当前正文依据的检查实际未通过，已携带问题退回连续场景方案",
                    }
        if (
            packet.content.get("review_kind") == "event_plan"
            and internal.get("event_plan_step") == "prewrite_assets"
        ):
            generated = editable.get("content")
            generated = generated if isinstance(generated, dict) else {}
            prewrite = Graph4.normalize_prewrite_check(generated.get("prewrite_check"))
            if not bool(prewrite.get("passed")):
                with self._event_approval_lock:
                    fresh = self._staging_store.load_optional(staging_id)
                    if fresh is None or fresh.content.get("status", "pending") != "pending":
                        raise ValueError("该审核任务已经处理")
                    current = self._load_volume_contract(
                        max(1, int(internal.get("volume_index") or 1))
                    ) or self._auth_store.load_latest("CONTRACT")
                    if current is None:
                        raise ValueError("当前卷契约不存在，无法退回场景方案")
                    expected_version = int(internal.get("base_version") or 0)
                    if current.version != expected_version:
                        raise ValueError(
                            f"事件规划所属卷版本已从 v{expected_version} "
                            f"更新到 v{current.version}；"
                            "请刷新后重新处理检查结果"
                        )
                    event_id = str(internal.get("event_id") or "")
                    merged = reopen_event_plan_from_step(
                        current.content,
                        event_id=event_id,
                        step_id="scene_plan",
                        revision_feedback=prewrite,
                    )
                    committed = self._auth_store.commit(
                        current.model_copy(
                            update={
                                "content": merged,
                                "updated_at": utcnow(),
                                "committed_by_run_id": packet.run_id,
                            }
                        )
                    )
                    self._mark_review(fresh, "rejected", editable)
                    return {
                        "rejected": True,
                        "review_kind": "event_plan",
                        "reopened_step": "scene_plan",
                        "event_id": event_id,
                        "version": committed.version,
                        "message": "正文前检查未通过，已携带检查意见退回连续场景方案",
                    }
        self._mark_review(packet, "rejected", dict(packet.content.get("editable") or {}))
        return {"rejected": True, "review_kind": packet.content["review_kind"]}

    def _save_auth_review(
        self,
        run_id: str,
        kind: str,
        title: str,
        artifacts: list[AuthObject],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        internal_artifacts = [
            {
                "artifact_key": self._auth_store.artifact_key(obj),
                "object": obj.model_dump(mode="json"),
            }
            for obj in artifacts
        ]
        editable_artifacts = [
            {
                "artifact_key": item["artifact_key"],
                "label": item["artifact_key"],
                "content": item["object"]["content"],
            }
            for item in internal_artifacts
        ]
        packet = self._save_review_packet(
            run_id=run_id,
            review_kind=kind,
            title=title,
            staging_type=StagingType.STG_AUTH_PATCH,
            editable={"artifacts": editable_artifacts},
            internal={"artifacts": internal_artifacts, **(extra or {})},
        )
        return self._review_payload(packet)

    def _save_review_packet(
        self,
        *,
        run_id: str,
        review_kind: str,
        title: str,
        staging_type: StagingType,
        editable: dict[str, Any],
        internal: dict[str, Any],
    ) -> StagingPacket:
        packet = StagingPacket(
            staging_id=new_staging_id(),
            run_id=run_id,
            staging_type=staging_type,
            content={
                "review_kind": review_kind,
                "title": title,
                "status": "pending",
                "editable": editable,
                "internal": internal,
            },
            created_at=utcnow(),
            verified=True,
        )
        self._staging_store.save(packet)
        return packet

    def _mark_review(self, packet: StagingPacket, status: str, editable: dict[str, Any]) -> None:
        content = dict(packet.content)
        content["status"] = status
        content["editable"] = editable
        self._staging_store.save(packet.model_copy(update={"content": content}))

    @staticmethod
    def _review_payload(packet: StagingPacket) -> dict[str, Any]:
        internal = dict(packet.content.get("internal") or {})
        revision_history = list(internal.get("revision_history") or [])
        audit_history = list(internal.get("audit_history") or [])
        latest_audit = dict(audit_history[-1]) if audit_history else {}
        current_audit = (
            dict(latest_audit.get("report") or {})
            if audit_history
            and int(latest_audit.get("basis_revision_count") or 0) == len(revision_history)
            and dict(latest_audit.get("audited_editable") or {})
            == dict(packet.content.get("editable") or {})
            else None
        )
        return {
            "staging_id": packet.staging_id,
            "run_id": packet.run_id,
            "review_kind": packet.content.get("review_kind", ""),
            "title": packet.content.get("title", "审核任务"),
            "status": packet.content.get("status", "pending"),
            "editable": packet.content.get("editable", {}),
            "asset_meta": internal.get("asset_meta"),
            "original_content": internal.get("original_content"),
            "foundation_step": internal.get("foundation_step"),
            "master_step": internal.get("master_step"),
            "volume_step": internal.get("volume_step"),
            "event_plan_step": internal.get("event_plan_step"),
            "event_id": internal.get("event_id"),
            "event_index": internal.get("event_index"),
            "volume_index": internal.get("volume_index"),
            "asset_id": internal.get("asset_id"),
            "max_tokens": internal.get("max_tokens"),
            "step_index": internal.get("step_index"),
            "step_total": internal.get("step_total"),
            "budget_report": internal.get("budget_report"),
            "quality_report": internal.get("quality_report"),
            "prewrite_check": (dict(internal.get("execution_report") or {}).get("prewrite_check")),
            "revision_history": revision_history,
            "revision_count": len(revision_history),
            "audit_history": audit_history,
            "audit_count": len(audit_history),
            "current_audit": current_audit,
            "suggested_feedback": str(dict(current_audit or {}).get("revision_feedback") or ""),
            "created_at": packet.created_at.isoformat(),
        }
