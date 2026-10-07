"""Local release hygiene checks. Never prints credential values or changes Git state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "LICENSE",
    "server/LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".env.example",
    "docs/DEMO.md",
    "docs/RELEASING.md",
    ".github/workflows/ci.yml",
)
PRIVATE_DIRECTORIES = {
    "workspace",
    "cache",
    ".runtime",
    ".checks",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SECRET_PATTERNS = {
    "credential-token": re.compile(
        rb"(?<![\w-])(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"
        rb"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}"
        rb"|AKIA[0-9A-Z]{16})(?![\w-])"
    ),
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "credential-in-url": re.compile(rb"https?://[^\s/:@]+:[^\s/@]+@"),
    "credential-assignment": re.compile(
        rb"(?i)\b(?:[A-Z0-9_]*API_KEY|[A-Z0-9_]*ACCESS_TOKEN|CLIENT_SECRET|PASSWORD)"
        rb"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9+/=_-]{24,})"
    ),
}


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # Git output can contain file contents; do not echo it into a release log.
        raise RuntimeError(f"git {args[0]} failed; check repository state locally")
    return result.stdout


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    lower = path.name.lower()
    environment = lower == ".env" or lower.startswith(".env.")
    return (
        bool({part.lower() for part in path.parts} & PRIVATE_DIRECTORIES)
        or (environment and not lower.endswith(".example"))
        or lower.endswith((".log", ".pid", ".db", ".sqlite", ".sqlite3", ".pem", ".key"))
        or bool(re.search(r"\.(?:db|sqlite3?)-(?:wal|shm|journal)$", lower))
        or name.startswith("server/src/novelwb/web/")
    )


def scan_content(name: str, data: bytes, scope: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if private_path(name):
        findings.append({"scope": scope, "path": name, "rule": "private-or-generated-path"})
    if len(data) > 5 * 1024 * 1024:
        findings.append({"scope": scope, "path": name, "rule": "file-exceeds-5MiB-review-needed"})
    for rule, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(data):
            findings.append(
                {
                    "scope": scope,
                    "path": name,
                    "rule": rule,
                    "line": data[: match.start()].count(b"\n") + 1,
                }
            )
    return findings


def blobs(root: Path, identifiers: set[str]) -> dict[str, bytes]:
    if not identifiers:
        return {}
    output = git(
        root,
        "cat-file",
        "--batch",
        data="".join(f"{identifier}\n" for identifier in sorted(identifiers)).encode("ascii"),
    )
    result: dict[str, bytes] = {}
    offset = 0
    while offset < len(output):
        end = output.index(b"\n", offset)
        identifier, kind, size_text = output[offset:end].split()
        if kind != b"blob":
            raise RuntimeError("Expected a Git blob")
        size = int(size_text)
        offset = end + 1
        result[identifier.decode("ascii")] = output[offset : offset + size]
        offset += size + 1
    return result


def index_entries(root: Path) -> list[tuple[str, str, str]]:
    entries = []
    for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, identifier, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError("Resolve index conflicts before checking a release")
        entries.append((name.decode("utf-8"), mode, identifier))
    return entries


def snapshot(root: Path, staged: bool) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    files: dict[str, bytes] = {}
    findings: list[dict[str, Any]] = []
    if staged:
        entries = index_entries(root)
        objects = blobs(root, {oid for _, mode, oid in entries if mode in {"100644", "100755"}})
        for name, mode, identifier in entries:
            if mode not in {"100644", "100755"}:
                findings.append({"scope": "index", "path": name, "rule": "non-regular-file"})
            else:
                files[name] = objects[identifier]
    else:
        names = set(
            git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
        )
        for raw in sorted(names - {b""}):
            name = raw.decode("utf-8")
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                findings.append({"scope": "worktree", "path": name, "rule": "non-regular-file"})
            elif path.is_file():
                files[name] = path.read_bytes()
    return files, findings


def scan_history(root: Path) -> tuple[list[dict[str, Any]], int, int]:
    commits = git(root, "rev-list", "--all", "HEAD").decode("ascii").splitlines()
    entries: dict[tuple[str, str, str], str] = {}
    for commit in commits:
        for record in git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
            if not record:
                continue
            metadata, raw_name = record.split(b"\t", 1)
            mode, _, identifier = metadata.decode("ascii").split()
            entries.setdefault((raw_name.decode("utf-8"), mode, identifier), commit[:12])
    objects = blobs(root, {oid for _, mode, oid in entries if mode in {"100644", "100755"}})
    findings = []
    for (name, mode, identifier), commit in entries.items():
        scope = f"history:{commit}"
        if mode not in {"100644", "100755"}:
            findings.append({"scope": scope, "path": name, "rule": "non-regular-file"})
        else:
            findings.extend(scan_content(name, objects[identifier], scope))
    return findings, len(commits), len(objects)


def check(
    root: Path, *, staged: bool = False, history: bool = False, require_delivery: bool = True
) -> dict[str, Any]:
    root = root.resolve()
    if Path(git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve() != root:
        raise RuntimeError("Run against the novel-workbench repository root")
    files, findings = snapshot(root, staged)
    scope = "index" if staged else "worktree"
    if require_delivery:
        for name in REQUIRED:
            if not files.get(name):
                findings.append({"scope": scope, "path": name, "rule": "missing-delivery-file"})
        if files.get("LICENSE") and files.get("server/LICENSE"):
            canonical = files["LICENSE"].replace(b"\r\n", b"\n")
            packaged = files["server/LICENSE"].replace(b"\r\n", b"\n")
            if canonical != packaged:
                findings.append(
                    {"scope": scope, "path": "server/LICENSE", "rule": "license-mismatch"}
                )
    for name, data in files.items():
        findings.extend(scan_content(name, data, scope))
    commits = objects = 0
    if history:
        historical, commits, objects = scan_history(root)
        findings.extend(historical)
    return {
        "passed": not findings,
        "scope": scope,
        "files_checked": len(files),
        "history_commits_checked": commits,
        "history_blobs_checked": objects,
        "findings": findings,
        "limits": "Pattern-based hygiene check; not a comprehensive security or license audit. "
        "History covers reachable local refs and HEAD, not reflogs or unreachable objects.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index", action="store_true", help="inspect staged bytes instead of working files"
    )
    parser.add_argument(
        "--history", action="store_true", help="also inspect all reachable local Git history"
    )
    parser.add_argument("--output", type=Path, help="write a JSON report without credential values")
    args = parser.parse_args()
    try:
        report = check(ROOT, staged=args.index, history=args.history)
    except (RuntimeError, OSError) as exc:
        parser.exit(2, f"Release check could not finish: {exc}\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    for finding in report["findings"]:
        line = f":{finding['line']}" if "line" in finding else ""
        print(f"[FAIL] {finding['scope']} {finding['path']}{line} ({finding['rule']})")
    label = "PASS" if report["passed"] else "FAIL"
    print(
        f"[{label}] {report['files_checked']} {report['scope']} files; "
        f"{report['history_commits_checked']} history commits; {len(report['findings'])} findings"
    )
    print(report["limits"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
