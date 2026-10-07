"""JSONL 工具 — 追加写入、流式读取，用于事件索引和运行日志。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from novelwb.utils.io_atomic import ensure_dir
from novelwb.utils.transactions import prepare_write


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """追加一条记录到 JSONL 文件（线程安全级别：进程内单线程）。"""
    ensure_dir(path.parent)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    prepare_write(path, append=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """流式读取 JSONL 文件，逐行解析。"""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_jsonl_all(path: Path) -> list[dict[str, Any]]:
    """读取全部 JSONL 记录到列表。"""
    return list(read_jsonl(path))


def read_last_jsonl(path: Path) -> dict[str, Any] | None:
    """读取 JSONL 最后一条记录（用于获取 latest 状态）。"""
    last = None
    for record in read_jsonl(path):
        last = record
    return last
