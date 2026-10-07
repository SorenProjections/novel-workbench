"""CLI and HTTP entries must inspect the same existing project data."""
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from novelwb.api import deps
from novelwb.api.main import app as http_app
from novelwb.api.routers import pipeline
from novelwb.cli.main import app as cli_app
from tests.test_pipeline import _make_orchestrator
from tests.test_reliability import _chapter_review


def _approved_project(tmp_path, monkeypatch):
    orch = _make_orchestrator(tmp_path)
    packet = _chapter_review(orch)
    orch.approve_workflow_review(packet.staging_id, {})
    monkeypatch.setattr(deps, "WORKSPACE_ROOT", tmp_path / "workspace")
    monkeypatch.setattr(deps, "get_orchestrator", lambda project_id: orch)
    monkeypatch.setattr(pipeline, "get_orchestrator", lambda project_id: orch)
    return orch


def test_api_regression_checks_previously_committed_events(tmp_path, monkeypatch):
    _approved_project(tmp_path, monkeypatch)
    with TestClient(http_app) as client:
        response = client.post("/projects/test_proj/pipeline/regression")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["event_count"] == 1
    assert response.json()["data"]["chapter_count"] == 1


def test_cli_regression_checks_previously_committed_events(tmp_path, monkeypatch):
    _approved_project(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli_app, ["regression", "test_proj"])
    assert result.exit_code == 0, result.output
    assert '"event_count": 1' in result.output
    assert '"chapter_count": 1' in result.output


def test_cli_create_and_read_use_the_same_workspace_outside_server(tmp_path, monkeypatch):
    workspace = tmp_path / "creative_workspace"
    monkeypatch.setattr(deps, "WORKSPACE_ROOT", workspace)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(cli_app, ["new-project", "中文项目"]).exit_code == 0
    assert "中文项目" in runner.invoke(cli_app, ["ls"]).output
    assert runner.invoke(cli_app, ["chapters", "中文项目"]).exit_code == 0
    assert workspace.joinpath("中文项目").is_dir()
    assert not tmp_path.joinpath("workspace").exists()


def test_cli_missing_project_queries_and_invalid_create_leave_no_data(tmp_path, monkeypatch):
    workspace = tmp_path / "creative_workspace"
    monkeypatch.setattr(deps, "WORKSPACE_ROOT", workspace)
    runner = CliRunner()
    for arguments in (["chapters", "missing"], ["run-auth", "missing", "stg_test"], ["new-project", "NUL"]):
        result = runner.invoke(cli_app, arguments)
        assert result.exit_code == 1 and "错误" in result.output
    assert not workspace.exists()
