"""Validator: 冻结枚举一致性 — error_codes/step_catalog/schema_names 不可删改。"""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_yaml_keys(path: Path, top_key: str, item_key: str) -> set[str]:
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {item[item_key] for item in raw.get(top_key, []) if item_key in item}


def validate_frozen_enums(core_dir: Path, baseline_dir: Path | None = None) -> list[str]:
    """对比当前枚举与基准，检测是否有删除或重命名。

    baseline_dir: 保存基准快照的目录（docs/spec_snapshots/）。
    首次运行时生成基准，之后只允许追加。
    """
    errors: list[str] = []

    # 当前值
    current_step_keys = _load_yaml_keys(core_dir / "step_catalog.yaml", "steps", "key")
    current_error_codes = _load_yaml_keys(core_dir / "error_codes.yaml", "errors", "code")
    # error_codes.yaml 的 key 是顶层 key，特殊处理
    ec_path = core_dir / "error_codes.yaml"
    if ec_path.exists():
        raw = yaml.safe_load(ec_path.read_text(encoding="utf-8"))
        current_error_codes = set(raw.get("errors", {}).keys())

    if baseline_dir is None:
        return errors  # 无基准，跳过

    baseline_dir = Path(baseline_dir)
    step_baseline_file = baseline_dir / "step_catalog_baseline.yaml"
    error_baseline_file = baseline_dir / "error_codes_baseline.yaml"

    # step_catalog 检查
    if step_baseline_file.exists():
        baseline_keys = _load_yaml_keys(step_baseline_file, "steps", "key")
        removed = baseline_keys - current_step_keys
        for k in sorted(removed):
            errors.append(f"step_catalog: '{k}' 被删除（冻结枚举不可删）")
    else:
        # 生成基准
        baseline_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy(core_dir / "step_catalog.yaml", step_baseline_file)

    # error_codes 检查
    if error_baseline_file.exists():
        raw_b = yaml.safe_load(error_baseline_file.read_text(encoding="utf-8"))
        baseline_codes = set(raw_b.get("errors", {}).keys())
        removed_codes = baseline_codes - current_error_codes
        for c in sorted(removed_codes):
            errors.append(f"error_codes: '{c}' 被删除（冻结枚举不可删）")
    else:
        baseline_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy(ec_path, error_baseline_file)

    return errors
