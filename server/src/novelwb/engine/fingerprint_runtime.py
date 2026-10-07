"""运行时指纹写入 — 启动时计算并写入 run_manifest，检测漂移。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novelwb.core.spec_fingerprint import (
    SpecFingerprint,
    assert_fingerprint_stable,
    compute_fingerprint,
)

_cached_fingerprint: SpecFingerprint | None = None


def get_fingerprint(repo_root: Path, force_recompute: bool = False) -> SpecFingerprint:
    """获取规范指纹（进程内缓存，避免重复计算）。"""
    global _cached_fingerprint
    if _cached_fingerprint is None or force_recompute:
        _cached_fingerprint = compute_fingerprint(repo_root)
    return _cached_fingerprint


def write_fingerprint_to_manifest(manifest: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """将规范指纹写入 run_manifest dict，返回更新后的 manifest。"""
    fp = get_fingerprint(repo_root)
    manifest["spec_hash"] = fp.spec_hash
    manifest["prompt_hash"] = fp.prompt_hash
    manifest["schema_hash"] = fp.schema_hash
    manifest["stepspec_hash"] = fp.stepspec_hash
    manifest["combined_hash"] = fp.combined_hash
    return manifest


def check_drift_or_raise(repo_root: Path, baseline_path: Path | None = None) -> None:
    """检查规范漂移，有漂移则抛出 RuntimeError。

    baseline_path: 保存上次指纹的 JSON 文件路径。
    如果文件不存在，则将当前指纹保存为基准（首次运行）。
    """
    fp = get_fingerprint(repo_root)

    if baseline_path is None:
        baseline_path = repo_root / "docs" / "spec_snapshots" / "fingerprint_baseline.json"

    if not baseline_path.exists():
        # 首次运行：保存基准
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(fp.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    drifts = assert_fingerprint_stable(fp, baseline)

    if drifts:
        drift_msg = "\n".join(f"  - {d}" for d in drifts)
        raise RuntimeError(
            f"规范漂移检测到 {len(drifts)} 处变化，请更新基准或回滚修改：\n{drift_msg}"
        )


def update_baseline(repo_root: Path, baseline_path: Path | None = None) -> None:
    """主动更新基准指纹（规范变更时手动调用）。"""
    fp = get_fingerprint(repo_root, force_recompute=True)

    if baseline_path is None:
        baseline_path = repo_root / "docs" / "spec_snapshots" / "fingerprint_baseline.json"

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(fp.as_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[fingerprint] 基准已更新: {baseline_path}")
    print(f"  combined_hash: {fp.combined_hash[:16]}...")
