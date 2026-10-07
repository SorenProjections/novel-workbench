"""MaterialsStore — 素材卡库读写。

存储格式：
  materials/{material_id}.json — 单个 MaterialCard
"""

from __future__ import annotations

from novelwb.core.constants import MaterialCardType
from novelwb.core.schemas.domain_models import MaterialCard
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json


class MaterialsStore:
    """管理 materials/ 目录下的 MaterialCard JSON 文件。"""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def save(self, card: MaterialCard) -> None:
        path = self._layout.material_path(card.material_id)
        with lock_path(path):
            atomic_write_json(path, card.model_dump(mode="json"))

    # ── 读取 ────────────────────────────────────────────────────

    def load(self, material_id: str) -> MaterialCard:
        path = self._layout.material_path(material_id)
        data = read_json(path)
        return MaterialCard.model_validate(data)

    def exists(self, material_id: str) -> bool:
        return self._layout.material_path(material_id).exists()

    def load_optional(self, material_id: str) -> MaterialCard | None:
        if not self.exists(material_id):
            return None
        return self.load(material_id)

    # ── 批量读取 ─────────────────────────────────────────────────

    def list_all(self) -> list[MaterialCard]:
        """返回全部素材卡（按 material_id 字典序）。"""
        cards: list[MaterialCard] = []
        for p in sorted(self._layout.materials_dir.glob("*.json")):
            data = read_json(p)
            cards.append(MaterialCard.model_validate(data))
        return cards

    def list_by_type(self, card_type: MaterialCardType) -> list[MaterialCard]:
        return [c for c in self.list_all() if c.card_type == card_type]

    # ── 删除 ────────────────────────────────────────────────────

    def delete(self, material_id: str) -> None:
        path = self._layout.material_path(material_id)
        path.unlink(missing_ok=True)
