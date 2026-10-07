"""Persistence for derived context packages and the rebuildable card index."""

from __future__ import annotations

from novelwb.core.constants import CardPatchOperation
from novelwb.core.schemas.domain_models import (
    ContextPackage,
    ObservedDelta,
    SourceRef,
    StatusCard,
    StatusCardIndex,
)
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.transactions import guarded_store


@guarded_store
class ContextStore:
    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    def save_package(self, package: ContextPackage) -> None:
        path = self._layout.context_package_path(package.event_id)
        with lock_path(path):
            atomic_write_json(path, package.model_dump(mode="json"))

    def load_package(self, event_id: str) -> ContextPackage | None:
        data = read_json(self._layout.context_package_path(event_id))
        return ContextPackage.model_validate(data) if data else None

    def load_card_index(self) -> StatusCardIndex:
        data = read_json(self._layout.status_card_index_path)
        return StatusCardIndex.model_validate(data) if data else StatusCardIndex()

    def seed_authority_cards(self, cards: list[StatusCard], run_id: str) -> StatusCardIndex:
        """Replace untouched bootstrap cards while preserving event-derived state."""
        current = self.load_card_index()
        event_cards = {
            card.card_id: card for card in current.cards if card.last_touched_event_id is not None
        }
        projected = {card.card_id: card for card in cards}
        projected.update(event_cards)
        updated = StatusCardIndex(
            index_version=current.index_version + 1,
            cards=sorted(projected.values(), key=lambda card: (card.card_type.value, card.card_id)),
            updated_by_event_id=f"init:{run_id}",
        )
        path = self._layout.status_card_index_path
        with lock_path(path):
            atomic_write_json(path, updated.model_dump(mode="json"))
        return updated

    def apply_event_delta(self, delta: ObservedDelta, event_id: str) -> StatusCardIndex:
        current = self.load_card_index()
        cards: dict[str, StatusCard] = {card.card_id: card for card in current.cards}

        # state_after is a scoped projection: merge touched cards but never delete absent cards.
        for group_cards in delta.state_after.status_cards.values():
            for card in group_cards:
                existing = cards.get(card.card_id)
                source_version = max(
                    card.source_version, existing.source_version if existing else 1
                )
                cards[card.card_id] = self._stamp_card(card, event_id, source_version)

        for patches in delta.card_updates.values():
            for patch in patches:
                if patch.operation == CardPatchOperation.RETIRE:
                    cards.pop(patch.card_id, None)
                    continue
                if patch.card is not None:
                    existing = cards.get(patch.card_id)
                    existing_version = existing.source_version if existing else 0
                    source_version = max(
                        patch.new_version or 0,
                        patch.card.source_version,
                        existing_version + 1,
                    )
                    cards[patch.card_id] = self._stamp_card(
                        patch.card,
                        event_id,
                        source_version,
                    )

        updated = StatusCardIndex(
            index_version=current.index_version + 1,
            cards=sorted(cards.values(), key=lambda card: (card.card_type.value, card.card_id)),
            updated_by_event_id=event_id,
        )
        path = self._layout.status_card_index_path
        with lock_path(path):
            atomic_write_json(path, updated.model_dump(mode="json"))
        return updated

    @staticmethod
    def _stamp_card(card: StatusCard, event_id: str, source_version: int) -> StatusCard:
        refs = list(card.source_refs)
        if not any(ref.event_id == event_id for ref in refs):
            refs.append(
                SourceRef(
                    authority="EVENT",
                    event_id=event_id,
                    path="observed_delta.card_updates",
                    evidence="已提交事件中的正文证据和状态对账结果",
                )
            )
        return card.model_copy(
            update={
                "source_refs": refs,
                "last_touched_event_id": event_id,
                "source_version": max(1, source_version),
            }
        )
