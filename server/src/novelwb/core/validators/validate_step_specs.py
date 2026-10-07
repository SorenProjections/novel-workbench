"""Validator: StepSpec ↔ step_catalog 全覆盖/字段合法/offline&RAG合规。"""

from __future__ import annotations

from pathlib import Path

import yaml


def validate_step_specs(core_dir: Path) -> list[str]:
    """返回错误列表，空列表表示通过。"""
    errors: list[str] = []

    # 加载 step_catalog
    catalog_file = core_dir / "step_catalog.yaml"
    if not catalog_file.exists():
        return ["step_catalog.yaml 不存在"]
    catalog_raw = yaml.safe_load(catalog_file.read_text(encoding="utf-8"))
    catalog_keys: set[str] = {s["key"] for s in catalog_raw.get("steps", [])}

    # 加载所有 StepSpec YAML
    spec_dir = core_dir / "step_specs"
    spec_keys: set[str] = set()
    for yaml_file in spec_dir.glob("*.yaml"):
        try:
            spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{yaml_file.name}: YAML解析失败 - {e}")
            continue
        if not isinstance(spec, dict):
            continue

        key = spec.get("step_key", "")
        spec_keys.add(key)

        # step_key 必须在 catalog 中
        if key and key not in catalog_keys:
            errors.append(f"{yaml_file.name}: step_key '{key}' 未在 step_catalog.yaml 注册")

        # RAG step 当前版本必须 enabled=false
        rag_cfg = spec.get("rag", {})
        if rag_cfg.get("enabled", False):
            errors.append(f"{key}: RAG 当前版本禁止启用 (enabled must be false)")

        # offline 默认应为 true，除非明确豁免
        llm_cfg = spec.get("llm", {})
        if llm_cfg.get("offline") is False and key != "graphR.material.rag":
            errors.append(f"{key}: offline=false 仅允许 graphR.material.rag")

        # best_of_n 范围检查
        bon = llm_cfg.get("best_of_n", 1)
        if not (1 <= bon <= 5):
            errors.append(f"{key}: best_of_n={bon} 超出范围 [1,5]")

        model = llm_cfg.get("model")
        if model and model not in {"deepseek-v4-pro", "deepseek-v4-flash"}:
            errors.append(f"{key}: llm.model={model!r} 非法")

        thinking = llm_cfg.get("thinking")
        if thinking and thinking not in {"enabled", "disabled"}:
            errors.append(f"{key}: llm.thinking={thinking!r} 非法")

        effort = llm_cfg.get("reasoning_effort")
        if effort and effort not in {"high", "max"}:
            errors.append(f"{key}: llm.reasoning_effort={effort!r} 非法")

        response_format = llm_cfg.get("response_format")
        if response_format and response_format != "json_object":
            errors.append(f"{key}: llm.response_format={response_format!r} 非法")

    # catalog 中的 key 必须都有对应 StepSpec（graphR 例外，当前跳过）
    # 注：StepSpec YAML 在阶段7写入，阶段6前以 [WARN] 形式报告
    missing_specs = catalog_keys - spec_keys - {"graphR.material.rag"}
    for k in sorted(missing_specs):
        errors.append(f"[WARN] step_catalog 中的 '{k}' 尚无 StepSpec YAML（阶段7前可忽略）")

    return errors
