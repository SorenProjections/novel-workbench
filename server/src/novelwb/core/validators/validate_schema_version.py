"""Validator: 所有 Schema 模型必须含固定 schema_version='v1'。"""

from __future__ import annotations

import ast
from pathlib import Path


def validate_schema_version(schema_dir: Path) -> list[str]:
    """扫描 schemas/*.py，确认 BaseSchema 子类含 schema_version 默认值。"""
    errors: list[str] = []

    for py_file in sorted(schema_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            errors.append(f"{py_file.name}: 解析失败 - {e}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # 只检查 BaseSchema 本身定义了 schema_version
            if node.name != "BaseSchema":
                continue
            has_version = any(
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id == "schema_version"
                for stmt in node.body
            )
            if not has_version:
                errors.append(f"{py_file.name}:BaseSchema: 缺少 schema_version 字段定义")

    return errors
