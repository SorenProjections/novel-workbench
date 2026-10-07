"""Task replay, cancellation and API project isolation without external calls."""
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novelwb.engine.task_service import TaskService
from novelwb.engine.step_runner import GraphDeps
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json


def _finish(service, layout, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = service.get(layout, run_id)
        if state["status"] in {"completed", "cancelled", "failed", "interrupted"}:
            return state
        time.sleep(.01)
    raise AssertionError("task did not terminate")


def test_task_replay_is_idempotent_and_tracks_usage(tmp_path):
    layout = WorkspaceLayout(tmp_path, "project")
    service = TaskService(workers=1)
    calls = []
    def work(progress):
        calls.append(1)
        progress({"event":"step","phase":"done","input_tokens":12,"output_tokens":3,"latency_ms":10})
        return {"review":{"title":"test"}}
    try:
        service.start(layout, "run_a", "workflow", {}, work)
        state = _finish(service, layout, "run_a")
        assert state["status"] == "completed", state
        service.start(layout, "run_a", "workflow", {}, work)
        assert calls == [1]
        assert state["input_tokens"] == 12 and state["output_tokens"] == 3
        first = list(service.events(layout, "run_a"))
        second = list(service.events(layout, "run_a", after=1))
        assert len(first) == 3 and len(second) == 2
        assert 'event: result' in second[-1]
        with pytest.raises(ValueError, match="另一组参数"):
            service.start(layout, "run_a", "workflow", {"stage":"prose"}, work)
    finally:
        service.close()


def test_task_cancel_is_project_scoped_and_prevents_next_step(tmp_path):
    layout = WorkspaceLayout(tmp_path, "one")
    other = WorkspaceLayout(tmp_path, "two")
    service = TaskService(workers=1)
    ready, release = threading.Event(), threading.Event()
    committed = []
    def work(progress):
        ready.set(); release.wait(5)
        progress({"event":"step"})
        committed.append(1)
        return {}
    try:
        service.start(layout, "run_a", "workflow", {}, work)
        assert ready.wait(5)
        with pytest.raises(FileNotFoundError):
            service.cancel(other, "run_a")
        service.cancel(layout, "run_a")
        release.set()
        assert _finish(service, layout, "run_a")["status"] == "cancelled"
        assert committed == []
    finally:
        release.set(); service.close()


def test_abandoned_task_becomes_interrupted(tmp_path):
    layout = WorkspaceLayout(tmp_path, "project")
    service = TaskService()
    path = layout.runs_dir / "tasks" / "run_a.json"
    import os
    atomic_write_json(path,{"status":"running","owner_pid":os.getpid(),"session":"previous-process","sequence":0})
    try:
        assert service.get(layout, "run_a")["status"] == "interrupted"
    finally:
        service.close()


def test_api_unknown_project_and_invalid_id_never_create_directories(tmp_path, monkeypatch):
    from novelwb.api import deps
    from novelwb.api.main import app
    from novelwb.api.routers import projects
    monkeypatch.setattr(deps, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(projects, "WORKSPACE_ROOT", tmp_path)
    with TestClient(app) as client:
        for endpoint in ["/projects/missing", "/projects/missing/pipeline/state", "/projects/missing/chapters"]:
            assert client.get(endpoint).status_code == 404
        for project_id in ["..", "C:outside", "NUL"]:
            assert client.post('/projects',json={"project_id":project_id}).status_code == 400
        assert list(tmp_path.iterdir()) == []
        assert client.post('/projects',json={"project_id":"中文项目"}).status_code == 200
        assert client.get('/projects/中文项目').status_code == 200


def test_missing_run_lookup_and_cancel_never_create_task_directories(tmp_path):
    layout = WorkspaceLayout(tmp_path, "empty")
    service = TaskService()
    try:
        with pytest.raises(FileNotFoundError):
            service.get(layout, "missing")
        with pytest.raises(FileNotFoundError):
            service.cancel(layout, "missing")
        with pytest.raises(ValueError):
            service.get(layout, "C:outside")
        assert not (layout.runs_dir / "tasks").exists()
    finally:
        service.close()


def test_event_replay_reads_incrementally_and_tolerates_an_incomplete_tail(tmp_path):
    import json
    path = tmp_path / "progress.jsonl"
    entries = [{"sequence": index, "event": "step"} for index in range(1, 1026)]
    path.write_bytes(b"".join((json.dumps(row) + "\n").encode() for row in entries) + b'{"sequence":')
    offset, actual = 0, []
    while True:
        rows, next_offset = TaskService._read_events(path, offset)
        actual.extend(rows)
        if next_offset == offset:
            break
        offset = next_offset
    assert actual == entries
    assert path.read_bytes()[offset:] == b'{"sequence":'


def test_queue_capacity_and_shutdown_cancel_only_queued_jobs(tmp_path):
    service = TaskService(workers=1, max_pending=2)
    one, two, three = [WorkspaceLayout(tmp_path, name) for name in ("one", "two", "three")]
    ready, release = threading.Event(), threading.Event()
    calls = []
    def running(progress):
        ready.set()
        assert release.wait(5)
        calls.append("one")
        return {}
    def queued(progress):
        calls.append("two")
        return {}
    try:
        service.start(one, "run", "workflow", {}, running)
        assert ready.wait(5)
        service.start(two, "run", "workflow", {}, queued)
        with pytest.raises(ValueError, match="队列已满"):
            service.start(three, "run", "workflow", {}, queued)
        service.close()
        assert service.get(two, "run")["status"] == "cancelled"
        release.set()
        assert _finish(service, one, "run")["status"] == "completed"
        assert calls == ["one"]
    finally:
        release.set()
        service.close()


def test_app_lifespan_closes_tasks_and_can_restart(monkeypatch):
    from novelwb.api.main import app
    from novelwb.api.routers import pipeline
    service = TaskService(workers=1)
    monkeypatch.setattr(pipeline, "tasks", service)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert not service.closed
    assert service.closed
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert pipeline.tasks is not service and not pipeline.tasks.closed
    assert pipeline.tasks.closed
