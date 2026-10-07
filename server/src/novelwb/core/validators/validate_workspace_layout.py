"""Validator: workspace 关键目录可读写/不缺失/权限检查。"""

from __future__ import annotations

import os
from pathlib import Path

from novelwb.core.constants import WorkspaceDirs
from novelwb.storage.workspace_layout import WorkspaceLayout

_REQUIRED_SUBDIRS = [
    WorkspaceDirs.AUTH,
    WorkspaceDirs.STAGING,
    WorkspaceDirs.EVENTS,
    WorkspaceDirs.PUBLISH,
    WorkspaceDirs.SNAPSHOTS,
    WorkspaceDirs.RUNS,
]


def validate_workspace_layout(workspace_root: Path, project_id: str) -> list[str]:
    """检查单个项目的 workspace 目录结构是否完整可用。"""
    errors: list[str] = []
    try:
        layout = WorkspaceLayout(workspace_root, project_id, create=False)
    except (ValueError, FileNotFoundError) as exc:
        return [str(exc)]
    project_dir = layout.project_dir
    for subdir_name in _REQUIRED_SUBDIRS:
        subdir = (project_dir / subdir_name).resolve()
        if not subdir.is_relative_to(project_dir):
            errors.append(f"子目录越出项目边界: {subdir_name}")
            continue
        if not subdir.is_dir():
            errors.append(f"必要子目录缺失: {subdir}")
            continue

        # 检查可写
        if not os.access(subdir, os.W_OK):
            errors.append(f"子目录不可写: {subdir}")

    return errors


def validate_repo_layout(repo_root: Path) -> list[str]:
    """检查 repo 级别必要文件是否存在。"""
    errors: list[str] = []
    required_files = [
        "SPEC_v1.md",
        "server/src/novelwb/core/step_catalog.yaml",
        "server/src/novelwb/core/error_codes.yaml",
        "server/src/novelwb/core/step_specs/stepspec_schema.json",
    ]
    for rel in required_files:
        p = repo_root / rel
        if not p.exists():
            errors.append(f"必要文件缺失: {rel}")
    return errors
