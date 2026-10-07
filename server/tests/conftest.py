"""pytest 共享 fixtures。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novelwb.adapters.llm.mock_replay import MockReplayAdapter
from novelwb.storage.workspace_layout import WorkspaceLayout


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    """临时 workspace 根目录。"""
    return tmp_path / "workspace"


@pytest.fixture()
def tmp_layout(tmp_workspace: Path) -> WorkspaceLayout:
    """临时项目布局。"""
    return WorkspaceLayout(tmp_workspace, "test_proj")


@pytest.fixture()
def mock_adapter() -> MockReplayAdapter:
    """默认 mock LLM 适配器（返回空字符串）。"""
    return MockReplayAdapter(default_response='{"_raw": "mock output"}')


@pytest.fixture()
def run_id() -> str:
    from novelwb.utils.ids import new_run_id
    return new_run_id()


@pytest.fixture()
def event_id() -> str:
    from novelwb.utils.ids import new_event_id
    return new_event_id()
