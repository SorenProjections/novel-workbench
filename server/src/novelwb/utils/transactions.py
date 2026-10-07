"""Durable undo journals for multi-file commits and isolated project reads."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar
from uuid import uuid4

from novelwb.utils.file_locks import lock_path

_current: ContextVar[Transaction | None] = ContextVar("file_transaction", default=None)
T = TypeVar("T", bound=type)
P = ParamSpec("P")
R = TypeVar("R")


def durable_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Transaction:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = self.root / ".transactions" / uuid4().hex
        self.entries: dict[str, dict[str, Any]] = {}
        self.started = False

    def prepare(self, path: Path, *, append: bool = False) -> None:
        target = path.resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("事务写入不能越出项目目录")
        relative = target.relative_to(self.root).as_posix()
        entry: dict[str, Any]
        if relative.startswith((".transactions/", "runs/tasks/")) or relative.endswith(".lock"):
            return
        if relative in self.entries:
            entry = self.entries[relative]
            if not append and "size" in entry:
                backup = f"before_{uuid4().hex}"
                durable_replace(self.directory / backup, target.read_bytes()[: entry["size"]])
                entry["backup"] = backup
                del entry["size"]
                self.mark("prepared")
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = {"path": relative, "exists": target.exists()}
        if target.exists():
            if append:
                entry["size"] = target.stat().st_size
            else:
                backup = f"before_{len(self.entries)}"
                durable_replace(self.directory / backup, target.read_bytes())
                entry["backup"] = backup
        first_write = not self.started
        self.entries[relative] = entry
        self.started = True
        self.mark("prepared")
        if first_write:
            durable_replace(
                self.root / ".transactions" / "pending.json",
                json.dumps({"id": self.directory.name}).encode(),
            )

    def mark(self, state: str) -> None:
        durable_replace(
            self.directory / "journal.json",
            json.dumps({"state": state, "entries": list(self.entries.values())}).encode(),
        )


def _restore(root: Path, directory: Path, entries: list[dict[str, Any]]) -> None:
    for entry in reversed(entries):
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("恢复日志中的路径越出项目目录")
        if not entry["exists"]:
            target.unlink(missing_ok=True)
        elif "size" in entry:
            with target.open("r+b") as file:
                file.truncate(entry["size"])
                file.flush()
                os.fsync(file.fileno())
        else:
            backup = (directory / entry["backup"]).resolve()
            if backup.parent != directory.resolve():
                raise ValueError("恢复日志中的备份路径非法")
            durable_replace(target, backup.read_bytes())


def _recover(root: Path) -> None:
    pending = root / ".transactions" / "pending.json"
    if not pending.exists():
        return
    data = json.loads(pending.read_text(encoding="utf-8"))
    directory = (root / ".transactions" / data["id"]).resolve()
    if directory.parent != (root / ".transactions").resolve():
        raise ValueError("事务恢复路径非法")
    journal = directory / "journal.json"
    if journal.exists():
        state = json.loads(journal.read_text(encoding="utf-8"))
        if state["state"] == "prepared":
            _restore(root, directory, state["entries"])
            state["state"] = "recovered"
            durable_replace(journal, json.dumps(state).encode())
    pending.unlink(missing_ok=True)


@contextmanager
def project_guard(root: Path) -> Iterator[None]:
    root = root.resolve()
    current = _current.get()
    if current is not None and current.root == root:
        yield
        return
    with lock_path(root / ".project", timeout=30):
        _recover(root)
        yield


@contextmanager
def transaction(root: Path) -> Iterator[Transaction]:
    root = root.resolve()
    current = _current.get()
    if current is not None:
        if current.root != root:
            raise ValueError("不能嵌套跨项目事务")
        yield current
        return
    with project_guard(root):
        current = Transaction(root)
        token = _current.set(current)
        pending = root / ".transactions" / "pending.json"
        try:
            yield current
            if current.started:
                current.mark("committed")
        except BaseException:
            if current.started:
                _restore(root, current.directory, list(current.entries.values()))
                current.mark("rolled_back")
            raise
        finally:
            _current.reset(token)
        pending.unlink(missing_ok=True)


def prepare_write(path: Path, *, append: bool = False) -> None:
    current = _current.get()
    if current is not None:
        current.prepare(path, append=append)


def atomic_method(method: Callable[P, R]) -> Callable[P, R]:
    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        self: Any = args[0]
        with transaction(self._layout.project_dir):
            return method(*args, **kwargs)

    return wrapped


def read_method(method: Callable[P, R]) -> Callable[P, R]:
    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        self: Any = args[0]
        with project_guard(self._layout.project_dir):
            return method(*args, **kwargs)

    return wrapped


def guarded_store(cls: T) -> T:
    for name, method in list(vars(cls).items()):
        if name.startswith("_") or not callable(method) or isinstance(method, staticmethod):
            continue
        wrapper = (
            atomic_method
            if name.startswith(
                ("commit", "save", "publish", "delete", "invalidate", "reactivate", "seed", "apply")
            )
            else read_method
        )
        setattr(cls, name, wrapper(method))
    return cls
