"""Bounded background jobs with durable state, event replay and cancellation."""

from __future__ import annotations

import builtins
import json
import os
import sys
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from novelwb.engine.step_runner import PipelineCancelled
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.file_locks import lock_path
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.jsonl import append_jsonl

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            # Access denied means a live process that we cannot inspect.
            return ctypes.get_last_error() == 5
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            return bool(kernel.WaitForSingleObject(handle, 0) == 258)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class TaskService:
    def __init__(self, *, workers: int = 4, max_pending: int = 32) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="novelwb")
        self._capacity = threading.BoundedSemaphore(max_pending)
        self._session = uuid4().hex
        self._condition = threading.Condition()
        self._closed = False
        self._futures: dict[Future[None], tuple[WorkspaceLayout, str]] = {}

    @property
    def closed(self) -> bool:
        return self._closed

    @staticmethod
    def _directory(layout: WorkspaceLayout) -> Path:
        path = (layout.runs_dir / "tasks").resolve()
        if not path.is_relative_to(layout.project_dir):
            raise ValueError("任务目录不能越出项目目录")
        return path

    def _path(self, layout: WorkspaceLayout, run_id: str) -> Path:
        layout.validate_id(run_id)
        path = (self._directory(layout) / f"{run_id}.json").resolve()
        if path.parent != self._directory(layout):
            raise ValueError("任务路径非法")
        return path

    @contextmanager
    def _guard(self, layout: WorkspaceLayout) -> Iterator[None]:
        with lock_path(self._directory(layout) / ".tasks"):
            yield

    def get(self, layout: WorkspaceLayout, run_id: str) -> dict[str, Any]:
        layout.validate_id(run_id)
        # A missing lookup must not create task directories. Resolve the state
        # file only under the guard: Windows realpath briefly opens a handle
        # that can prevent a concurrent atomic replacement.
        if not (self._directory(layout) / f"{run_id}.json").exists():
            raise FileNotFoundError("运行不存在")
        with self._guard(layout):
            path = self._path(layout, run_id)
            state = read_json(path)
            if state is None:
                raise FileNotFoundError("运行不存在")
            if not isinstance(state, dict):
                raise ValueError("运行状态文件损坏")
            if state["status"] not in TERMINAL and (
                not _alive(int(state["owner_pid"]))
                or (state["owner_pid"] == os.getpid() and state["session"] != self._session)
            ):
                state["status"] = "interrupted"
                state["message"] = "后端进程已结束；已批准断点保留，可重新生成未完成文件"
                atomic_write_json(path, state)
            return state

    def list(self, layout: WorkspaceLayout) -> list[dict[str, Any]]:
        return [
            self.get(layout, path.stem)
            for path in sorted(self._directory(layout).glob("*.json"), reverse=True)
            if not path.stem.startswith(".")
        ]

    def start(
        self,
        layout: WorkspaceLayout,
        run_id: str,
        kind: str,
        params: dict[str, Any],
        work: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]],
    ) -> dict[str, Any]:
        layout.validate_id(run_id)
        with self._guard(layout):
            path = self._path(layout, run_id)
            if path.exists():
                existing = self.get(layout, run_id)
                if existing["kind"] != kind or existing["params"] != params:
                    raise ValueError("运行 ID 已用于另一组参数")
                return existing
            if any(state["status"] not in TERMINAL for state in self.list(layout)):
                raise ValueError("项目已有运行任务，请等待完成或取消当前任务")
            if self._closed:
                raise ValueError("任务服务正在关闭")
            if not self._capacity.acquire(blocking=False):
                raise ValueError("任务队列已满，请稍后重试")
            state = {
                "run_id": run_id,
                "project_id": layout.project_id,
                "kind": kind,
                "params": params,
                "status": "queued",
                "cancel_requested": False,
                "owner_pid": os.getpid(),
                "session": self._session,
                "sequence": 0,
                "started_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "message": "任务已排队",
            }
            try:
                atomic_write_json(path, state)
                future = self._executor.submit(self._run, layout, run_id, work)
                with self._condition:
                    self._futures[future] = (layout, run_id)
                future.add_done_callback(self._finished)
                if self._closed:
                    future.cancel()
            except BaseException:
                self._capacity.release()
                if path.exists():
                    state["status"] = "failed"
                    state["message"] = "无法提交后台任务"
                    atomic_write_json(path, state)
                raise
            return state

    def emit(self, layout: WorkspaceLayout, run_id: str, payload: dict[str, Any]) -> None:
        with self._guard(layout):
            path = self._path(layout, run_id)
            state = read_json(path)
            state["sequence"] += 1
            entry = {**payload, "run_id": run_id, "sequence": state["sequence"]}
            # Events precede the cursor so reconnect cannot miss a published event.
            append_jsonl(path.with_suffix(".events.jsonl"), entry)
            state["updated_at"] = datetime.now(UTC).isoformat()
            state["message"] = (
                payload.get("title") or payload.get("message") or payload.get("event")
            )
            if payload.get("event") == "step" and payload.get("phase") == "done":
                for key in ("input_tokens", "output_tokens", "latency_ms"):
                    state[key] += int(payload.get(key) or 0)
            if payload.get("event") in {"result", "error", "cancelled"}:
                state["status"] = {
                    "result": "completed",
                    "error": "failed",
                    "cancelled": "cancelled",
                }[payload["event"]]
                state["result"] = payload
            atomic_write_json(path, state)
        with self._condition:
            self._condition.notify_all()

    def _run(self, layout: WorkspaceLayout, run_id: str, work: Callable[..., Any]) -> None:
        def progress(payload: dict[str, Any]) -> None:
            if self.get(layout, run_id)["cancel_requested"]:
                raise PipelineCancelled("run cancelled by user")
            self.emit(layout, run_id, payload)

        try:
            with self._guard(layout):
                path = self._path(layout, run_id)
                state = read_json(path)
                state["status"] = "running"
                atomic_write_json(path, state)
            progress({"event": "graph_start", "title": "正在执行生成任务"})
            result = work(progress)
            # Completed files are persisted checkpoints; cancellation never erases them.
            if self.get(layout, run_id)["cancel_requested"]:
                self.emit(
                    layout,
                    run_id,
                    {"event": "cancelled", "message": "运行已取消，已保存的断点保留"},
                )
            elif result.get("success") is False or (
                isinstance(result.get("result"), dict) and result["result"].get("success") is False
            ):
                self.emit(
                    layout,
                    run_id,
                    {
                        "event": "error",
                        "message": result.get("abort_reason")
                        or result.get("result", {}).get("abort_reason", "生成失败"),
                        "result": result,
                    },
                )
            else:
                self.emit(layout, run_id, {"event": "result", **result})
        except PipelineCancelled:
            self.emit(
                layout, run_id, {"event": "cancelled", "message": "运行已取消，已保存的断点保留"}
            )
        except Exception as exc:
            self.emit(layout, run_id, {"event": "error", "message": str(exc)})
        finally:
            self._capacity.release()

    def cancel(self, layout: WorkspaceLayout, run_id: str) -> dict[str, Any]:
        self.get(layout, run_id)
        with self._guard(layout):
            state = self.get(layout, run_id)
            finished = state["status"] in TERMINAL
            if not finished:
                state["cancel_requested"] = True
                atomic_write_json(self._path(layout, run_id), state)
            return {
                "run_id": run_id,
                "cancel_requested": not finished,
                "already_finished": finished,
            }

    @staticmethod
    def _read_events(path: Path, offset: int) -> tuple[builtins.list[dict[str, Any]], int]:
        rows: list[dict[str, Any]] = []
        if not path.exists():
            return rows, offset
        with path.open("rb") as file:
            file.seek(offset)
            for _ in range(512):
                start = file.tell()
                line = file.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    # A process may have exited during the final append.
                    file.seek(start)
                    break
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("进度记录必须是 JSON 对象")
                rows.append(row)
            return rows, file.tell()

    def events(self, layout: WorkspaceLayout, run_id: str, after: int = 0) -> Iterator[str]:
        self.get(layout, run_id)
        with self._guard(layout):
            path = self._path(layout, run_id)
        cursor, offset = max(0, after), 0
        while True:
            state = self.get(layout, run_id)
            with self._guard(layout):
                rows, offset = self._read_events(path.with_suffix(".events.jsonl"), offset)
            for row in rows:
                if row["sequence"] > cursor:
                    cursor = row["sequence"]
                    yield (
                        f"id: {cursor}\nevent: {row['event']}\ndata: "
                        f"{json.dumps(row, ensure_ascii=False)}\n\n"
                    )
            if len(rows) == 512:
                continue
            if state["status"] in TERMINAL and cursor >= state["sequence"]:
                if state["status"] == "interrupted":
                    yield (
                        f"event: error\ndata: "
                        f"{json.dumps({'message': state['message']}, ensure_ascii=False)}\n\n"
                    )
                return
            with self._condition:
                notified = self._condition.wait(timeout=2)
            if not notified:
                yield 'event: heartbeat\ndata: {"message":"等待当前步骤"}\n\n'

    def _finished(self, future: Future[None]) -> None:
        with self._condition:
            task = self._futures.pop(future, None)
        if future.cancelled() and task is not None:
            layout, run_id = task
            try:
                self.emit(layout, run_id, {"event": "cancelled", "message": "排队任务已取消"})
            finally:
                self._capacity.release()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            futures = tuple(self._futures)
        # Cancel outside the executor's shutdown lock: callbacks persist task state
        # while a concurrent submission may still hold its project task lock.
        self._executor.shutdown(wait=False)
        for future in futures:
            future.cancel()


tasks = TaskService()
