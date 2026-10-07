"""Portable mock-mode end-to-end check, isolated from creative workspace data."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "src"))
from fastapi.testclient import TestClient
from novelwb.api import deps
from novelwb.api.main import app
from novelwb.api.routers import pipeline, projects
from novelwb.engine.task_service import TaskService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=ROOT / ".checks/smoke")
    args = parser.parse_args()
    workspace = args.workspace.resolve() / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=False)
    os.environ["NOVELWB_LLM_ADAPTER"] = "mock"
    os.environ["NOVELWB_MOCK_FIXTURES"] = str(ROOT / "server/tests/fixtures/mock")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    deps.WORKSPACE_ROOT = projects.WORKSPACE_ROOT = workspace
    deps._build_orchestrator.cache_clear()
    service = TaskService(workers=1)
    pipeline.tasks = service
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.post("/projects", json={"project_id": "smoke"}).status_code == 200
            body = {"run_id": "run_smoke", "kind": "workflow", "params": {
                "stage": "foundation", "brief": "低复杂度群像小说，围绕渡口停航与补给争执展开。"}}
            url = "/projects/smoke/pipeline/runs"
            response = client.post(url, json=body)
            assert response.status_code == 200, response.text
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = client.get(f"{url}/run_smoke").json()["data"]
                if state["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                time.sleep(0.05)
            assert state["status"] == "completed", state
            assert client.post(url, json=body).json()["data"]["sequence"] == state["sequence"]
            review = state["result"]["review"]
            endpoint = f"/projects/smoke/pipeline/workflow/reviews/{review['staging_id']}/approve"
            payload = {"editable": review["editable"]}
            approved = client.post(endpoint, json=payload)
            assert approved.status_code == 200, approved.text
            repeated = client.post(endpoint, json=payload)
            assert repeated.json() == approved.json()
            replay = client.get(f"{url}/run_smoke/events", headers={"Last-Event-ID": "1"})
            assert replay.status_code == 200 and "event: result" in replay.text
            assert client.get("/projects/missing/pipeline/state").status_code == 404
        print(f"Smoke passed: persisted task -> replay -> review -> idempotent approval ({workspace})")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
