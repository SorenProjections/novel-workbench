"""PromptRegistry — 加载 prompts/registry.yaml，校验一致性。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from novelwb.utils.logger import get_logger

logger = get_logger(__name__)


class PromptRegistry:
    """Prompt 注册表，从 prompts/registry.yaml 加载。"""

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._registry: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        registry_file = self._prompts_dir / "registry.yaml"
        if not registry_file.exists():
            logger.warning("prompts/registry.yaml 不存在，注册表为空")
            return

        raw = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "prompts" not in raw:
            raise ValueError("registry.yaml 格式错误：缺少顶层 'prompts' 键")

        errors: list[str] = []
        for entry in raw["prompts"]:
            key = entry.get("prompt_key")
            if not key:
                errors.append("存在缺少 prompt_key 的条目")
                continue

            # 校验 prompt.yaml 存在
            path = entry.get("path", "")
            prompt_yaml = self._prompts_dir / path / "prompt.yaml"
            prompt_jinja = self._prompts_dir / path / "prompt.jinja2"

            if path and not prompt_yaml.exists():
                errors.append(f"{key}: prompt.yaml 不存在于 {prompt_yaml}")
            if path and not prompt_jinja.exists():
                errors.append(f"{key}: prompt.jinja2 不存在于 {prompt_jinja}")

            self._registry[key] = entry

        if errors:
            raise ValueError("PromptRegistry 加载失败:\n" + "\n".join(f"  - {e}" for e in errors))

        logger.info("PromptRegistry 加载完成", extra={"count": len(self._registry)})

    def get(self, prompt_key: str) -> dict[str, Any]:
        if prompt_key not in self._registry:
            raise KeyError(f"prompt_key 未注册: '{prompt_key}'")
        return self._registry[prompt_key]

    def all_keys(self) -> list[str]:
        return list(self._registry.keys())

    def __contains__(self, prompt_key: str) -> bool:
        return prompt_key in self._registry
