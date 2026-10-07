#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_spec_sync.py — 规范同步检查脚本

验证：
  1. StepSpec ↔ step_catalog 全覆盖
  2. Prompt registry ↔ prompt.yaml 一致
  3. Schema version 字段存在
  4. Workspace repo 布局完整
  5. 冻结枚举未被删除
  6. 真值链引用完整（StepSpec→prompt_key/schema_name）

CI 必跑，任意失败直接退出码 1。
"""

import sys
from pathlib import Path

# 修复 Windows 终端编码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 定位路径
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SERVER_SRC = REPO_ROOT / "server" / "src"

sys.path.insert(0, str(SERVER_SRC))

from novelwb.core.schema_registry import all_schema_names
from novelwb.core.validators.validate_step_specs import validate_step_specs
from novelwb.core.validators.validate_prompts_registry import validate_prompts_registry
from novelwb.core.validators.validate_schema_version import validate_schema_version
from novelwb.core.validators.validate_workspace_layout import validate_repo_layout
from novelwb.core.validators.validate_frozen_enums import validate_frozen_enums
from novelwb.core.validators.validate_truth_chains import validate_truth_chains

CORE_DIR = SERVER_SRC / "novelwb" / "core"
PROMPTS_DIR = SERVER_SRC / "novelwb" / "prompts"
SCHEMA_DIR = CORE_DIR / "schemas"
BASELINE_DIR = REPO_ROOT / "docs" / "spec_snapshots"

all_errors: list[str] = []
all_warnings: list[str] = []

def run_check(name: str, errors: list[str]) -> None:
    warnings = [e for e in errors if e.startswith("[WARN]")]
    real_errors = [e for e in errors if not e.startswith("[WARN]")]
    if real_errors:
        print(f"[FAIL] {name}")
        for e in real_errors:
            print(f"       {e}")
        all_errors.extend(real_errors)
    elif warnings:
        print(f"[WARN] {name}")
        for w in warnings:
            print(f"       {w}")
        all_warnings.extend(warnings)
    else:
        print(f"[ OK ] {name}")


print("=" * 60)
print("check_spec_sync — 规范同步检查")
print("=" * 60)

schema_keys = all_schema_names()

run_check("1. repo 布局",
    validate_repo_layout(REPO_ROOT))

run_check("2. StepSpec ↔ step_catalog",
    validate_step_specs(CORE_DIR))

run_check("3. Prompt registry",
    validate_prompts_registry(PROMPTS_DIR, schema_keys))

run_check("4. Schema version 字段",
    validate_schema_version(SCHEMA_DIR))

run_check("5. 冻结枚举",
    validate_frozen_enums(CORE_DIR, BASELINE_DIR))

run_check("6. 真值链引用",
    validate_truth_chains(CORE_DIR, PROMPTS_DIR, schema_keys))

print("=" * 60)
if all_errors:
    print(f"FAILED — {len(all_errors)} 个错误，{len(all_warnings)} 个警告")
    sys.exit(1)
else:
    print(f"PASSED — 0 错误，{len(all_warnings)} 个警告")
    sys.exit(0)
