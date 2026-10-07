"""Release gates must inspect actual staged and historical bytes without leaking them."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_release.py"
SPEC = importlib.util.spec_from_file_location("release_check", SCRIPT)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    release.git(tmp_path, "init")
    (tmp_path / "README.md").write_text("Synthetic release test\n", encoding="utf-8")
    release.git(tmp_path, "add", "README.md")
    commit(tmp_path)
    return tmp_path


def commit(root: Path) -> None:
    release.git(
        root,
        "-c",
        "user.name=Delivery Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "synthetic fixture",
    )


def fake_token() -> str:
    return "sk-" + "syntheticCredentialOnly0123456789"


def test_scanner_catches_staged_secret_after_worktree_is_cleaned(repository: Path):
    source = repository / "config.txt"
    source.write_text(fake_token(), encoding="utf-8")
    release.git(repository, "add", "config.txt")
    source.write_text("safe placeholder", encoding="utf-8")
    assert release.check(repository, require_delivery=False)["passed"]
    report = release.check(repository, staged=True, require_delivery=False)
    assert not report["passed"]
    assert any(item["rule"] == "credential-token" for item in report["findings"])
    assert fake_token() not in json.dumps(report)


def test_scanner_finds_secret_deleted_from_current_tree(repository: Path):
    source = repository / "retired.txt"
    source.write_text(fake_token(), encoding="utf-8")
    release.git(repository, "add", "retired.txt")
    commit(repository)
    source.unlink()
    release.git(repository, "add", "-u")
    commit(repository)
    assert release.check(repository, require_delivery=False)["passed"]
    report = release.check(repository, history=True, require_delivery=False)
    assert report["history_commits_checked"] == 3
    assert any(item["scope"].startswith("history:") for item in report["findings"])
    assert fake_token() not in json.dumps(report)


def test_ignored_environment_is_not_read_but_force_tracked_one_fails(repository: Path):
    (repository / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repository / ".env").write_text(fake_token(), encoding="utf-8")
    assert release.check(repository, require_delivery=False)["passed"]
    release.git(repository, "add", "-f", ".env")
    report = release.check(repository, require_delivery=False)
    assert any(item["rule"] == "private-or-generated-path" for item in report["findings"])


def test_untracked_chinese_path_is_scanned_without_staging(repository: Path):
    (repository / "新配置.txt").write_text(fake_token(), encoding="utf-8")
    report = release.check(repository, require_delivery=False)
    assert any(item["path"] == "新配置.txt" for item in report["findings"])
    assert release.check(repository, staged=True, require_delivery=False)["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "server/workspace/book.json",
        ".env.production",
        "server/.runtime/backend.log",
        "server/src/novelwb/web/index.html",
        "database.sqlite-wal",
        "server/WORKSPACE/book.json",
    ],
)
def test_runtime_and_local_configuration_are_rejected(path: str):
    assert release.private_path(path)


def test_example_config_is_allowed_but_its_contents_are_scanned():
    assert not release.scan_content(".env.example", b"DEEPSEEK_API_KEY=\n", "worktree")
    assert release.scan_content(".env.example", fake_token().encode(), "worktree")


def test_missing_delivery_documents_fail(repository: Path):
    report = release.check(repository)
    assert any(item["path"] == "LICENSE" for item in report["findings"])


def test_package_license_must_match_repository_license(repository: Path):
    for name in release.REQUIRED:
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic delivery text\n", encoding="utf-8")
    assert release.check(repository)["passed"]
    (repository / "server/LICENSE").write_text("Different license\n", encoding="utf-8")
    report = release.check(repository)
    assert any(item["rule"] == "license-mismatch" for item in report["findings"])
