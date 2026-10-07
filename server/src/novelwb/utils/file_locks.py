"""Reentrant OS locks, automatically released when a worker exits."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from weakref import WeakValueDictionary


class LockTimeoutError(RuntimeError):
    """The lock could not be acquired within its deadline."""


_registry_guard = threading.Lock()
_locks: WeakValueDictionary[str, threading.RLock] = WeakValueDictionary()
_held = threading.local()


def shared_thread_lock(resource: Path, scope: str) -> threading.RLock:
    """Keep a resource's in-process guard shared across independently configured owners."""
    key = f"{os.path.normcase(str(resource.resolve()))}::{scope}"
    with _registry_guard:
        return _locks.setdefault(key, threading.RLock())


class FileLock:
    """Advisory OS lock: a persistent .lock file is never a stale owner."""

    def __init__(self, path: Path, timeout: float = 10.0, poll: float = 0.05) -> None:
        self.lock_path = Path(str(path) + ".lock").resolve()
        self.timeout = timeout
        self.poll = poll
        self._key = os.path.normcase(str(self.lock_path))
        with _registry_guard:
            self._thread_lock = _locks.setdefault(self._key, threading.RLock())
        self._depth = 0

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout
        if not self._thread_lock.acquire(timeout=max(0, self.timeout)):
            raise LockTimeoutError(f"无法在 {self.timeout}s 内获取锁: {self.lock_path}")
        owners: dict[str, tuple[BinaryIO, int]] = getattr(_held, "owners", {})
        _held.owners = owners
        if self._key in owners:
            held_file, depth = owners[self._key]
            owners[self._key] = (held_file, depth + 1)
            self._depth += 1
            return
        file: BinaryIO | None = None
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            file = self.lock_path.open("a+b")
            if self.lock_path.stat().st_size == 0:
                file.write(b"0")
                file.flush()
            while True:
                try:
                    file.seek(0)
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    owners[self._key] = (file, 1)
                    self._depth += 1
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise LockTimeoutError(
                            f"无法在 {self.timeout}s 内获取锁: {self.lock_path}"
                        ) from None
                    time.sleep(self.poll)
        except BaseException:
            if file is not None:
                file.close()
            self._thread_lock.release()
            raise

    def release(self) -> None:
        if not self._depth:
            return
        owners = _held.owners
        file, depth = owners[self._key]
        try:
            if depth == 1:
                try:
                    file.seek(0)
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
                finally:
                    try:
                        file.close()
                    finally:
                        del owners[self._key]
            else:
                owners[self._key] = (file, depth - 1)
        finally:
            self._depth -= 1
            self._thread_lock.release()

    @contextmanager
    def __call__(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


@contextmanager
def lock_path(path: Path, timeout: float = 10.0) -> Iterator[None]:
    with FileLock(path, timeout=timeout)():
        yield
