#!/usr/bin/env python3
"""一键运行事件流水线脚本。

用法::

    python scripts/run_pipeline.py <project_id> <draft_text>
    python scripts/run_pipeline.py my_novel "今天故事里发生了大事..."

环境变量::

    NOVELWB_WORKSPACE   workspace 根目录（默认 server/workspace）
    NOVELWB_LLM_ADAPTER deepseek 或 mock（默认 mock）
    DEEPSEEK_API_KEY    使用 DeepSeek 时必填
"""

from __future__ import annotations

import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
from pathlib import Path

# 确保 src 在 PYTHONPATH
_SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SERVER_DIR / "src"))


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/run_pipeline.py <project_id> <draft_text>", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    draft_text = sys.argv[2]

    from novelwb.api.deps import get_orchestrator, WORKSPACE_ROOT
    from novelwb.core.schemas.domain_models import EventDraft
    from novelwb.utils.ids import new_event_id, new_run_id

    run_id = new_run_id()
    event_id = new_event_id()
    draft = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text=draft_text,
        blocks=[],
        word_count=len(draft_text),
    )

    print(f"项目: {project_id}")
    print(f"run_id: {run_id}")
    print(f"event_id: {event_id}")
    print(f"workspace: {WORKSPACE_ROOT}")
    print("正在执行事件流水线...\n")

    orch = get_orchestrator(project_id)
    result = orch.run_event_pipeline(run_id, event_id, draft)

    if not result["success"]:
        print("流水线执行失败，请查看日志", file=sys.stderr)
        sys.exit(1)

    e_out = result["event"]
    c_out = result["chapter"]
    output = {
        "run_id": run_id,
        "event_id": event_id,
        "fix_attempts": e_out.fix_attempts,
        "diff_passed": e_out.diff_report.passed,
        "chapters_generated": len(c_out.chapter_specs) if c_out else 0,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
