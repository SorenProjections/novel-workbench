"""Judge — best-of-n 候选选优引擎。

流程：
1. 对每个 Candidate 运行 HardLint（可选）
2. 按 (hard_violations_count, soft_violations_count) 升序排名
3. 选出 rank=1 的 Candidate，更新 selected=True
4. 返回排序后的列表 + 选出的 Candidate
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from novelwb.core.schemas.domain_models import Candidate, EventDraft
from novelwb.engine.hard_lint import HardLintEngine, LintContext


@dataclass
class JudgeResult:
    """Judge 运行结果。"""

    candidates: list[Candidate]  # 全部候选（按分数排序）
    selected: Candidate  # 最优候选
    lint_reports: dict[str, dict[str, Any]]  # candidate_id -> DiffReport.model_dump()
    passed_count: int  # 通过 HardLint 的候选数
    total_count: int


class Judge:
    """best-of-n 选优引擎。

    Args:
        lint_engine: HardLintEngine 实例。若为 None，跳过 HardLint 仅按 rank 排序。
        prefer_rank: 若所有候选都通过，优先选第几名（1-indexed，默认1）。
    """

    def __init__(
        self,
        lint_engine: HardLintEngine | None = None,
        prefer_rank: int = 1,
    ) -> None:
        self._lint = lint_engine or HardLintEngine()
        self._prefer_rank = prefer_rank

    def evaluate(
        self,
        candidates: list[Candidate],
        lint_ctx_template: LintContext | None = None,
    ) -> JudgeResult:
        """对候选列表进行 HardLint + 排序 + 选优。

        Args:
            candidates:         best-of-n 生成的 Candidate 列表。
            lint_ctx_template:  LintContext 模板，judge 会用每个候选的 content
                                 填充 draft 字段后运行 HardLint。
                                 若为 None，仅按原始 rank 排序。

        Returns:
            JudgeResult
        """
        if not candidates:
            raise ValueError("candidates 不能为空")

        scored: list[tuple[int, int, int, Candidate]] = []  # (hard, soft, rank, candidate)
        lint_reports: dict[str, dict[str, Any]] = {}

        for cand in candidates:
            if lint_ctx_template is not None:
                draft = self._extract_draft(cand, lint_ctx_template)
                ctx = LintContext(
                    run_id=lint_ctx_template.run_id,
                    event_id=lint_ctx_template.event_id,
                    draft=draft,
                    chapter_specs=lint_ctx_template.chapter_specs,
                    bible_auth=lint_ctx_template.bible_auth,
                    volume_contract=lint_ctx_template.volume_contract,
                    pre_snapshot=lint_ctx_template.pre_snapshot,
                    observed_delta=lint_ctx_template.observed_delta,
                    history_chapter_specs=lint_ctx_template.history_chapter_specs,
                    enabled_rule_groups=lint_ctx_template.enabled_rule_groups,
                    context_package=lint_ctx_template.context_package,
                )
                report = self._lint.run(ctx)
                lint_reports[cand.candidate_id] = report.model_dump(mode="json")
                hard_cnt = len(report.violated_forbidden)
                soft_cnt = len(report.soft_defects)
            else:
                hard_cnt = 0
                soft_cnt = 0

            scored.append((hard_cnt, soft_cnt, cand.rank, cand))

        # 升序排序：hard 最少 > soft 最少 > 原始 rank 最小
        scored.sort(key=lambda x: (x[0], x[1], x[2]))

        sorted_candidates = []
        for new_rank, (hard_cnt, soft_cnt, _orig_rank, cand) in enumerate(scored, start=1):
            cand.rank = new_rank
            cand.selected = new_rank == 1
            sorted_candidates.append(cand)

        selected = sorted_candidates[0]
        passed_count = sum(1 for h, _, _, _ in scored if h == 0)

        return JudgeResult(
            candidates=sorted_candidates,
            selected=selected,
            lint_reports=lint_reports,
            passed_count=passed_count,
            total_count=len(candidates),
        )

    @staticmethod
    def _extract_draft(cand: Candidate, ctx_template: LintContext) -> EventDraft | None:
        """尝试从 Candidate.content 中反序列化 EventDraft。

        content 可能是：
        - 已解析的 dict（直接用）
        - JSON 字符串（需解析）
        - 其他类型（返回 None，跳过 HardLint A 以外的规则）
        """
        content = cand.content
        # Candidate.content 现在是 dict（StepRunner 统一转换）
        # 若有 _raw 键，先尝试解析原始文本
        if isinstance(content, dict) and "_raw" in content:
            raw = content["_raw"]
            try:
                content = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(content, dict):
            try:
                return EventDraft.model_validate(content)
            except Exception:
                return None
        return None
