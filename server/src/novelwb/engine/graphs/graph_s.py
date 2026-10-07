"""图S — 权威提交流程（Auth Commit）。

步骤：
  S1. authVerify  — 验证暂存区 StagingPacket
  S2. authCommit  — ATOMIC COMMIT（或 ROLLBACK）
"""

from __future__ import annotations

from dataclasses import dataclass

from novelwb.core.schemas.domain_models import AuthObject
from novelwb.core.schemas.patch_models import CommitReceipt, StagingPacket, VerifyResult
from novelwb.engine.step_runner import GraphDeps, StepRunner
from novelwb.storage import AuthStore, StagingStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow
from novelwb.utils.transactions import atomic_method

_logger = get_logger(__name__)


@dataclass
class GraphSInput:
    run_id: str
    staging_packet: StagingPacket
    expected_object_type: str | None = None


@dataclass
class GraphSOutput:
    verify_result: VerifyResult
    commit_receipt: CommitReceipt
    committed_object: AuthObject | None = None
    aborted: bool = False


class GraphS:
    """权威提交图执行器。"""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._layout = layout
        self._runner = StepRunner(deps)
        self._auth_store = AuthStore(layout)
        self._staging_store = StagingStore(layout)

    @atomic_method
    def run(self, inp: GraphSInput) -> GraphSOutput:
        run_id = inp.run_id
        packet = inp.staging_packet

        # ── S1: Auth Verify ─────────────────────────────────────
        verify_result = self._run_verify(run_id, packet)

        if not verify_result.passed:
            _logger.warning(f"graphS_verify_failed staging={packet.staging_id}")
            receipt = CommitReceipt(
                receipt_id=f"rcpt_fail_{packet.staging_id}",
                run_id=run_id,
                staging_id=packet.staging_id,
                commit_type="auth_patch",
                committed_at=utcnow(),
                committed_objects=[],
            )
            return GraphSOutput(
                verify_result=verify_result,
                commit_receipt=receipt,
                aborted=True,
            )

        # ── S2: Auth Commit ──────────────────────────────────────
        auth_obj, receipt = self._run_commit(run_id, packet)
        _logger.info(f"graphS_committed staging={packet.staging_id}")
        return GraphSOutput(
            verify_result=verify_result,
            commit_receipt=receipt,
            committed_object=auth_obj,
        )

    def _run_verify(self, run_id: str, packet: StagingPacket) -> VerifyResult:
        result = self._runner.run(
            step_key="graphS.auth.verify",
            input_pack={
                "run_id": run_id,
                "staging_id": packet.staging_id,
                "staging_type": packet.staging_type,
                "content": packet.content,
            },
            run_id=run_id,
        )
        now = utcnow()
        if result.parsed and isinstance(result.parsed, dict):
            try:
                return VerifyResult.model_validate(
                    {
                        "staging_id": packet.staging_id,
                        "checked_at": now,
                        **result.parsed,
                    }
                )
            except Exception:
                pass
        return VerifyResult(
            staging_id=packet.staging_id,
            passed=result.lint_passed,
            violations=result.violations,
            checked_at=now,
        )

    def _run_commit(self, run_id: str, packet: StagingPacket) -> tuple[AuthObject, CommitReceipt]:
        self._runner.run(
            step_key="graphS.auth.commit",
            input_pack={
                "run_id": run_id,
                "staging_id": packet.staging_id,
                "content": packet.content,
            },
            run_id=run_id,
        )
        content_dict = packet.content if isinstance(packet.content, dict) else {}
        now = utcnow()
        auth_obj = AuthObject(
            object_id=content_dict.get("object_id", f"auth_{packet.staging_id}"),
            project_id=content_dict.get("project_id", self._layout.project_id),
            object_type=content_dict.get("object_type", "BIBLE"),
            content=content_dict.get("content", content_dict),
            created_at=now,
            updated_at=now,
            committed_by_run_id=run_id,
        )
        auth_obj = self._auth_store.commit(auth_obj)
        self._staging_store.delete(packet.staging_id)
        receipt = CommitReceipt(
            receipt_id=f"rcpt_{packet.staging_id}",
            run_id=run_id,
            staging_id=packet.staging_id,
            commit_type="auth_patch",
            committed_at=now,
            committed_objects=[auth_obj.object_id],
            new_versions={auth_obj.object_type.value: auth_obj.version},
        )
        return auth_obj, receipt
