"""Verify a demo cannot select the live adapter or overwrite an existing workspace."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
PROBE = """
import importlib.util
import json
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("demo", Path(sys.argv[1]) / "demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
report = demo.prepare_demo(Path(sys.argv[2]))
from fastapi.testclient import TestClient
from novelwb.api import deps
from novelwb.api.main import app
assert deps._build_orchestrator(report["project_id"])._deps.llm.adapter_type == "mock_replay"
with TestClient(app) as client:
    base = "/projects/" + report["project_id"] + "/pipeline"
    before = client.get(base + "/workflow").json()["data"]
    assert before["foundation_progress"]["approved_count"] == 0
    review = before["pending_reviews"][0]
    endpoint = base + "/workflow/reviews/" + review["staging_id"] + "/approve"
    first = client.post(endpoint, json={"editable": review["editable"]})
    assert first.status_code == 200
    assert client.post(endpoint, json={"editable": review["editable"]}).json() == first.json()
    after = client.get(base + "/workflow").json()["data"]
    assert after["foundation_progress"]["approved_count"] == 1
    assert "event: result" in client.get(base + "/runs/run_demo/events").text
second = demo.prepare_demo(Path(sys.argv[2]))
assert report["workspace"] != second["workspace"]
assert Path(report["workspace"]).is_dir()
print("Demo isolation and approval passed")
"""


def test_demo_overrides_live_configuration_and_preserves_prior_runs(tmp_path: Path):
    sentinel = tmp_path / "existing-data"
    sentinel.mkdir()
    marker = sentinel / "keep.txt"
    marker.write_text("must remain unchanged", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", "-c", PROBE, str(SCRIPTS), str(tmp_path / "demo")],
        cwd=tmp_path,
        env={
            **os.environ,
            "NOVELWB_LLM_ADAPTER": "deepseek",
            "NOVELWB_WORKSPACE": str(sentinel),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8") == "must remain unchanged"
    assert sorted(path.name for path in sentinel.iterdir()) == ["keep.txt"]
