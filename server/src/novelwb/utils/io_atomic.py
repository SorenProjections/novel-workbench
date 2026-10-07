"""Durable atomic writes with participation in the current project transaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novelwb.utils.transactions import durable_replace, prepare_write


def atomic_write_bytes(path: Path, data: bytes) -> None:
    prepare_write(path)
    durable_replace(path, data)


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=indent))


def atomic_delete(path: Path) -> None:
    prepare_write(path)
    path.unlink(missing_ok=True)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
