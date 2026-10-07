"""ID 生成工具 — 统一前缀 + UUID4 短 ID。"""

from __future__ import annotations

import uuid


def _short_uuid() -> str:
    return uuid.uuid4().hex[:12]


def new_run_id() -> str:
    return f"run_{_short_uuid()}"


def new_step_id() -> str:
    return f"step_{_short_uuid()}"


def new_candidate_id() -> str:
    return f"cand_{_short_uuid()}"


def new_event_id() -> str:
    return f"evt_{_short_uuid()}"


def new_chapter_id() -> str:
    return f"ch_{_short_uuid()}"


def new_staging_id() -> str:
    return f"stg_{_short_uuid()}"


def new_receipt_id() -> str:
    return f"rcpt_{_short_uuid()}"


def new_rollback_id() -> str:
    return f"rbk_{_short_uuid()}"


def new_snapshot_key() -> str:
    return f"snap_{_short_uuid()}"


def new_material_id() -> str:
    return f"mat_{_short_uuid()}"


def new_call_id() -> str:
    return f"call_{_short_uuid()}"


def new_report_id() -> str:
    return f"rpt_{_short_uuid()}"
