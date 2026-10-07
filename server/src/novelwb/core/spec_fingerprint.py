"""规范指纹计算 — spec_hash/prompt_hash/schema_hash/stepspec_hash。

每次启动时计算，写入 run_manifest。
任意一个 hash 变化 → 规范漂移 → CI 失败。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from novelwb.utils.hashing import file_hash, stable_hash


@dataclass(frozen=True)
class SpecFingerprint:
    """一次计算的规范指纹快照。"""

    spec_hash: str  # SPEC_v1.md 内容 hash
    prompt_hash: str  # prompts/registry.yaml + 所有 prompt.yaml hash
    schema_hash: str  # 所有 Pydantic schema 模块 hash
    stepspec_hash: str  # 所有 StepSpec YAML hash
    combined_hash: str  # 四者合并 hash（写入 run_manifest）

    def as_dict(self) -> dict[str, str]:
        return {
            "spec_hash": self.spec_hash,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "stepspec_hash": self.stepspec_hash,
            "combined_hash": self.combined_hash,
        }


def _hash_dir_yaml(directory: Path, glob: str = "**/*.yaml") -> str:
    """对目录下所有 YAML 文件按路径排序后合并 hash。"""
    files = sorted(directory.glob(glob))
    parts: list[str] = []
    for f in files:
        parts.append(f"{f.relative_to(directory)}:{file_hash(str(f))}")
    combined = "\n".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _hash_python_schemas(schema_dir: Path) -> str:
    """对 schemas/ 目录下所有 .py 文件按路径排序后合并 hash。"""
    files = sorted(schema_dir.glob("*.py"))
    parts: list[str] = []
    for f in files:
        parts.append(f"{f.name}:{file_hash(str(f))}")
    combined = "\n".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_fingerprint(repo_root: Path) -> SpecFingerprint:
    """计算完整规范指纹。repo_root 是 novel-workbench/ 目录。"""
    server_src = repo_root / "server" / "src" / "novelwb"

    # 1. SPEC hash
    spec_file = repo_root / "SPEC_v1.md"
    spec_hash = file_hash(str(spec_file)) if spec_file.exists() else "missing"

    # 2. Prompt hash = registry.yaml + 所有 prompt.yaml
    prompts_dir = server_src / "prompts"
    prompt_hash = _hash_dir_yaml(prompts_dir, "**/*.yaml") if prompts_dir.exists() else "missing"

    # 3. Schema hash = schemas/*.py
    schema_dir = server_src / "core" / "schemas"
    schema_hash = _hash_python_schemas(schema_dir) if schema_dir.exists() else "missing"

    # 4. StepSpec hash = core/step_specs/*.yaml
    stepspec_dir = server_src / "core" / "step_specs"
    stepspec_hash = _hash_dir_yaml(stepspec_dir, "*.yaml") if stepspec_dir.exists() else "missing"

    # 5. Combined
    combined = stable_hash(
        {
            "spec": spec_hash,
            "prompt": prompt_hash,
            "schema": schema_hash,
            "stepspec": stepspec_hash,
        }
    )

    return SpecFingerprint(
        spec_hash=spec_hash,
        prompt_hash=prompt_hash,
        schema_hash=schema_hash,
        stepspec_hash=stepspec_hash,
        combined_hash=combined,
    )


def assert_fingerprint_stable(
    current: SpecFingerprint,
    baseline: dict[str, str],
) -> list[str]:
    """对比当前指纹与基准，返回漂移项列表（空=无漂移）。"""
    drifts: list[str] = []
    for key in ("spec_hash", "prompt_hash", "schema_hash", "stepspec_hash"):
        cur_val = getattr(current, key)
        base_val = baseline.get(key)
        if base_val and cur_val != base_val:
            drifts.append(f"{key}: {base_val[:8]}... -> {cur_val[:8]}...")
    return drifts
