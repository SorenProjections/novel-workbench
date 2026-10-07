"""Check wheel resources and run a mock workflow outside the source checkout."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import logging
import os
import re
import time
from pathlib import Path
import novelwb
from fastapi.testclient import TestClient
from novelwb.api.main import app

logging.getLogger("httpx").setLevel(logging.WARNING)
package = Path(novelwb.__file__).resolve().parent
assert package.parent == Path(os.environ["NOVELWB_PACKAGE_ROOT"]).resolve(), package
assert (package / "core/step_specs/stepspec_schema.json").is_file()
assert (package / "web/index.html").is_file()
assert (package / "web/THIRD_PARTY_NOTICES.txt").is_file()
with TestClient(app) as client:
    assert client.get("/health").status_code == 200
    page = client.get("/")
    assert page.status_code == 200 and "/ui/assets/" in page.text
    notices = client.get("/ui/THIRD_PARTY_NOTICES.txt")
    assert notices.status_code == 200 and "lucide-react" in notices.text
    assets = re.findall(r'(?:src|href)="(/ui/assets/[^"]+)"', page.text)
    assert assets
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200 and response.content, asset
    assert client.post("/projects", json={"project_id": "wheel_probe"}).status_code == 200
    assert client.get("/projects/wheel_probe/pipeline/workflow").status_code == 200
    url = "/projects/wheel_probe/pipeline/runs"
    body = {"run_id": "run_package", "kind": "workflow", "params": {
        "stage": "foundation", "brief": "渡口停航引发的补给争执。"}}
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = client.get(url + "/run_package").json()["data"]
        if state["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(0.05)
    assert state["status"] == "completed", state
    review = state["result"]["review"]
    approval = client.post(
        f"/projects/wheel_probe/pipeline/workflow/reviews/{review['staging_id']}/approve",
        json={"editable": review["editable"]})
    assert approval.status_code == 200, approval.text
    assert "event: result" in client.get(url + "/run_package/events").text
print("Package probe passed: bundled resources, static UI, mock generation, approval and replay")
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", type=Path, default=ROOT / ".checks/wheels")
    parser.add_argument("--workspace", type=Path, default=ROOT / ".checks/package")
    args = parser.parse_args()
    wheels = sorted(args.wheel_dir.glob("novelwb-*.whl"))
    if len(wheels) != 1:
        parser.error("wheel-dir must contain exactly one novelwb wheel")
    destination = args.workspace.resolve() / uuid4().hex
    destination.mkdir(parents=True, exist_ok=False)
    with ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        assert (
            metadata["License-Expression"] == "MIT"
            or "MIT License" in metadata.get("License", "")
        ), "Missing MIT package metadata"
        license_name = next(
            name for name in names if ".dist-info/" in name and name.endswith("/LICENSE")
        )
        canonical = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
        assert archive.read(license_name).replace(b"\r\n", b"\n") == canonical
        for name in archive.namelist():
            if not (destination / name).resolve().is_relative_to(destination):
                raise ValueError("Wheel contains a path outside the extraction directory")
        archive.extractall(destination)
    environment = {
        **os.environ,
        "PYTHONPATH": str(destination),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "NOVELWB_PACKAGE_ROOT": str(destination),
        "NOVELWB_WORKSPACE": str(destination / "workspace"),
        "NOVELWB_LLM_ADAPTER": "mock",
        "NOVELWB_MOCK_FIXTURES": str(ROOT / "server/tests/fixtures/mock"),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", PROBE], cwd=destination, env=environment, timeout=60
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
