"""Storage 层基本读写测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.storage.runs_store import RunsStore
from novelwb.storage.events_store import EventsStore
from novelwb.storage.staging_store import StagingStore
from novelwb.storage.auth_store import AuthStore
from novelwb.core.schemas.domain_models import (
    RunManifest,
    EventRecord,
    DiffReport,
    ObservedDelta,
    StateSnapshot,
    BlockSpec,
    AuthObject,
)
from novelwb.core.constants import AuthObjectType, CommitType, StagingType


def _now():
    return datetime.now(timezone.utc)


# ── RunsStore ──────────────────────────────────────────────────────────────


def test_runs_store_roundtrip(tmp_layout: WorkspaceLayout):
    store = RunsStore(tmp_layout)
    manifest = RunManifest(
        run_id="run-001",
        project_id="test_proj",
        step_key="event_draft",
        started_at=_now(),
        spec_hash="aaa",
        prompt_hash="bbb",
        schema_hash="ccc",
        stepspec_hash="ddd",
        llm_adapter="mock",
    )
    store.save(manifest)
    loaded = store.load("run-001")
    assert loaded.run_id == "run-001"
    assert loaded.step_key == "event_draft"


def test_runs_store_list_index(tmp_layout: WorkspaceLayout):
    store = RunsStore(tmp_layout)
    for i in range(3):
        m = RunManifest(
            run_id=f"run-{i:03d}",
            project_id="test_proj",
            step_key="s",
            started_at=_now(),
            spec_hash="x",
            prompt_hash="x",
            schema_hash="x",
            stepspec_hash="x",
            llm_adapter="mock",
        )
        store.save(m)
    index = store.list_index()
    assert len(index) == 3


# ── EventsStore ───────────────────────────────────────────────────────────


def _make_event_record(event_id: str, run_id: str) -> EventRecord:
    snap = StateSnapshot(snapshot_key=f"post_{event_id}")
    delta = ObservedDelta(
        state_after=snap,
        result_state_summary="ok",
    )
    diff = DiffReport(event_id=event_id, run_id=run_id, passed=True)
    return EventRecord(
        event_id=event_id,
        project_id="test_proj",
        draft_text="hello",
        state_before_key=f"pre_{event_id}",
        state_after_key=f"post_{event_id}",
        observed_delta=delta,
        diff_report=diff,
        committed_at=_now(),
        committed_by_run_id=run_id,
        ledger_version_after=1,
    )


def test_events_store_roundtrip(tmp_layout: WorkspaceLayout):
    store = EventsStore(tmp_layout)
    rec = _make_event_record("ev-001", "run-001")
    store.save(rec)
    loaded = store.load("ev-001")
    assert loaded.event_id == "ev-001"
    assert loaded.diff_report.passed is True


def test_events_store_list_by_run(tmp_layout: WorkspaceLayout):
    store = EventsStore(tmp_layout)
    store.save(_make_event_record("ev-001", "run-A"))
    store.save(_make_event_record("ev-002", "run-A"))
    store.save(_make_event_record("ev-003", "run-B"))
    by_a = store.list_by_run("run-A")
    assert len(by_a) == 2
    by_b = store.list_by_run("run-B")
    assert len(by_b) == 1


# ── StagingStore ──────────────────────────────────────────────────────────


def test_staging_store_roundtrip(tmp_layout: WorkspaceLayout):
    from novelwb.storage.staging_store import StagingStore
    from novelwb.core.schemas.patch_models import StagingPacket

    store = StagingStore(tmp_layout)
    packet = StagingPacket.model_construct(
        staging_id="stg-001",
        run_id="run-001",
        staging_type=StagingType.STG_EVENT,
        content={},
        created_at=_now(),
    )
    store.save(packet)
    loaded = store.load_optional("stg-001")
    assert loaded is not None
    assert loaded.staging_id == "stg-001"
    store.delete("stg-001")
    assert store.load_optional("stg-001") is None


def test_auth_store_keeps_multiple_logical_documents_per_type(tmp_layout: WorkspaceLayout):
    store = AuthStore(tmp_layout)
    for object_id in ("spec00", "world_a", "world_b"):
        store.commit(AuthObject(
            object_id=object_id,
            project_id="test_proj",
            object_type=AuthObjectType.BIBLE,
            version=1,
            content={"label": object_id},
            created_at=_now(),
            updated_at=_now(),
            committed_by_run_id="run-001",
        ))

    bundle = store.load_bundle({"BIBLE"})
    assert {item.object_id for item in bundle} == {"spec00", "world_a", "world_b"}
    assert store.load_artifact("world_a").content["label"] == "world_a"


def test_auth_store_versions_each_logical_document_independently(tmp_layout: WorkspaceLayout):
    store = AuthStore(tmp_layout)
    first = AuthObject(
        object_id="spec00",
        project_id="test_proj",
        object_type=AuthObjectType.BIBLE,
        version=1,
        content={"revision": 1},
        created_at=_now(),
        updated_at=_now(),
        committed_by_run_id="run-001",
    )
    store.commit(first)
    stored = store.commit(first.model_copy(update={
        "content": {"revision": 2},
        "committed_by_run_id": "run-002",
    }))

    assert stored.version == 2
    assert store.load_artifact("spec00").content == {"revision": 2}
