"""项目管理路由 /projects。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from novelwb.api.deps import WORKSPACE_ROOT, ok, require_project

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    project_id: str
    description: str = ""


@router.post("")
def create_project(body: CreateProjectBody) -> dict[str, Any]:
    """初始化项目目录。"""
    from novelwb.storage.workspace_layout import WorkspaceLayout

    pid = body.project_id.strip()
    try:
        layout = WorkspaceLayout(WORKSPACE_ROOT, pid)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return ok({"project_id": pid, "project_dir": str(layout.project_dir)}, "项目已创建")


@router.get("")
def list_projects() -> dict[str, Any]:
    """列出 workspace 下所有项目目录。"""
    if not WORKSPACE_ROOT.exists():
        return ok([])
    projects = [
        {"project_id": d.name, "path": str(d)}
        for d in sorted(WORKSPACE_ROOT.iterdir())
        if d.is_dir()
        and not d.name.startswith(".")
        and d.resolve().parent == WORKSPACE_ROOT.resolve()
    ]
    return ok(projects)


@router.get("/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    """获取项目基本信息。"""
    layout = require_project(project_id)
    if not layout.project_dir.exists():
        raise HTTPException(404, f"项目不存在: {project_id}")
    from novelwb.storage import PublishStore, RunsStore

    runs = RunsStore(layout).list_index()
    chapters = PublishStore(layout).chapter_count()
    return ok(
        {
            "project_id": project_id,
            "run_count": len(runs),
            "chapter_count": chapters,
        }
    )
