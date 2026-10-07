"""Validator: 真值链闸门 — StepSpec/Prompt/Schema/Action枚举全量互引用检查。"""

from __future__ import annotations

from pathlib import Path

import yaml


def validate_truth_chains(
    core_dir: Path,
    prompts_dir: Path,
    schema_registry_keys: set[str],
) -> list[str]:
    """检查 StepSpec → prompt_key、output_schema 的引用都能找到对应实体。"""
    errors: list[str] = []

    # 已注册的 prompt_key
    registry_file = prompts_dir / "registry.yaml"
    registered_prompts: set[str] = set()
    if registry_file.exists():
        raw = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
        registered_prompts = {e["prompt_key"] for e in raw.get("prompts", []) if "prompt_key" in e}

    # 已注册的 step_key
    catalog_file = core_dir / "step_catalog.yaml"
    catalog_keys: set[str] = set()
    if catalog_file.exists():
        raw_c = yaml.safe_load(catalog_file.read_text(encoding="utf-8"))
        catalog_keys = {s["key"] for s in raw_c.get("steps", [])}

    # 遍历所有 StepSpec YAML
    spec_dir = core_dir / "step_specs"
    for yaml_file in sorted(spec_dir.glob("*.yaml")):
        try:
            spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(spec, dict):
            continue

        step_key = spec.get("step_key", yaml_file.stem)

        # 1. step_key 必须在 catalog
        if step_key not in catalog_keys:
            errors.append(f"{step_key}: step_key 未在 step_catalog 注册")

        # 2. prompt_key 必须在 registry（registry 存在时才检查）
        prompt_key = spec.get("llm", {}).get("prompt_key", "")
        if prompt_key and registered_prompts and prompt_key not in registered_prompts:
            errors.append(f"{step_key}: prompt_key '{prompt_key}' 未在 prompts/registry.yaml 注册")

        # 3. input_schema / output_schema 必须在 schema_registry
        for schema_field in ("input_schema", "output_schema"):
            schema_name = spec.get(schema_field, "")
            if schema_name and schema_name not in schema_registry_keys:
                errors.append(
                    f"{step_key}: {schema_field} '{schema_name}' 未在 schema_registry 注册"
                )

    return errors
