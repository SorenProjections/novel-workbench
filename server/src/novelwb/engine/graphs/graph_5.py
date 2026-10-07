"""图5 — 章后置流程（Chapter Post-processing）。

步骤：
  5.1 chapterizeCut    — 生成章节化方案（ChapterSpec 列表）
  5.2 chapterizeReview — 评审章节化方案
  5.3 fatigue          — 生成疲劳报告
  5.4 chapterCommit    — CHAPTER_COMMIT → 写发布层
"""

from __future__ import annotations

from dataclasses import dataclass, field

from novelwb.core.constants import ChapterIntent
from novelwb.core.schemas.domain_models import (
    ChapterSpec,
    EventDraft,
    FatigueReport,
    VolumeContract,
)
from novelwb.core.schemas.patch_models import CommitReceipt, VerifyResult
from novelwb.engine.hard_lint import LintContext
from novelwb.engine.step_runner import GraphDeps, StepRunner
from novelwb.storage import PublishStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_report_id
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import to_iso, utcnow
from novelwb.utils.transactions import atomic_method

_logger = get_logger(__name__)


@dataclass
class Graph5Input:
    run_id: str
    event_id: str
    draft: EventDraft
    history_chapter_specs: list[ChapterSpec] = field(default_factory=list)
    volume_contract: VolumeContract | None = None
    project_id: str = ""
    commit: bool = True


@dataclass
class Graph5Output:
    chapter_specs: list[ChapterSpec]
    chapter_texts: dict[str, str]
    review_result: VerifyResult
    fatigue_report: FatigueReport
    commit_receipt: CommitReceipt
    aborted: bool = False


