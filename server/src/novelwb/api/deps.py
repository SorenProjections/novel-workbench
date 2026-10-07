"""FastAPI 依赖注入 — 从环境变量/配置初始化共享对象。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException

from novelwb.adapters.llm.base import LLMAdapter
from novelwb.adapters.llm.deepseek import DeepSeekAdapter
from novelwb.adapters.llm.mock_replay import MockReplayAdapter
from novelwb.engine.orchestrator import Orchestrator, OrchestratorConfig
from novelwb.storage.workspace_layout import WorkspaceLayout

# ── 加载 .env ─────────────────────────────────────────────────────────────

_THIS_DIR = Path(__file__).parent
_PACKAGE_DIR = _THIS_DIR.parent
_SERVER_DIR = _PACKAGE_DIR.parent.parent if _PACKAGE_DIR.parent.name == "src" else Path.cwd()
_PROJECT_ROOT = _SERVER_DIR.parent  # novel-workbench/

# 优先加载项目根目录的 .env，再尝试 server/ 目录
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_SERVER_DIR / ".env", override=False)

# ── 路径常量 ──────────────────────────────────────────────────────────────

_SRC_DIR = _PACKAGE_DIR
PROMPTS_DIR = _SRC_DIR / "prompts"
CORE_DIR = _SRC_DIR / "core"
WORKSPACE_ROOT = Path(
    os.environ.get(
        "NOVELWB_WORKSPACE", os.environ.get("WORKSPACE_ROOT", str(_SERVER_DIR / "workspace"))
    )
)


# ── 单例工厂 ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=32)
def _build_orchestrator(project_id: str) -> Orchestrator:
    # 兼容 .env 中的 LLM_ADAPTER 和环境变量中的 NOVELWB_LLM_ADAPTER
    adapter_type = os.environ.get("NOVELWB_LLM_ADAPTER", os.environ.get("LLM_ADAPTER", "mock"))
    llm: LLMAdapter
    if adapter_type == "deepseek":
        llm = DeepSeekAdapter()
    else:
        fixture_directory = os.environ.get("NOVELWB_MOCK_FIXTURES")
        llm = MockReplayAdapter(fixtures_dir=Path(fixture_directory) if fixture_directory else None)
    cfg = OrchestratorConfig(
        workspace_root=WORKSPACE_ROOT,
        project_id=project_id,
        prompts_dir=PROMPTS_DIR,
        core_dir=CORE_DIR,
        llm_adapter=llm,
    )
    return Orchestrator(cfg)


def get_orchestrator(project_id: str) -> Orchestrator:
    require_project(project_id)
    return _build_orchestrator(project_id)


# ── 公共响应工具 ──────────────────────────────────────────────────────────


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"status": "ok", "message": message, "data": data}


def err(message: str, code: int = 400) -> dict[str, Any]:
    return {"status": "error", "message": message, "data": None}


def require_project(project_id: str) -> WorkspaceLayout:
    try:
        return WorkspaceLayout(WORKSPACE_ROOT, project_id, create=False)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
