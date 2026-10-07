"""Deterministic context compiler for event-scoped LLM working sets.

The compiler never changes authority data. It projects a traceable, budgeted
working set from authority objects and the derived status-card index.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from novelwb.core.constants import ContextPriority, Defaults, StatusCardType
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ContextCardSelection,
    ContextOmission,
    ContextPackage,
    ContextSource,
    ReadingFocus,
    StateSnapshot,
    StatusCard,
    StatusCardIndex,
)

_PROTECTED_KEYS: dict[str, set[str]] = {
    "BIBLE": {
        "spec00",
        "rules",
        "world_rules",
        "hard_constraints",
        "forbidden_zones",
        "scale_budget",
        "type_contract",
        "lens",
        "taboo",
        "self_check",
    },
    "REG": {"terminology", "term_table", "rules", "interfaces"},
    "CHAR": {"current_state", "character_states", "reading_focus"},
    "LEDGER": {
        "open_threads",
        "debts",
        "due_debts",
        "momentum_debt",
        "breather_quota",
    },
    "CONTRACT": {
        "volume_id",
        "sub_question",
        "volume_promise",
        "volume_contract",
        "conflict_form_rotation",
        "breather_quota",
        "max_consecutive_breather",
        "momentum_debt_max",
        "promise_scenes",
        "motif_steps",
    },
    "MOTIF": {"active_motifs", "motif_steps"},
}

_CARD_GROUPS: dict[StatusCardType, str] = {
    StatusCardType.PLOT: "plot_cards",
    StatusCardType.CHARACTER: "character_cards",
    StatusCardType.SCENE: "scene_cards",
    StatusCardType.FACTION: "faction_cards",
    StatusCardType.ITEM: "item_cards",
    StatusCardType.RULE: "rule_cards",
}


class ContextCompiler:
    """Compile only the authority fragments and status cards an event needs."""

    def __init__(
        self,
        token_budget: int = Defaults.DEFAULT_CONTEXT_INPUT_TOKENS,
        cards_per_type: int = Defaults.DEFAULT_CONTEXT_CARDS_PER_TYPE,
    ) -> None:
        self._token_budget = max(1000, int(token_budget))
        self._cards_per_type = max(1, int(cards_per_type))

    def compile_event(
        self,
        *,
        event_id: str,
        event_slot: dict[str, Any],
        auth_objects: Iterable[AuthObject | None],
        card_index: StatusCardIndex | None = None,
        latest_snapshot: StateSnapshot | None = None,
    ) -> ContextPackage:
        auth_list = [obj for obj in auth_objects if obj is not None]
        focus = self._build_focus(event_slot)
        hints = self._focus_hints(event_slot)
        source_versions = {
            f"{obj.object_type.value}:{obj.object_id}": obj.version for obj in auth_list
        }

        task_source = self._make_source(
            authority="TASK",
            object_id=event_id,
            version=None,
            path="event_slot",
            reason="当前事件意图、允许变化与禁止变化是本次写作的绑定任务。",
            protected=True,
            payload=_compact_value(event_slot, max_chars=5000),
        )
        protected_sources = [task_source]
        candidate_sources: list[tuple[float, ContextSource]] = []
        omitted: list[ContextOmission] = []
        chapter_design = event_slot.get("chapter_design")
        has_reading_assets = isinstance(chapter_design, dict) and isinstance(
            chapter_design.get("reading_assets"), dict
        )

        for obj in auth_list:
            authority = obj.object_type.value
            content = obj.content if isinstance(obj.content, dict) else {}
            protected_keys = _PROTECTED_KEYS.get(authority, set())
            for key, value in content.items():
                source_id = f"{authority}.{obj.object_id}.{key}"
                if key == "event_slots":
                    omitted.append(
                        ContextOmission(
                            source_id=source_id,
                            reason="当前事件槽已作为受保护任务输入，省略整卷事件槽表以避免重复注入",
                        )
                    )
                    continue
                if key == "story_room" and has_reading_assets:
                    omitted.append(
                        ContextOmission(
                            source_id=source_id,
                            reason="当前事件已携带按ID解析的reading_assets，省略全书或全卷故事室",
                        )
                    )
                    continue
                protected = key in protected_keys or any(
                    marker in key.lower() for marker in protected_keys
                )
                score = self._relevance_score(source_id, value, focus, hints)
                source = self._make_source(
                    authority=authority,
                    object_id=obj.object_id,
                    version=obj.version,
                    path=key,
                    reason=(
                        "权威硬约束或当前状态，必须原样进入工作集。"
                        if protected
                        else "该权威片段与当前事件目标、实体或债务相关。"
                    ),
                    protected=protected,
                    payload=_compact_value(value, max_chars=2600 if protected else 1600),
                )
                if protected:
                    protected_sources.append(source)
                else:
                    candidate_sources.append((score, source))

        cards = self._collect_cards(auth_list, card_index, latest_snapshot)
        focus_ids = self._collect_focus_ids(auth_list, latest_snapshot)
        card_candidates: list[tuple[float, StatusCard]] = []
        for card in cards:
            score = self._relevance_score(card.card_id, card.model_dump(mode="json"), focus, hints)
            focus_lower = focus.lower()
            if card.card_name.lower() in focus_lower:
                score += 30.0
            if card.subject_id and card.subject_id.lower() in focus_lower:
                score += 20.0
            if card.card_id in focus_ids:
                score += 100.0
            if card.card_type in {StatusCardType.PLOT, StatusCardType.CHARACTER}:
                score += 0.5
            card_candidates.append((score, card))

        selected_sources: list[ContextSource] = []
        selected_cards: list[ContextCardSelection] = []
        used_tokens = sum(source.estimated_tokens for source in protected_sources)

        # Keep at least the best fragment from each logical authority document.
        best_by_authority: dict[str, tuple[float, ContextSource]] = {}
        for score, source in candidate_sources:
            anchor_key = f"{source.authority}:{source.object_id}"
            current = best_by_authority.get(anchor_key)
            if current is None or score > current[0]:
                best_by_authority[anchor_key] = (score, source)
        ordered_sources = sorted(
            candidate_sources,
            key=lambda item: (
                item[1].source_id not in {best[1].source_id for best in best_by_authority.values()},
                -item[0],
                item[1].source_id,
            ),
        )
        for score, source in ordered_sources:
            anchor_key = f"{source.authority}:{source.object_id}"
            is_authority_anchor = best_by_authority.get(anchor_key, (None, None))[1] == source
            if score <= 0 and not is_authority_anchor:
                omitted.append(
                    ContextOmission(source_id=source.source_id, reason="与当前事件无可验证关联")
                )
                continue
            if used_tokens + source.estimated_tokens > self._token_budget:
                omitted.append(ContextOmission(source_id=source.source_id, reason="超过上下文预算"))
                continue
            selected_sources.append(source)
            used_tokens += source.estimated_tokens

        selected_per_type: dict[StatusCardType, int] = defaultdict(int)
        ordered_cards = sorted(card_candidates, key=lambda item: (-item[0], item[1].card_id))
        has_positive_card = any(score > 0.5 for score, _ in ordered_cards)
        for score, card in ordered_cards:
            fallback_card = not has_positive_card and card.card_type in {
                StatusCardType.PLOT,
                StatusCardType.CHARACTER,
            }
            if score <= 0.5 and not fallback_card:
                omitted.append(
                    ContextOmission(source_id=card.card_id, reason="状态卡与当前事件无关")
                )
                continue
            if selected_per_type[card.card_type] >= self._cards_per_type:
                omitted.append(
                    ContextOmission(source_id=card.card_id, reason="同类状态卡数量超过上限")
                )
                continue
            card_tokens = _estimate_tokens(card.model_dump(mode="json"))
            if used_tokens + card_tokens > self._token_budget:
                omitted.append(ContextOmission(source_id=card.card_id, reason="超过上下文预算"))
                continue
            priority = (
                ContextPriority.HIGH
                if score >= 20
                else ContextPriority.MEDIUM
                if score >= 3
                else ContextPriority.LOW
            )
            selected_cards.append(
                ContextCardSelection(
                    card=card,
                    reason="既有阅读焦点指定"
                    if card.card_id in focus_ids
                    else "与事件目标、实体或债务语义相关",
                    priority=priority,
                    relevance_score=score,
                    estimated_tokens=card_tokens,
                )
            )
            selected_per_type[card.card_type] += 1
            used_tokens += card_tokens

        if used_tokens > self._token_budget:
            omitted.append(
                ContextOmission(
                    source_id="context_budget",
                    reason="受保护上下文本身超过预算；硬约束被保留，禁止静默截断",
                )
            )

        payload = {
            "context_id": f"ctx_{event_id}",
            "event_id": event_id,
            "focus": focus,
            "protected_sources": [item.model_dump(mode="json") for item in protected_sources],
            "selected_sources": [item.model_dump(mode="json") for item in selected_sources],
            "selected_cards": [item.model_dump(mode="json") for item in selected_cards],
            "omitted": [item.model_dump(mode="json") for item in omitted],
            "source_versions": source_versions,
            "token_budget": self._token_budget,
            "estimated_tokens": used_tokens,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return ContextPackage.model_validate({**payload, "fingerprint": fingerprint})

    @staticmethod
    def render_input_context(package: ContextPackage) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = defaultdict(dict)
        for source in [*package.protected_sources, *package.selected_sources]:
            if source.authority == "TASK":
                continue
            authority_group = grouped[source.authority]
            artifacts = authority_group.setdefault("_artifacts", {})
            artifacts.setdefault(source.object_id, {})[source.path] = source.payload
            # Preserve old prompt access for unique top-level keys.
            authority_group.setdefault(source.path, source.payload)

        status_cards: dict[str, list[dict[str, Any]]] = defaultdict(list)
        reading_focus: list[dict[str, Any]] = []
        for selection in package.selected_cards:
            card = selection.card
            status_cards[_CARD_GROUPS[card.card_type]].append(card.model_dump(mode="json"))
            reading_focus.append(
                ReadingFocus(
                    focus_id=f"focus_{card.card_id}",
                    card_id=card.card_id,
                    card_type=card.card_type,
                    why_needed=selection.reason,
                    priority=selection.priority,
                    source_refs=card.source_refs,
                ).model_dump(mode="json")
            )

        char_context = dict(grouped.get("CHAR", {}))
        char_context["reading_focus"] = reading_focus
        char_context["status_cards"] = dict(status_cards)
        return {
            "bible_content": dict(grouped.get("BIBLE", {})),
            "reg_content": dict(grouped.get("REG", {})),
            "char_content": char_context,
            "ledger_content": dict(grouped.get("LEDGER", {})),
            "volume_content": dict(grouped.get("CONTRACT", {})),
            "motif_content": dict(grouped.get("MOTIF", {})),
            "context_meta": {
                "context_id": package.context_id,
                "fingerprint": package.fingerprint,
                "focus": package.focus,
                "source_versions": package.source_versions,
                "token_budget": package.token_budget,
                "estimated_tokens": package.estimated_tokens,
                "selected_source_ids": [
                    source.source_id
                    for source in [*package.protected_sources, *package.selected_sources]
                ],
                "selected_card_ids": [
                    selection.card.card_id for selection in package.selected_cards
                ],
                "omitted": [item.model_dump(mode="json") for item in package.omitted],
            },
        }

    @staticmethod
    def _make_source(**kwargs: Any) -> ContextSource:
        payload = kwargs["payload"]
        return ContextSource(
            source_id=f"{kwargs['authority']}.{kwargs['object_id']}.{kwargs['path']}",
            estimated_tokens=_estimate_tokens(payload),
            **kwargs,
        )

    @staticmethod
    def _build_focus(event_slot: dict[str, Any]) -> str:
        fields = (
            "event_goal",
            "result_target",
            "conflict_form",
            "key_deliverables",
            "required_debts_handling",
            "allowed_delta",
            "forbidden_delta",
            "sprout",
        )
        parts = [event_slot.get(key) for key in fields if event_slot.get(key)]
        chapter_design = event_slot.get("chapter_design")
        if isinstance(chapter_design, dict):
            for key in (
                "chapter_center",
                "reader_payoff",
                "character_focus_ids",
                "location_ids",
                "scene_asset_ids",
                "foreshadowing_ids",
                "relationship_ids",
            ):
                if chapter_design.get(key):
                    parts.append(chapter_design[key])
        return " | ".join(_collect_strings(parts)) or str(event_slot.get("slot_id") or "未命名事件")

    @staticmethod
    def _focus_hints(event_slot: dict[str, Any]) -> set[str]:
        hints: set[str] = set()
        for text in _collect_strings(event_slot):
            for token in re.split(r"[\s，。！？；：、,.!?;:（）()\[\]{}]+", text):
                token = token.strip()
                if 2 <= len(token) <= 40:
                    hints.add(token.lower())
                    if _contains_cjk(token):
                        for size in (3, 4):
                            hints.update(
                                token[index : index + size].lower()
                                for index in range(len(token) - size + 1)
                            )
        return hints

    @staticmethod
    def _relevance_score(source_id: str, payload: Any, focus: str, hints: set[str]) -> float:
        haystack = f"{source_id}\n{json.dumps(payload, ensure_ascii=False, default=str)}".lower()
        focus_lower = focus.lower()
        score = 0.0
        if source_id.lower() in focus_lower:
            score += 20.0
        for value in _collect_strings(payload):
            candidate = value.strip().lower()
            if 2 <= len(candidate) <= 24 and candidate in focus_lower:
                score += 10.0
        for hint in hints:
            if hint in haystack:
                score += min(3.0, 0.4 + len(hint) / 8.0)
        return round(score, 3)

    @staticmethod
    def _collect_cards(
        auth_objects: list[AuthObject],
        card_index: StatusCardIndex | None,
        latest_snapshot: StateSnapshot | None,
    ) -> list[StatusCard]:
        by_id: dict[str, StatusCard] = {}
        if card_index:
            by_id.update({card.card_id: card for card in card_index.cards})
        if latest_snapshot:
            for cards in latest_snapshot.status_cards.values():
                for card in cards:
                    by_id[card.card_id] = card
        for obj in auth_objects:
            if obj.object_type.value != "CHAR" or not isinstance(obj.content, dict):
                continue
            groups = obj.content.get("status_cards")
            if not isinstance(groups, dict):
                current = obj.content.get("current_state")
                groups = current.get("status_cards") if isinstance(current, dict) else None
            if not isinstance(groups, dict):
                continue
            snapshot = StateSnapshot.model_validate(
                {"snapshot_key": "legacy_card_projection", "status_cards": groups}
            )
            for cards in snapshot.status_cards.values():
                for card in cards:
                    by_id.setdefault(card.card_id, card)
        return list(by_id.values())

    @staticmethod
    def _collect_focus_ids(
        auth_objects: list[AuthObject],
        latest_snapshot: StateSnapshot | None,
    ) -> set[str]:
        ids = {
            focus.card_id for focus in (latest_snapshot.reading_focus if latest_snapshot else [])
        }
        for obj in auth_objects:
            if obj.object_type.value != "CHAR" or not isinstance(obj.content, dict):
                continue
            raw = obj.content.get("reading_focus")
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, dict) and item.get("card_id"):
                    ids.add(str(item["card_id"]))
        return ids


def _collect_strings(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        if value.strip():
            result.append(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            result.extend(_collect_strings(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            result.extend(_collect_strings(item))
    return result


def _compact_value(value: Any, *, max_chars: int, depth: int = 0) -> Any:
    if depth > 5:
        return "[上下文层级过深，已省略]"
    if isinstance(value, str):
        return value if len(value) <= max_chars else f"{value[:max_chars]}…[已按预算截断]"
    if isinstance(value, dict):
        items = list(value.items())[:24]
        result = {
            str(key): _compact_value(item, max_chars=max(240, max_chars // 2), depth=depth + 1)
            for key, item in items
        }
        if len(value) > len(items):
            result["_omitted_keys"] = len(value) - len(items)
        return result
    if isinstance(value, (list, tuple)):
        items = list(value)[:16]
        compact_items = [
            _compact_value(item, max_chars=max(240, max_chars // 2), depth=depth + 1)
            for item in items
        ]
        if len(value) > len(items):
            compact_items.append({"_omitted_items": len(value) - len(items)})
        return compact_items
    return value


def _estimate_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars)


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
