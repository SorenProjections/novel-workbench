"""StagingStore — 暂存区（STG_EVENT / STG_CHAPTER / STG_AUTH_PATCH）读写。"""

from __future__ import annotations

from novelwb.core.schemas.patch_models import StagingPacket
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_delete, atomic_write_json, read_json
from novelwb.utils.transactions import guarded_store


@guarded_store
class StagingStore:
    """管理 staging/ 目录下的 StagingPacket JSON 文件。

    一个 staging_id 对应一个文件，文件名为 {staging_id}.json。
    写入前加文件锁防止并发覆盖。
    """

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def save(self, packet: StagingPacket) -> None:
        path = self._layout.staging_packet_path(packet.staging_id)
        with lock_path(path):
            atomic_write_json(path, packet.model_dump(mode="json"))

    # ── 读取 ────────────────────────────────────────────────────

    def load(self, staging_id: str) -> StagingPacket:
        path = self._layout.staging_packet_path(staging_id)
        data = read_json(path)
        return StagingPacket.model_validate(data)

    def exists(self, staging_id: str) -> bool:
        return self._layout.staging_packet_path(staging_id).exists()

    def load_optional(self, staging_id: str) -> StagingPacket | None:
        if not self.exists(staging_id):
            return None
        return self.load(staging_id)

    # ── 删除（提交后清理） ───────────────────────────────────────

    def delete(self, staging_id: str) -> None:
        path = self._layout.staging_packet_path(staging_id)
        atomic_delete(path)

    # ── 列举 ────────────────────────────────────────────────────

    def list_all(self) -> list[StagingPacket]:
        """返回暂存区内所有包（按文件名排序）。"""
        packets: list[StagingPacket] = []
        for p in sorted(self._layout.staging_dir.glob("*.json")):
            data = read_json(p)
            packets.append(StagingPacket.model_validate(data))
        return packets
