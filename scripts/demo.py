"""Start a loopback-only demo with fixture responses and a fresh isolated workspace."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BRIEF = "低复杂度群像悬疑：药船被困渡口，人物必须付出代价查明停航原因。"


def prepare_demo(output_root: Path) -> dict:
    directory = output_root.resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / "workspace"
    os.environ["NOVELWB_LLM_ADAPTER"] = "mock"
    os.environ["NOVELWB_MODEL_SETTINGS_DISABLED"] = "1"
    os.environ["NOVELWB_MOCK_FIXTURES"] = str(ROOT / "server/tests/fixtures/mock")
    os.environ["NOVELWB_WORKSPACE"] = str(workspace)
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    sys.path.insert(0, str(ROOT / "server/src"))

    from fastapi.testclient import TestClient
    from novelwb.api import deps
    from novelwb.api.main import app
    from novelwb.api.routers import projects

    logging.getLogger("httpx").setLevel(logging.WARNING)
    deps.WORKSPACE_ROOT = projects.WORKSPACE_ROOT = workspace
    deps._build_orchestrator.cache_clear()
    project_id, run_id = "demo-ferry", "run_demo"
    with TestClient(app) as client:
        response = client.post("/projects", json={"project_id": project_id})
        response.raise_for_status()
        url = f"/projects/{project_id}/pipeline/runs"
        response = client.post(
            url,
            json={
                "run_id": run_id,
                "kind": "workflow",
                "params": {"stage": "foundation", "brief": BRIEF},
            },
        )
        response.raise_for_status()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = client.get(f"{url}/{run_id}")
            response.raise_for_status()
            state = response.json()["data"]
            if state["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.05)
        if state["status"] != "completed":
            raise RuntimeError("Demo fixture generation failed; inspect the isolated task log")
        review = state["result"]["review"]
        report = {
            "mode": "mock",
            "workspace": str(workspace),
            "project_id": project_id,
            "run_id": run_id,
            "staging_id": review["staging_id"],
            "brief": BRIEF,
            "supported_step": "foundation/spec00",
            "status": "pending_review",
            "note": "Fixture responses demonstrate approval and persistence, not literary quality. "
            "Later generation steps are not included in this demo.",
        }
    (directory / "demo.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path, default=ROOT / ".checks/demo")
    parser.add_argument(
        "--prepare-only", action="store_true", help="prepare the review without a web server"
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not args.prepare_only and not (ROOT / "server/src/novelwb/web/index.html").is_file():
        parser.error("Build the UI first: cd webui, npm ci, npm run build")
    report = prepare_demo(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not args.prepare_only:
        import uvicorn
        from novelwb.api.main import app

        print(f"Demo: http://127.0.0.1:{args.port}/ — Ctrl+C to stop", flush=True)
        print(
            "Open 审核中心, edit and approve 作品规格, then inspect 分层资产. "
            "Only this first foundation file has an offline fixture.",
            flush=True,
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
