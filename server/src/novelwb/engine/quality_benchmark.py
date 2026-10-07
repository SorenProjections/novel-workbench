"""Offline corpus checks for prose signals and committed-story constraints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novelwb.core.constants import AuthObjectType
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ChapterSpec,
    DiffReport,
    EventRecord,
    ObservedDelta,
    StateSnapshot,
)
from novelwb.engine.prose_quality import ProseQualityEvaluator
from novelwb.engine.regression import RegressionContext, RegressionRunner
from novelwb.utils.timeutil import utcnow


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    text = str(case["text"])
    quality = ProseQualityEvaluator().evaluate(text, target_chars=int(case["target_chars"]))
    now = utcnow()
    snapshot = StateSnapshot(snapshot_key="post_sample", event_id="sample")
    record = EventRecord(
        event_id="sample",
        project_id="benchmark",
        draft_text=text,
        state_before_key="pre_sample",
        state_after_key=str(case.get("state_after_key", snapshot.snapshot_key)),
        observed_delta=ObservedDelta(state_after=snapshot, result_state_summary="固定样例状态"),
        diff_report=DiffReport(event_id="sample", run_id="benchmark", passed=True),
        committed_at=now,
        committed_by_run_id="benchmark",
        ledger_version_after=1,
    )
    bible = AuthObject(
        object_id="spec00",
        project_id="benchmark",
        object_type=AuthObjectType.BIBLE,
        content=case.get("spec00", {}),
        created_at=now,
        updated_at=now,
        committed_by_run_id="benchmark",
    )
    regression = RegressionRunner().run(
        RegressionContext(
            run_id="benchmark",
            project_id="benchmark",
            event_records=[record],
            bible_auth=bible,
            chapter_specs=[ChapterSpec.model_validate(item) for item in case.get("chapters", [])],
        )
    )
    issue_ids = sorted({issue.issue_id for issue in regression.issues})
    expected = case["expected"]
    failures = []
    if quality.passed != expected["quality_passed"]:
        desired = expected["quality_passed"]
        failures.append(f"正文质量通过状态：期望 {desired}，实际 {quality.passed}")
    if regression.passed != expected["regression_passed"]:
        failures.append("故事约束回归状态与基线不一致")
    missing = set(expected.get("issue_ids", [])) - set(issue_ids)
    if missing:
        failures.append(f"未检出固定缺陷：{sorted(missing)}")
    if quality.score < expected.get("minimum_score", 0):
        failures.append("正常样例评分低于基线下限")
    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "quality": quality.to_dict(),
        "regression_passed": regression.passed,
        "issue_ids": issue_ids,
    }


def evaluate_corpus(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("评测集不能为空，样例 ID 必须唯一")
    results = [evaluate_case(case) for case in cases]
    return {
        "corpus_version": corpus["version"],
        "sample_count": len(results),
        "passed": all(result["passed"] for result in results),
        "results": results,
    }
