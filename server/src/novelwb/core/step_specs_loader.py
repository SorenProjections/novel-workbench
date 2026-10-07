"""StepSpec Loader — 加载并校验所有 StepSpec YAML 文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from novelwb.utils.logger import get_logger

logger = get_logger(__name__)

_SPEC_DIR_NAME = "step_specs"
_SCHEMA_FILE_NAME = "stepspec_schema.json"


def _load_stepspec_schema(core_dir: Path) -> dict[str, Any]:
    schema_path = core_dir / _SPEC_DIR_NAME / _SCHEMA_FILE_NAME
    if not schema_path.exists():
        raise FileNotFoundError(f"StepSpec JSONSchema 不存在: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError(f"StepSpec JSONSchema 必须是对象: {schema_path}")
    return schema


def _validate_against_schema(spec: dict[str, Any], schema: dict[str, Any], path: Path) -> list[str]:
    """简单字段校验（不引入 jsonschema 依赖，手动检查 required 字段）。"""
    errors: list[str] = []
    required = schema.get("required", [])
    for field in required:
        if field not in spec:
            errors.append(f"{path.name}: 缺少必填字段 '{field}'")
    return errors


def load_all_stepspecs(core_dir: Path) -> dict[str, dict[str, Any]]:
    """加载 core/step_specs/*.yaml，返回 {step_key: spec_dict}。"""
    spec_dir = core_dir / _SPEC_DIR_NAME
    schema = _load_stepspec_schema(core_dir)

    specs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for yaml_file in sorted(spec_dir.glob("*.yaml")):
        try:
            spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{yaml_file.name}: YAML解析失败 - {e}")
            continue

        if not isinstance(spec, dict):
            errors.append(f"{yaml_file.name}: 顶层必须是 dict")
            continue

        field_errors = _validate_against_schema(spec, schema, yaml_file)
        errors.extend(field_errors)

        step_key = spec.get("step_key", yaml_file.stem)
        if step_key in specs:
            errors.append(f"step_key 重复: '{step_key}' 在 {yaml_file.name}")
        else:
            specs[step_key] = spec

    if errors:
        raise ValueError("StepSpec 加载失败:\n" + "\n".join(f"  - {e}" for e in errors))

    logger.info("StepSpec 加载完成", extra={"count": len(specs)})
    return specs


def get_stepspec(step_key: str, core_dir: Path) -> dict[str, Any]:
    """获取单个 StepSpec，不存在则抛出 KeyError。"""
    specs = load_all_stepspecs(core_dir)
    if step_key not in specs:
        raise KeyError(f"step_key 未注册: '{step_key}'")
    return specs[step_key]