class Graph5:
    """章后置图执行器。"""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._layout = layout
        self._runner = StepRunner(deps)
        self._publish_store = PublishStore(layout)

    def run(self, inp: Graph5Input) -> Graph5Output:
        run_id = inp.run_id
        event_id = inp.event_id
        draft = inp.draft

        # ── 5.1: ChapterizeCut ────────────────────────────────
        chapter_specs = self._run_cut(
            run_id, event_id, draft, inp.history_chapter_specs, inp.volume_contract
        )
        if chapter_specs and not self._valid_cut_anchors(draft.draft_text, chapter_specs):
            _logger.warning(f"graph5_invalid_cut_anchors event={event_id}; fallback=single_chapter")
            chapter_specs = []
        if not chapter_specs:
            _logger.warning(f"graph5_no_chapters event={event_id}")
            chapter_specs = [
                self._default_chapter_spec(event_id, draft, len(inp.history_chapter_specs) + 1)
            ]
        chapter_texts = self._split_chapter_texts(draft.draft_text, chapter_specs)

        # ── 5.2: ChapterizeReview ─────────────────────────────
        review = self._run_review(
            run_id,
            event_id,
            chapter_specs,
            chapter_texts,
            inp.history_chapter_specs,
            inp.volume_contract,
        )

        if not review.passed:
            _logger.warning(f"graph5_review_failed viol={review.violations}")
            # 软失败：仍继续（可在策略层配置是否阻断）

        # ── 5.3: Fatigue ──────────────────────────────────────
        fatigue = self._run_fatigue(
            run_id, event_id, chapter_specs, inp.history_chapter_specs, inp.project_id
        )

        # ── 5.4: ChapterCommit ────────────────────────────────
        receipt = (
            self._run_commit(run_id, event_id, chapter_specs, chapter_texts)
            if inp.commit
            else CommitReceipt.model_construct(
                receipt_id="",
                run_id=run_id,
                staging_id="",
                commit_type="chapter",
                committed_at="",
                committed_objects=[],
            )
        )

        return Graph5Output(
            chapter_specs=chapter_specs,
            chapter_texts=chapter_texts,
            review_result=review,
            fatigue_report=fatigue,
            commit_receipt=receipt,
        )

    def commit_reviewed(
        self,
        *,
        run_id: str,
        event_id: str,
        chapter_specs: list[ChapterSpec],
        chapter_texts: dict[str, str],
        review_result: VerifyResult,
        fatigue_report: FatigueReport,
    ) -> Graph5Output:
        """Publish a human-reviewed chapter split without cutting it again."""
        receipt = self._run_commit(run_id, event_id, chapter_specs, chapter_texts)
        return Graph5Output(
            chapter_specs=chapter_specs,
            chapter_texts=chapter_texts,
            review_result=review_result,
            fatigue_report=fatigue_report,
            commit_receipt=receipt,
        )

    # ── 内部步骤 ──────────────────────────────────────────────────────────

    def _run_cut(
        self,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        history: list[ChapterSpec],
        vc: VolumeContract | None,
    ) -> list[ChapterSpec]:
        lint_ctx = LintContext(
            run_id=run_id,
            event_id=event_id,
            draft=draft,
            chapter_specs=[],
            history_chapter_specs=history,
            volume_contract=vc,
            enabled_rule_groups=["A", "F"],
        )
        result = self._runner.run(
            step_key="graph5.chapterize.cut",
            input_pack={
                "run_id": run_id,
                "event_id": event_id,
                "draft_text": draft.draft_text,
                "scene_ids": [block.block_id for block in draft.blocks],
                "history_count": len(history),
            },
            lint_ctx=lint_ctx,
            run_id=run_id,
        )
        if result.parsed and isinstance(result.parsed, list):
            specs = []
            for i, item in enumerate(result.parsed):
                if isinstance(item, dict):
                    try:
                        specs.append(
                            ChapterSpec.model_validate(
                                {
                                    "chapter_id": item.get("chapter_id", f"chp_{event_id}_{i}"),
                                    "chapter_index": len(history) + i + 1,
                                    "chapter_intent": item.get(
                                        "chapter_intent", ChapterIntent.ADVANCE
                                    ),
                                    **item,
                                }
                            )
                        )
                    except Exception:
                        pass
            return specs
        return []

    def _run_review(
        self,
        run_id: str,
        event_id: str,
        specs: list[ChapterSpec],
        chapter_texts: dict[str, str],
        history: list[ChapterSpec],
        vc: VolumeContract | None,
    ) -> VerifyResult:
        lint_ctx = LintContext(
            run_id=run_id,
            event_id=event_id,
            chapter_specs=specs,
            history_chapter_specs=history,
            volume_contract=vc,
            enabled_rule_groups=["A", "E", "F"],
        )
        result = self._runner.run(
            step_key="graph5.chapterize.review",
            input_pack={
                "run_id": run_id,
                "event_id": event_id,
                "chapter_specs": [s.model_dump(mode="json") for s in specs],
                "chapter_texts": chapter_texts,
            },
            lint_ctx=lint_ctx,
            run_id=run_id,
        )
        now = utcnow()
        staging_id = f"stg_review_{event_id}"
        if result.parsed and isinstance(result.parsed, dict):
            try:
                return VerifyResult.model_validate(
                    {
                        "staging_id": staging_id,
                        "checked_at": now,
                        **result.parsed,
                    }
                )
            except Exception:
                pass
        return VerifyResult(
            staging_id=staging_id,
            passed=result.lint_passed,
            violations=result.violations,
            checked_at=now,
        )

    def _run_fatigue(
        self,
        run_id: str,
        event_id: str,
        specs: list[ChapterSpec],
        history: list[ChapterSpec],
        project_id: str,
    ) -> FatigueReport:
        result = self._runner.run(
            step_key="graph5.chapter.fatigue_report",
            input_pack={
                "run_id": run_id,
                "event_id": event_id,
                "chapter_specs": [s.model_dump(mode="json") for s in specs],
                "history_count": len(history),
            },
            run_id=run_id,
        )
        now = utcnow()
        if result.parsed and isinstance(result.parsed, dict):
            try:
                return FatigueReport.model_validate(
                    {
                        "report_id": new_report_id(),
                        "project_id": project_id,
                        "generated_at": now,
                        **result.parsed,
                    }
                )
            except Exception:
                pass
        return FatigueReport(
            report_id=new_report_id(),
            project_id=project_id,
            generated_at=now,
        )

    @atomic_method
    def _run_commit(
        self,
        run_id: str,
        event_id: str,
        specs: list[ChapterSpec],
        chapter_texts: dict[str, str],
    ) -> CommitReceipt:
        from novelwb.core.constants import ChapterIntent
        from novelwb.core.schemas.domain_models import ChapterCommitRecord

        self._runner.run(
            step_key="graph5.chapter.commit",
            input_pack={
                "run_id": run_id,
                "event_id": event_id,
                "chapter_count": len(specs),
            },
            run_id=run_id,
        )

        now = utcnow()
        # 将自然切分后的独立章节正文写入 publish 层。
        for spec in specs:
            chapter_text = chapter_texts.get(spec.chapter_id, "").strip()
            if not chapter_text:
                continue
            record = ChapterCommitRecord(
                chapter_id=spec.chapter_id,
                project_id="",
                chapter_index=spec.chapter_index,
                chapter_intent=spec.chapter_intent
                if spec.chapter_intent
                else ChapterIntent.ADVANCE,
                text=chapter_text,
                word_count=len(chapter_text),
                committed_at=now,
                committed_by_run_id=run_id,
                source_event_ids=[event_id],
            )
            self._publish_store.publish(record, chapter_text)

        return CommitReceipt.model_construct(
            receipt_id=f"rcpt_chap_{event_id}",
            run_id=run_id,
            staging_id=f"stg_chap_{event_id}",
            commit_type="chapter",
            committed_at=to_iso(now),
            committed_objects=[spec.chapter_id for spec in specs],
        )

    @staticmethod
    def _default_chapter_spec(
        event_id: str, draft: EventDraft, chapter_index: int = 1
    ) -> ChapterSpec:
        return ChapterSpec.model_construct(
            chapter_id=f"chp_{event_id}_0",
            chapter_index=chapter_index,
            chapter_intent=ChapterIntent.ADVANCE,
        )

    @staticmethod
    def _split_chapter_texts(text: str, specs: list[ChapterSpec]) -> dict[str, str]:
        """Split one continuous event draft at quoted natural-language end anchors."""
        if not specs:
            return {}
        if len(specs) == 1:
            return {specs[0].chapter_id: text.strip()}

        boundaries: list[int] = []
        cursor = 0
        for spec in specs[:-1]:
            anchor = (spec.end_anchor or "").strip()
            position = text.find(anchor, cursor) if anchor else -1
            if position >= 0:
                boundary = position + len(anchor)
            else:
                boundary = -1
            boundaries.append(boundary)
            if boundary > cursor:
                cursor = boundary

        if any(boundary <= 0 for boundary in boundaries) or boundaries != sorted(boundaries):
            weights = [max(1, spec.estimated_chars) for spec in specs]
            total_weight = sum(weights)
            running = 0
            boundaries = []
            for weight in weights[:-1]:
                running += weight
                approximate = int(len(text) * running / total_weight)
                paragraph_end = text.find("\n\n", approximate)
                boundaries.append(paragraph_end if paragraph_end >= 0 else approximate)

        result: dict[str, str] = {}
        starts = [0, *boundaries]
        ends = [*boundaries, len(text)]
        for spec, start, end in zip(specs, starts, ends):
            result[spec.chapter_id] = text[start:end].strip()
        return result

    @staticmethod
    def _valid_cut_anchors(text: str, specs: list[ChapterSpec]) -> bool:
        if len(specs) <= 1:
            return True
        cursor = 0
        for index, spec in enumerate(specs):
            start_anchor = (spec.start_anchor or "").strip()
            end_anchor = (spec.end_anchor or "").strip()
            if not start_anchor or not end_anchor:
                return False
            start_position = text.find(start_anchor, cursor)
            if start_position < 0 or text[cursor:start_position].strip():
                return False
            end_position = text.find(end_anchor, start_position + len(start_anchor))
            if end_position < 0:
                return False
            cursor = end_position + len(end_anchor)
            if index == len(specs) - 1 and text[cursor:].strip():
                return False
        return True
