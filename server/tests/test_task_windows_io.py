"""Reproduce Windows path-resolution handles overlapping task state writes."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

import pytest

from novelwb.engine.task_service import TaskService
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing semantics")
@pytest.mark.parametrize("operation", ["get", "start", "events"])
def test_state_reader_does_not_block_atomic_state_replacement(tmp_path, monkeypatch, operation):
    import ctypes
    from ctypes import wintypes

    layout = WorkspaceLayout(tmp_path, "project")
    service = TaskService(workers=1)
    path = layout.runs_dir / "tasks" / "run.json"
    atomic_write_json(path, {"status": "completed", "sequence": 0, "kind": "workflow", "params": {}})
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    opened, release = threading.Event(), threading.Event()
    resolve = Path.resolve
    reader_id = None

    def slow_resolve(self, *args, **kwargs):
        result = resolve(self, *args, **kwargs)
        if self == path and threading.get_ident() == reader_id:
            # Model the zero-sharing handle used by CPython's Windows realpath.
            # Keep it open long enough to make the concurrency failure reproducible.
            handle = kernel.CreateFileW(str(path), 0, 0, None, 3, 0x02000000, None)
            assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
            try:
                opened.set()
                assert release.wait(10)
            finally:
                kernel.CloseHandle(handle)
        return result

    def read():
        nonlocal reader_id
        reader_id = threading.get_ident()
        if operation == "start":
            return service.start(layout, "run", "workflow", {}, lambda progress: {})
        if operation == "events":
            return list(service.events(layout, "run"))
        return service.get(layout, "run")

    monkeypatch.setattr(Path, "resolve", slow_resolve)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(read)
            try:
                assert opened.wait(10)
                writing = pool.submit(service.emit, layout, "run", {"event": "heartbeat"})
                try:
                    writing.result(timeout=0.2)
                except TimeoutError:
                    pass
            finally:
                release.set()
            reading.result(timeout=10)
            writing.result(timeout=10)
        assert service.get(layout, "run")["sequence"] == 1
    finally:
        release.set()
        service.close()
