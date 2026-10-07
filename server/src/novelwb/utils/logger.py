"""结构化日志 — JSON 格式，含 trace_id，自动脱敏。"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from novelwb.utils.redaction import redact_dict
from novelwb.utils.timeutil import utcnow_iso

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = os.environ.get("LOG_FORMAT", "json").lower()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "ts": utcnow_iso(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 附加 extra 字段
        for key, val in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
            ):
                log_data[key] = redact_dict(val)

        if record.exc_info:
            log_data["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, separators=(",", ":"))


def _setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    if _LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))


_setup_logging()


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。"""
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    event: str,
    level: str = "INFO",
    **kwargs: Any,
) -> None:
    """记录结构化事件日志（额外字段通过 kwargs 传入）。"""
    extra = {"event": event, **kwargs}
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(event, extra=extra)
