"""小说工业化 CLI — novelwb。

用法示例::

    novelwb new-project my_novel
    novelwb run-event my_novel "今天发生了一件大事..."
    novelwb run-auth my_novel <staging_id>
    novelwb regression my_novel
    novelwb ls
    novelwb chapters my_novel
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from fastapi import HTTPException

from novelwb.storage.workspace_layout import WorkspaceLayout

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(name="novelwb", help="小说工业化流水线 CLI", add_completion=False)

# ── 工具函数 ──────────────────────────────────────────────────────────────


def _workspace() -> Path:
    from novelwb.api.deps import WORKSPACE_ROOT

    return WORKSPACE_ROOT


def _get_orchestrator(project_id: str) -> Any:
    from novelwb.api.deps import get_orchestrator

    try:
        return get_orchestrator(project_id)
    except HTTPException as exc:
        typer.echo(f"错误: {exc.detail}", err=True)
        raise typer.Exit(1) from exc


def _existing_layout(project_id: str) -> WorkspaceLayout:
    from novelwb.api.deps import require_project

    try:
        return require_project(project_id)
    except HTTPException as exc:
        typer.echo(f"错误: {exc.detail}", err=True)
        raise typer.Exit(1) from exc


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


# ── 命令 ──────────────────────────────────────────────────────────────────


@app.command("new-project")
def new_project(
    project_id: str = typer.Argument(..., help="项目 ID（字母数字下划线）"),
    description: str = typer.Option("", "--desc", "-d", help="项目描述"),
) -> None:
    """初始化新项目目录。"""
    ws = _workspace()
    pid = project_id.strip()
    try:
        layout = WorkspaceLayout(ws, pid)
    except ValueError as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"项目已创建: {layout.project_dir}")


@app.command("ls")
def list_projects() -> None:
    """列出 workspace 下所有项目。"""
    ws = _workspace()
    if not ws.exists():
        typer.echo("(workspace 为空)")
        return
    projects = [d.name for d in sorted(ws.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    if not projects:
        typer.echo("(没有项目)")
    for p in projects:
        typer.echo(p)


@app.command("run-event")
def run_event(
    project_id: str = typer.Argument(..., help="项目 ID"),
    draft_text: str = typer.Argument(..., help="事件草稿文本"),
    event_id: str = typer.Option("", "--event-id", help="指定 event_id（留空自动生成）"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id（留空自动生成）"),
) -> None:
    """执行事件提交流水线（图E + 图5）。"""
    from novelwb.core.schemas.domain_models import EventDraft
    from novelwb.utils.ids import new_event_id, new_run_id

    orch = _get_orchestrator(project_id)
    rid = run_id or new_run_id()
    eid = event_id or new_event_id()

    draft = EventDraft.model_construct(
        event_id=eid,
        run_id=rid,
        draft_text=draft_text,
        blocks=[],
        word_count=len(draft_text),
    )
    typer.echo(f"运行 event 流水线: run_id={rid} event_id={eid}")
    result = orch.run_event_pipeline(rid, eid, draft)
    if not result["success"]:
        typer.echo("流水线执行失败，请查看日志", err=True)
        raise typer.Exit(1)

    e_out = result["event"]
    c_out = result["chapter"]
    _print_json(
        {
            "run_id": rid,
            "event_id": eid,
            "fix_attempts": e_out.fix_attempts,
            "chapters": len(c_out.chapter_specs) if c_out else 0,
            "diff_passed": e_out.diff_report.passed,
        }
    )


@app.command("run-auth")
def run_auth(
    project_id: str = typer.Argument(..., help="项目 ID"),
    staging_id: str = typer.Argument(..., help="暂存包 ID"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id"),
) -> None:
    """执行权威提交流水线（图S）。"""
    from novelwb.storage import StagingStore
    from novelwb.utils.ids import new_run_id

    layout = _existing_layout(project_id)
    staging_store = StagingStore(layout)
    packet = staging_store.load_optional(staging_id)
    if packet is None:
        typer.echo(f"暂存包不存在: {staging_id}", err=True)
        raise typer.Exit(1)

    orch = _get_orchestrator(project_id)
    rid = run_id or new_run_id()
    typer.echo(f"运行 auth 流水线: run_id={rid} staging_id={staging_id}")
    out = orch.run_auth_pipeline(rid, packet)
    if out.aborted:
        typer.echo("权威提交验证失败", err=True)
        raise typer.Exit(1)
    _print_json(
        {
            "run_id": rid,
            "staging_id": staging_id,
            "committed": True,
            "receipt_id": out.commit_receipt.receipt_id,
        }
    )


@app.command("init-novel")
def init_novel(
    project_id: str = typer.Argument(..., help="项目 ID"),
    brief: str = typer.Argument(..., help="小说简介（用引号括起来）"),
    volume_index: int = typer.Option(1, "--volume", "-v", help="第几卷（默认第1卷）"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id（留空自动生成）"),
) -> None:
    """运行舞台引擎（图1+图2+图3），建立项目权威层基础设施。

    示例:
        novelwb init-novel my_novel
        "都市异能，主角觉醒异能后在弱肉强食的都市中崛起，主线是复仇+寻找失散家人"
    """
    from novelwb.utils.ids import new_run_id as _new_run_id

    orch = _get_orchestrator(project_id)
    rid = run_id or _new_run_id()
    typer.echo(f"运行舞台引擎: run_id={rid} project={project_id} volume={volume_index}")
    typer.echo("步骤: 图1（舞台引擎）→ 图2（长线骨架）→ 图3（分卷规划）")
    result = orch.run_stage_engine(rid, brief, volume_index=volume_index)

    if not result.get("success"):
        typer.echo(f"舞台引擎执行失败: {result.get('abort_reason', '未知原因')}", err=True)
        raise typer.Exit(1)

    spec00 = result.get("spec00")
    longline = result.get("longline")
    volume_contract = result.get("volume_contract")
    _print_json(
        {
            "run_id": rid,
            "success": True,
            "spec00_id": spec00.object_id if spec00 else None,
            "longline_id": longline.object_id if longline else None,
            "volume_contract_id": volume_contract.object_id if volume_contract else None,
            "main_promise": (spec00.content.get("main_promise") if spec00 else None),
            "volume_index": volume_index,
        }
    )
    typer.echo("舞台引擎完成！权威层基础设施已建立。可以使用 write-event 开始写作。")


@app.command("write-event")
def write_event(
    project_id: str = typer.Argument(..., help="项目 ID"),
    event_goal: str = typer.Argument(..., help="事件目标描述（一句话）"),
    result_target: str = typer.Option("", "--result", "-r", help="期望的事件结果"),
    slot_id: str = typer.Option("", "--slot-id", help="事件槽位ID（留空自动生成）"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id（留空自动生成）"),
    is_key_event: bool = typer.Option(False, "--key", help="是否为关键事件（获得更高预算）"),
) -> None:
    """运行事件写作流水线（图4生成草稿 → 图E提交 → 图5章节化）。

    示例:
        novelwb write-event my_novel "主角在宗门大比中遭遇昔日仇人，以弱胜强完成复仇" --key
    """
    from novelwb.utils.ids import new_event_id as _new_event_id
    from novelwb.utils.ids import new_run_id as _new_run_id

    orch = _get_orchestrator(project_id)
    rid = run_id or _new_run_id()
    sid = slot_id or f"slot_{_new_event_id()}"

    event_slot = {
        "slot_id": sid,
        "event_goal": event_goal,
        "result_target": result_target or f"完成：{event_goal}",
        "is_key_event": is_key_event,
        "conflict_form": None,
        "key_deliverables": [],
        "forbidden_delta": [],
        "allowed_delta": [],
    }

    typer.echo(f"运行事件写作: run_id={rid} slot_id={sid}")
    typer.echo(f"目标: {event_goal}")
    typer.echo("步骤: 图4（事件执行）→ 图E（提交校验）→ 图5（章节化）")

    result = orch.run_event_write(rid, event_slot)

    if not result.get("success"):
        typer.echo(f"事件写作失败: {result.get('abort_reason', '请查看日志')}", err=True)
        raise typer.Exit(1)

    draft = result.get("draft")
    e_out = result.get("event")
    c_out = result.get("chapter")
    _print_json(
        {
            "run_id": rid,
            "event_id": draft.event_id if draft else None,
            "word_count": draft.word_count if draft else 0,
            "namecheck_passed": result.get("namecheck_passed", True),
            "diff_passed": e_out.diff_report.passed if e_out else None,
            "fix_attempts": e_out.fix_attempts if e_out else 0,
            "chapters_generated": len(c_out.chapter_specs) if c_out else 0,
        }
    )
    if draft:
        chapter_count = len(c_out.chapter_specs) if c_out else 0
        completion_message = f"\n事件写作完成！字数：{draft.word_count}，章节：{chapter_count}"
        typer.echo(completion_message)


@app.command("sprout-event")
def sprout_event(
    project_id: str = typer.Argument(..., help="项目 ID"),
    root_event_goal: str = typer.Argument(..., help="需要展开为连续完整事件的根事件目标"),
    event_count: int = typer.Option(
        6,
        "--events",
        "-e",
        "--chapters",
        "-c",
        min=1,
        max=12,
        help="最大蔓生事件数；--chapters 为兼容别名",
    ),
    result_target: str = typer.Option("", "--result", "-r", help="根事件最终结果目标"),
    start_index: int = typer.Option(1, "--start", help="起始事件序号"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id（留空自动生成）"),
    is_key_event: bool = typer.Option(False, "--key", help="是否按关键事件体量展开"),
) -> None:
    """把一个根事件蔓生为连续完整事件；每个事件完成后再自然切章。"""
    from novelwb.utils.ids import new_run_id as _new_run_id

    orch = _get_orchestrator(project_id)
    rid = run_id or _new_run_id()
    typer.echo(f"运行事件蔓生: run_id={rid} events={event_count}")
    result = orch.run_event_sprout(
        run_id=rid,
        root_event_goal=root_event_goal,
        event_count=event_count,
        result_target=result_target,
        start_index=start_index,
        is_key_event=is_key_event,
    )
    if not result.get("success"):
        typer.echo(f"事件蔓生失败: {result.get('abort_reason', 'unknown')}", err=True)
        raise typer.Exit(1)
    _print_json(result)


@app.command("auto-volume")
def auto_volume(
    project_id: str = typer.Argument(..., help="项目 ID"),
    start_index: int = typer.Option(1, "--start", help="从第几个规划事件开始（1-indexed）"),
    max_events: int = typer.Option(0, "--max", help="最多写多少个事件（0=写到本卷末尾）"),
    only_key: bool = typer.Option(False, "--key-only", help="仅写关键事件"),
    run_id: str = typer.Option("", "--run-id", help="指定 run_id（留空自动生成）"),
) -> None:
    """按图3已规划的事件槽位表，自动连载整卷。

    前置：必须先 init-novel（图3会生成 event_slots 事件槽位表）。
    示例:
        novelwb auto-volume qingcheng            # 自动写完本卷规划的全部事件
        novelwb auto-volume qingcheng --start 3 --max 5
    """
    from novelwb.utils.ids import new_run_id as _new_run_id

    orch = _get_orchestrator(project_id)
    rid = run_id or _new_run_id()
    typer.echo(f"运行自动连载: run_id={rid} project={project_id}")
    typer.echo("步骤: 读取图3事件槽位表 → 逐槽 图4→图E→图5")

    result = orch.run_volume_auto(
        rid,
        start_index=start_index,
        max_events=max_events,
        only_key=only_key,
        progress=lambda p: typer.echo(
            f"  [{p.get('event')}] "
            + (f"第{p['chapter_index']}章 " if p.get("chapter_index") else "")
            + (p.get("event_goal", "") or p.get("reason", ""))[:60]
        ),
    )
    if not result.get("success"):
        typer.echo(f"自动连载失败: {result.get('abort_reason', '请查看日志')}", err=True)
        raise typer.Exit(1)
    _print_json(result)
    typer.echo(f"\n自动连载完成！共写 {result.get('completed_slots', 0)} 个事件。")


@app.command("regression")
def regression(
    project_id: str = typer.Argument(..., help="项目 ID"),
    test_types: str | None = typer.Option(
        None, "--types", "-t", help="逗号分隔的测试类型，如 prose,mechanic"
    ),
) -> None:
    """运行回归测试。"""
    orch = _get_orchestrator(project_id)
    types = [t.strip() for t in test_types.split(",")] if test_types else None
    typer.echo(f"运行项目回归测试: project_id={project_id}")
    result = orch.run_regression(test_types=types)
    report = result["report"]
    _print_json(
        {
            "passed": report.passed,
            "event_count": report.event_count,
            "chapter_count": report.chapter_count,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "issues": [
                {"type": i.test_type, "id": i.issue_id, "severity": i.severity, "msg": i.message}
                for i in report.issues
            ],
        }
    )


@app.command("chapters")
def list_chapters(
    project_id: str = typer.Argument(..., help="项目 ID"),
) -> None:
    """列出项目所有已发布章节。"""
    from novelwb.storage import PublishStore

    layout = _existing_layout(project_id)
    store = PublishStore(layout)
    records = store.list_index()
    if not records:
        typer.echo("(没有已发布章节)")
        return
    for r in records:
        typer.echo(f"  {r.get('chapter_id', '?')}  {r.get('created_at', '')}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
