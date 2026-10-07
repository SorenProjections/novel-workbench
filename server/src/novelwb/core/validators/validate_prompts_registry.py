"""Validator: prompts/registry ↔ prompt.yaml/version/path/schema_name 一致。"""

from __future__ import annotations

from pathlib import Path

import yaml


def validate_prompts_registry(prompts_dir: Path, schema_registry_keys: set[str]) -> list[str]:
    """返回错误列表，空列表表示通过。"""
    errors: list[str] = []

    registry_file = prompts_dir / "registry.yaml"
    if not registry_file.exists():
        # 阶段7前 registry 还未创建，仅警告
        return ["[WARN] prompts/registry.yaml 尚未创建（阶段7前可忽略）"]

    try:
        raw = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [f"registry.yaml 解析失败: {e}"]

    if not isinstance(raw, dict) or "prompts" not in raw:
        return ["registry.yaml 缺少顶层 'prompts' 键"]

    seen_keys: set[str] = set()
    for entry in raw.get("prompts", []):
        key = entry.get("prompt_key", "")
        version = entry.get("prompt_version", "")
        path = entry.get("path", "")
        schema_name = entry.get("schema_name", "")

        if not key:
            errors.append("存在缺少 prompt_key 的条目")
            continue

        if key in seen_keys:
            errors.append(f"prompt_key 重复: '{key}'")
        seen_keys.add(key)

        if not version:
            errors.append(f"{key}: 缺少 prompt_version")

        if not path:
            errors.append(f"{key}: 缺少 path")
        else:
            prompt_yaml = prompts_dir / path / "prompt.yaml"
            prompt_jinja = prompts_dir / path / "prompt.jinja2"
            if not prompt_yaml.exists():
                errors.append(f"{key}: 缺少 {prompt_yaml}")
            if not prompt_jinja.exists():
                errors.append(f"{key}: 缺少 {prompt_jinja}")
            else:
                # 校验 prompt.yaml 中的 version 与 registry 一致
                try:
                    py = yaml.safe_load(prompt_yaml.read_text(encoding="utf-8"))
                    if py.get("version") != version:
                        errors.append(
                            f"{key}: registry version '{version}' != "
                            f"prompt.yaml version '{py.get('version')}'"
                        )
                except Exception as e:
                    errors.append(f"{key}: prompt.yaml 读取失败 - {e}")

        if schema_name and schema_name not in schema_registry_keys:
            errors.append(f"{key}: schema_name '{schema_name}' 未在 schema_registry 注册")

    return errors
