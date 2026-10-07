"""图P — 章节许可（Chapter License）。

步骤：
  P1. chapterLicense — 生成 CHAPTER_LICENSE（ChapterSpec）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from novelwb.core.constants import ChapterIntent
from novelwb.core.schemas.domain_models import ChapterSpec, VolumeContract
from novelwb.engine.hard_lint import LintContext
from novelwb.engine.step_runner import GraphDeps, StepResult, StepRunner
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.logger import get_logger

_logger = get_logger(__name__)


@dataclass
class GraphPInput:
    run_id: str
    event_id: str
    chapter_index: int
    input_pack: dict[str, Any] = field(default_factory=dict)  # 来自上游图的输入
    history_chapter_specs: list[ChapterSpec] = field(default_factory=list)
    volume_contract: VolumeContract | None = None


@dataclass
class GraphPOutput:
    chapter_spec: ChapterSpec
    lint_passed: bool
    violations: list[str] = field(default_factory=list)


class GraphP:
    """章节许可图执行器。"""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._runner = StepRunner(deps)

    def run(self, inp: GraphPInput) -> GraphPOutput:
        run_id = inp.run_id
        event_id = inp.event_id

        lint_ctx = LintContext(
            run_id=run_id,
            event_id=event_id,
            chapter_specs=[],
            history_chapter_specs=inp.history_chapter_specs,
            volume_contract=inp.volume_contract,
            enabled_rule_groups=["A", "F"],
        )

        result = self._runner.run(
            step_key="graphP.chapter.license",
            input_pack={
                "run_id": run_id,
                "event_id": event_id,
                "chapter_index": inp.chapter_index,
                **inp.input_pack,
            },
            lint_ctx=lint_ctx,
            run_id=run_id,
        )

        chapter_spec = self._parse_spec(result, event_id, inp.chapter_index)
        _logger.info(f"graphP_done event={event_id} lint={result.lint_passed}")

        return GraphPOutput(
            chapter_spec=chapter_spec,
            lint_passed=result.lint_passed,
            violations=result.violations,
        )

    @staticmethod
    def _parse_spec(result: StepResult, event_id: str, chapter_index: int) -> ChapterSpec:
        if result.parsed and isinstance(result.parsed, dict):
            try:
                return ChapterSpec.model_validate(
                    {
                        "chapter_id": result.parsed.get(
                            "chapter_id", f"chp_{event_id}_{chapter_index}"
                        ),
                        "chapter_index": chapter_index,
                        "chapter_intent": result.parsed.get(
                            "chapter_intent", ChapterIntent.ADVANCE
                        ),
                        **result.parsed,
                    }
                )
            except Exception:
                pass
        return ChapterSpec.model_construct(
            chapter_id=f"chp_{event_id}_{chapter_index}",
            chapter_index=chapter_index,
            chapter_intent=ChapterIntent.ADVANCE,
        )
