"""Failure, concurrent approval and path-boundary regression contracts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys

import pytest

from novelwb.core.constants import AuthObjectType, ChapterIntent, StagingType
from novelwb.core.schemas.domain_models import (
    AuthObject, ChapterSpec, ContextPackage, DiffReport, EventDraft, FatigueReport,
    ObservedDelta, StateSnapshot,
)
from novelwb.core.schemas.patch_models import VerifyResult
from novelwb.storage import AuthStore, WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.transactions import project_guard
from novelwb.utils.timeutil import utcnow
from tests.test_pipeline import _make_orchestrator


def _object(value=0):
    return AuthObject(object_id="spec00", project_id="test_proj", object_type=AuthObjectType.BIBLE,
        content={"value": value}, created_at=utcnow(), updated_at=utcnow(), committed_by_run_id="audit")


def test_concurrent_authority_versions_are_unique(tmp_layout):
    store = AuthStore(tmp_layout)
    store.commit(_object())
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda index: store.commit(_object(index)).version, range(8)))
    assert sorted(versions) == list(range(2, 10))
    assert store.load_artifact("spec00").version == 9
    assert store.load_latest("BIBLE").version == 9


def test_authority_commit_rolls_back_all_pointers_and_history(tmp_layout, monkeypatch):
    import novelwb.storage.auth_store as module
    store = AuthStore(tmp_layout)
    store.commit(_object())
    original = module.atomic_write_json
    def fail_last(path, data):
        if path == tmp_layout.auth_artifact_latest_path("spec00"):
            raise OSError("injected write failure")
        original(path, data)
    monkeypatch.setattr(module, "atomic_write_json", fail_last)
    with pytest.raises(OSError):
        store.commit(_object(2))
    assert store.load_latest("BIBLE").version == 1
    assert store.load_artifact("spec00").version == 1
    assert len(store.load_history("BIBLE")) == 1


def test_expected_version_is_checked_inside_transaction(tmp_layout):
    store = AuthStore(tmp_layout)
    store.commit(_object())
    store.commit(_object(2), expected_version=1)
    with pytest.raises(ValueError, match="版本冲突"):
        store.commit(_object(3), expected_version=1)
    assert store.load_artifact("spec00").content == {"value": 2}


def test_crashed_process_recovery_releases_lock_and_restores_data(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "authority.json"
    atomic_write_json(target, {"value": "old"})
    source = Path(__file__).resolve().parents[1] / "src"
    code = '''
import os,sys
from pathlib import Path
from novelwb.utils.transactions import transaction
from novelwb.utils.io_atomic import atomic_write_json
root=Path(sys.argv[1])
with transaction(root):
    atomic_write_json(root/'authority.json', {'value':'half-written'})
    atomic_write_json(root/'new.json', {'value':'new'})
    os._exit(73)
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(root)],
        env={**os.environ, "PYTHONPATH": str(source)}, timeout=20)
    assert result.returncode == 73
    with project_guard(root):
        assert read_json(target) == {"value": "old"}
        assert not (root / "new.json").exists()


@pytest.mark.parametrize("name", ["..", ".", "a/b", "a\\b", "C:outside", "NUL", "CON.txt", "a.", "a\x00b"])
def test_project_ids_cannot_escape_workspace(tmp_path, name):
    with pytest.raises(ValueError):
        WorkspaceLayout(tmp_path, name)
    assert not list(tmp_path.iterdir())


def test_read_only_layout_never_creates_unknown_project(tmp_path):
    with pytest.raises(FileNotFoundError):
        WorkspaceLayout(tmp_path, "missing", create=False)
    assert not list(tmp_path.iterdir())


def _chapter_review(orch):
    now = utcnow()
    orch._auth_store.commit(AuthObject(object_id="ledger", project_id="test_proj",
        object_type=AuthObjectType.LEDGER, content={"momentum_debt":0}, created_at=now,
        updated_at=now, committed_by_run_id="audit"))
    draft = EventDraft(event_id="evt_probe", run_id="audit", draft_text="审核测试正文", word_count=6)
    context = ContextPackage(context_id="ctx_probe",event_id="evt_probe",focus="audit",
        token_budget=120000, fingerprint="a"*64)
    pre = StateSnapshot(snapshot_key="snap_pre",event_id="evt_probe",context_fingerprint=context.fingerprint)
    delta = ObservedDelta(state_after=StateSnapshot(snapshot_key="snap_post",event_id="evt_probe",
        context_fingerprint=context.fingerprint),result_state_summary="audit",momentum_debt_delta=1)
    spec = ChapterSpec(chapter_id="chp_probe",chapter_index=1,chapter_intent=ChapterIntent.ADVANCE)
    return orch._save_review_packet(run_id="audit",review_kind="chapter_plan",title="audit",
        staging_type=StagingType.STG_CHAPTER,
        editable={"chapter_specs":[spec.model_dump(mode="json")],"chapter_texts":{"chp_probe":draft.draft_text}},
        internal={"draft":draft.model_dump(mode="json"),"context_package":context.model_dump(mode="json"),
            "pre_snapshot":pre.model_dump(mode="json"),"observed_delta":delta.model_dump(mode="json"),
            "diff_report":DiffReport(event_id="evt_probe",run_id="audit",passed=True).model_dump(mode="json"),
            "review_result":VerifyResult(staging_id="probe",passed=True,checked_at=now).model_dump(mode="json"),
            "fatigue_report":FatigueReport(report_id="probe",project_id="test_proj",generated_at=now).model_dump(mode="json")})


def test_repeated_and_concurrent_approval_applies_delta_once(tmp_path):
    orch = _make_orchestrator(tmp_path)
    packet = _chapter_review(orch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: orch.approve_workflow_review(packet.staging_id, {}), range(2)))
    assert results[0] == results[1]
    assert orch._auth_store.load_latest("LEDGER").content["momentum_debt"] == 1
    assert len(orch._events_store.list_index()) == len(orch._publish_store.list_index()) == 1
    assert orch.run_regression()["report"].event_count == 1


def test_publication_failure_preserves_review_and_rolls_back_event(tmp_path, monkeypatch):
    orch = _make_orchestrator(tmp_path)
    packet = _chapter_review(orch)
    original = orch._graph_5.commit_reviewed
    def fail(**kwargs):
        raise OSError("publication failed")
    monkeypatch.setattr(orch._graph_5, "commit_reviewed", fail)
    with pytest.raises(OSError):
        orch.approve_workflow_review(packet.staging_id, {})
    assert not orch._events_store.list_index()
    assert orch._snapshots_store.load_latest() is None
    assert orch._auth_store.load_latest("LEDGER").content["momentum_debt"] == 0
    assert orch._staging_store.load(packet.staging_id).content["status"] == "pending"
    monkeypatch.setattr(orch._graph_5, "commit_reviewed", original)
    assert orch.approve_workflow_review(packet.staging_id, {})["approved"]


def test_latest_bundle_does_not_rescan_history(tmp_layout, monkeypatch):
    store = AuthStore(tmp_layout)
    store.commit(_object())
    store.load_bundle()
    def no_history(*args):
        raise AssertionError("hot read scanned history")
    monkeypatch.setattr(store, "load_history", no_history)
    assert store.load_bundle()[0].object_id == "spec00"


def test_progress_callbacks_are_isolated_between_threads(tmp_path):
    import threading
    from novelwb.engine.step_runner import StepRunner
    orch = _make_orchestrator(tmp_path)
    barrier = threading.Barrier(2)
    calls = {"first": [], "second": []}
    def run(name):
        with orch._progress_sink(calls[name].append):
            barrier.wait(timeout=5)
            StepRunner(orch._deps)._emit({"event": "step", "owner": name})
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, calls))
    assert [row["owner"] for row in calls["first"]] == ["first"]
    assert [row["owner"] for row in calls["second"]] == ["second"]
    assert orch._deps.progress_context.get() is None


def test_workspace_validator_checks_without_creating_projects(tmp_path):
    from novelwb.core.validators.validate_workspace_layout import validate_workspace_layout
    assert validate_workspace_layout(tmp_path, "missing")
    assert validate_workspace_layout(tmp_path, "..")
    assert list(tmp_path.iterdir()) == []


def test_graph_s_commits_authority_and_staging_as_one_transaction(tmp_path, monkeypatch):
    from novelwb.core.schemas.patch_models import StagingPacket
    from novelwb.engine.graphs import GraphSInput
    orch = _make_orchestrator(tmp_path)
    packet = StagingPacket(staging_id="stg_auth", run_id="audit", staging_type=StagingType.STG_AUTH_PATCH,
        content={"object_id":"spec00","project_id":"test_proj","object_type":"BIBLE","content":{"value":1}},
        created_at=utcnow())
    orch._staging_store.save(packet)
    original = orch._graph_s._staging_store.delete
    def fail(staging_id):
        raise OSError("failed to finalize staging")
    monkeypatch.setattr(orch._graph_s._staging_store, "delete", fail)
    with pytest.raises(OSError):
        orch._graph_s.run(GraphSInput(run_id="audit", staging_packet=packet))
    assert orch._auth_store.load_artifact("spec00") is None
    assert orch._staging_store.load_optional("stg_auth") is not None
    monkeypatch.setattr(orch._graph_s._staging_store, "delete", original)
    assert orch._graph_s.run(GraphSInput(run_id="audit", staging_packet=packet)).aborted is False
    assert orch._auth_store.load_artifact("spec00").content == {"value":1}
    assert orch._staging_store.load_optional("stg_auth") is None
    next_packet = packet.model_copy(update={"staging_id": "stg_auth_next"})
    orch._staging_store.save(next_packet)
    result = orch._graph_s.run(GraphSInput(run_id="audit", staging_packet=next_packet))
    assert result.committed_object.version == 2
    assert result.commit_receipt.new_versions == {"BIBLE": 2}


def test_rollback_restores_history_after_append_then_delete(tmp_path):
    from novelwb.utils.io_atomic import atomic_delete
    from novelwb.utils.jsonl import append_jsonl, read_jsonl_all
    from novelwb.utils.transactions import transaction
    path = tmp_path / "history.jsonl"
    append_jsonl(path, {"version":1})
    with pytest.raises(OSError):
        with transaction(tmp_path):
            append_jsonl(path, {"version":2})
            atomic_delete(path)
            raise OSError("failed transaction")
    assert read_jsonl_all(path) == [{"version":1}]


def test_same_lock_instance_can_be_nested_and_fully_released(tmp_path):
    from novelwb.utils.file_locks import FileLock
    lock = FileLock(tmp_path / "nested", timeout=0.1)
    with lock():
        with lock():
            assert lock._depth == 2
        assert lock._depth == 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        def acquire_again():
            with FileLock(tmp_path / "nested", timeout=0.1)():
                return "released"
        assert pool.submit(acquire_again).result(timeout=2) == "released"
