"""StepRunner — 单步 LLM 调用的通用执行器。

职责：
1. 从 StepSpec 读取 best_of_n / hardlint profile / max_tokens 等配置
2. 渲染 Jinja2 prompt
3. 循环 best_of_n 次调用 LLM
4. 用 HardLintEngine + Judge 选优
5. 返回 StepResult（含选中文本、call_records、diff_report）
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2

from novelwb.adapters.llm.base import LLMAdapter
from novelwb.core.prompt_registry import PromptRegistry
from novelwb.core.schemas.domain_models import Candidate, LLMCallRecord
from novelwb.engine.hard_lint import HardLintEngine, LintContext
from novelwb.engine.judge import Judge
from novelwb.utils.hashing import stable_hash
from novelwb.utils.ids import new_candidate_id, new_step_id
from novelwb.utils.logger import get_logger

_logger = get_logger(__name__)


class PipelineCancelled(RuntimeError):
    """Cooperative cancellation raised at a StepRunner boundary."""


# ── 结果 ──────────────────────────────────────────────────────────────────


@dataclass
class StepResult:
    step_id: str
    step_key: str
    text: str  # 选中候选的原始文本
    parsed: Any  # json.loads(text)，解析失败时为 None
    call_records: list[LLMCallRecord]  # 全部 best_of_n 次调用记录
    candidates: list[Candidate]  # 排序后全部候选
    lint_passed: bool  # 选中候选是否通过 HardLint
    violations: list[str] = field(default_factory=list)
    ok: bool = True  # 是否拿到通过解析与步骤结构校验的响应


# ── 依赖容器 ──────────────────────────────────────────────────────────────


@dataclass
class GraphDeps:
    """图执行所需的全部外部依赖（注入式，方便测试替换）。"""

    llm: LLMAdapter
    prompt_registry: PromptRegistry
    prompts_dir: Path  # src/novelwb/prompts/
    step_specs: dict[str, Any]  # step_key -> stepspec dict
    lint_engine: HardLintEngine = field(default_factory=HardLintEngine)
    judge: Judge = field(default_factory=Judge)
    # 可选的细粒度进度回调；设置后每个 step 的开始/完成都会上报（含产物预览）。
    # 由 Orchestrator 在流式运行前后 set/reset，便于 SSE 展示"每一步生成的东西"。
    progress: Callable[[dict[str, Any]], None] | None = None
    progress_context: ContextVar[Callable[[dict[str, Any]], None] | None] = field(
        default_factory=lambda: ContextVar("run_progress", default=None)
    )


# ── StepRunner ────────────────────────────────────────────────────────────


class StepRunner:
    """执行单个 step 的 LLM 调用 + HardLint + Judge 选优。"""

    # 当某次调用返回空内容时，额外追加的最多重试次数（在 best_of_n 之外）。
    # 用于兜住 DeepSeek 等模型偶发的空 content 响应。
    _EMPTY_RETRY_LIMIT = 3

    # 全局 max_tokens 下限：所有步骤的 max_tokens 都抬到至少这个值。
    # 注意：max_tokens 只是输出长度上限，不是质量旋钮——模型写完即停，调高不会让它多写/多想
    # （实测 max_tokens=200000 时模型仍只输出它需要的长度）。它唯一作用是防截断。
    # 32000 已远超任何步骤实际用量（含正文写作），再高纯属无用余量。
    _STEP_RETRY_LIMITS = {
        "graph4.event.blocks.write": 1,
        # Graph 2 produces large structured planning files.  One structural
        # retry is enough; combining the old three retries with adapter-level
        # retries could multiply an expensive request many times.
        "graph2.longline.core": 1,
        "graph2.story.field": 1,
        "graph2.map.room": 1,
        # Graph 3 files are expensive long-context structured outputs. Allow
        # one structural retry, not the generic three extra attempts.
        "graph3.volume.plan": 1,
        "graph3.volume.story_room": 1,
        "graph3.volume.map_room": 1,
        "graph3.volume.map_schedule": 1,
        "graph3.volume.event_designs": 1,
        "graph3.volume.fatigue_report": 1,
        # ObservedDelta is commit-critical and structurally deep. Retry one
        # schema-invalid candidate, while bounding the cost of the larger
        # output budget used by this step.
        "graphE.event.extract": 1,
        "graphE.event.reconcile": 1,
        "graphE.event.fix": 1,
    }

    # 临时：全局关闭 best-of（所有步骤只生成一次），用于快速、低成本地调试质量。
    # 以后想恢复按 StepSpec 的 best_of_n 取候选，把这里改回 False 即可。

    def __init__(self, deps: GraphDeps) -> None:
        self._deps = deps
        self._jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(deps.prompts_dir)),
            autoescape=False,
            undefined=jinja2.Undefined,
        )
        self._jinja_env.filters["tojson"] = lambda v, **kw: json.dumps(v, ensure_ascii=False, **kw)

    def run(
        self,
        step_key: str,
        input_pack: dict[str, Any],
        lint_ctx: LintContext | None = None,
        run_id: str = "",
        extra_vars: dict[str, Any] | None = None,
        parsed_validator: Callable[[Any], bool] | None = None,
        llm_overrides: dict[str, Any] | None = None,
    ) -> StepResult:
        """执行一个 step，返回 StepResult。"""
        spec = self._deps.step_specs.get(step_key)
        if spec is None:
            raise KeyError(f"StepSpec 未找到: {step_key!r}")

        llm_cfg = {
            **spec.get("llm", {}),
            **(llm_overrides or {}),
        }
        prompt_key: str = llm_cfg.get("prompt_key", step_key)
        best_of_n: int = max(1, llm_cfg.get("best_of_n", 1))
        max_tokens: int = llm_cfg.get("max_tokens", 2048)
        temperature: float = llm_cfg.get("temperature", 0.7)
        model: str | None = llm_cfg.get("model")
        thinking: str | None = llm_cfg.get("thinking")

        # 临时：全局关闭 best-of，所有步骤只生成一次
        complexity_level = self._complexity_level(input_pack)
        if complexity_level == "low":
            best_of_n = 1
        elif complexity_level == "medium":
            best_of_n = min(best_of_n, 2)

        # 全局抬高 max_tokens 上限，避免推理吃光额度导致 content 截断/为空
        reasoning_effort: str | None = llm_cfg.get("reasoning_effort")
        response_format = llm_cfg.get("response_format")

        # ── 获取 prompt 元数据 ────────────────────────────────────
        prompt_meta = self._deps.prompt_registry.get(prompt_key)
        if prompt_meta is None:
            raise KeyError(f"prompt_key 未注册: {prompt_key!r}")
        prompt_version: str = prompt_meta.get("prompt_version", "1.0")
        prompt_path: str = prompt_meta.get("path", "")

        # ── 渲染 Jinja2 ──────────────────────────────────────────
        template_path = f"{prompt_path}/prompt.jinja2"
        rendered = self._render(template_path, input_pack, run_id, extra_vars or {})
        prompt_hash = stable_hash(rendered)[:16]

        step_id = new_step_id()

        self._emit(
            {
                "event": "step",
                "phase": "start",
                "step_key": step_key,
                "step_id": step_id,
                "best_of_n": best_of_n,
            }
        )

        # ── best-of-n 调用（空响应/无效 JSON/结构不完整自动重试）─────
        candidates: list[Candidate] = []
        usable: list[Candidate] = []
        raw_wrapped_ids: set[str] = set()
        saw_nonempty = False
        saw_structurally_invalid = False
        call_records: list[LLMCallRecord] = []
        requires_json = self._requires_json_response(response_format)

        retry_limit = self._STEP_RETRY_LIMITS.get(step_key, self._EMPTY_RETRY_LIMIT)
        max_attempts = best_of_n + retry_limit
        attempt = 0
        retry_feedback = ""
        while attempt < max_attempts:
            attempt += 1
            self._emit(
                {
                    "event": "step",
                    "phase": "attempt",
                    "step_key": step_key,
                    "step_id": step_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                }
            )
            attempt_prompt = rendered
            if attempt > 1:
                # A structurally invalid response may already be in the LLM
                # cache.  A distinct, actionable retry prompt both avoids
                # replaying that bad cache entry and tells the model what to
                # correct.
                attempt_prompt = (
                    f"{rendered}\n\n"
                    "## 上一次输出未通过结构校验\n\n"
                    f"校验结果：{retry_feedback or '输出不是本步骤要求的完整结构'}\n"
                    "请根据以上错误重新生成一份完整输出，不要只返回补丁或解释。\n"
                    f"重试标识：{step_id}-{attempt}"
                )
            attempt_prompt_hash = stable_hash(attempt_prompt)[:16]
            resp = self._deps.llm.call(
                attempt_prompt,
                step_id=step_id,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                prompt_hash=attempt_prompt_hash,
                max_tokens=max_tokens,
                temperature=temperature,
                model=model,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                response_format=response_format,
            )
            call_records.append(resp.record)
            text = resp.text or ""
            saw_nonempty = saw_nonempty or bool(text.strip())
            # Candidate.content 是 dict；先尝试解析，失败则包装
            parsed_content, parsed_ok = self._extract_json(text)
            if requires_json and not isinstance(parsed_content, (dict, list)):
                parsed_ok = False
            candidate_id = new_candidate_id()
            if not isinstance(parsed_content, dict):
                parsed_content = {"_raw": text}
                raw_wrapped_ids.add(candidate_id)
            cand = Candidate(
                candidate_id=candidate_id,
                step_id=step_id,
                rank=attempt,
                content=parsed_content,
                selected=False,
            )
            candidates.append(cand)
            structure_ok = True
            structure_error = ""
            if text.strip() and parsed_ok and parsed_validator is not None:
                try:
                    structure_ok = bool(parsed_validator(parsed_content))
                except Exception as exc:
                    structure_ok = False
                    structure_error = str(exc).strip()
                saw_structurally_invalid = saw_structurally_invalid or not structure_ok
            if text.strip() and (not requires_json or parsed_ok) and structure_ok:
                usable.append(cand)
            if len(usable) >= best_of_n:
                break  # 已凑够 best_of_n 个有效候选
            if attempt >= best_of_n and usable:
                break  # 调用够 best_of_n 次且至少有一个有效候选，不再浪费额度
            if text.strip() == "":
                retry_feedback = "模型返回了空内容"
                _logger.warning(
                    f"step_empty_response step={step_key} attempt={attempt}/{max_attempts}"
                )
            elif requires_json and not parsed_ok:
                retry_feedback = "模型返回的内容不是可解析的完整 JSON"
                _logger.warning(
                    f"step_invalid_json_response step={step_key} attempt={attempt}/{max_attempts}"
                )
            elif not structure_ok:
                retry_feedback = structure_error or "JSON 字段、类型或必填值不符合本步骤契约"
                _logger.warning(
                    f"step_invalid_structure step={step_key} attempt={attempt}/{max_attempts}: "
                    f"{retry_feedback[:1000]}"
                )

        # ── Judge 选优（只在有效候选里选；全无效则降级）──────────────
        ok = bool(usable)
        pool = usable or candidates
        judge_result = self._deps.judge.evaluate(pool, lint_ctx_template=lint_ctx)
        selected = judge_result.selected

        # content 是 dict；恢复为 JSON 字符串供下游解析
        import json as _json

        content_dict = selected.content if isinstance(selected.content, dict) else {}
        if selected.candidate_id in raw_wrapped_ids:
            raw_text = str(content_dict.get("_raw", ""))
            parsed = self._try_parse(raw_text)
        else:
            raw_text = _json.dumps(content_dict, ensure_ascii=False)
            parsed = content_dict

        # 选中候选是否通过 HardLint
        selected_report = judge_result.lint_reports.get(selected.candidate_id, {})
        lint_passed = selected_report.get("passed", True)
        violations = selected_report.get("violated_forbidden", [])

        if not ok:
            reason = (
                "invalid_structure"
                if saw_structurally_invalid
                else "invalid_json"
                if saw_nonempty
                else "empty"
            )
            _logger.error(
                f"step_no_usable_response step={step_key} attempts={attempt} "
                f"reason={reason} — 重试后仍无可用候选"
            )
        _logger.info(
            f"step_runner_done step={step_key} attempts={attempt} ok={ok} "
            f"lint={lint_passed} v={len(violations)}"
        )

        invalid_json = bool(
            requires_json and saw_nonempty and not ok and not saw_structurally_invalid
        )
        invalid_structure = bool(saw_structurally_invalid and not ok)
        self._emit(
            {
                "event": "step",
                "phase": "done",
                "step_key": step_key,
                "step_id": step_id,
                "best_of_n": best_of_n,
                "prompt_key": prompt_key,
                "prompt_version": prompt_version,
                "prompt_hash": prompt_hash,
                "complexity_level": complexity_level,
                "max_tokens": max_tokens,
                "request_preview": rendered[:4000],
                "attempts": attempt,
                "ok": ok,
                "empty": not saw_nonempty,
                "invalid_json": invalid_json,
                "invalid_structure": invalid_structure,
                "validation_error": retry_feedback if not ok else "",
                "lint_passed": bool(lint_passed),
                "violations": len(violations),
                "input_tokens": sum(record.input_tokens for record in call_records),
                "output_tokens": sum(record.output_tokens for record in call_records),
                "latency_ms": sum(record.latency_ms for record in call_records),
                "preview": (
                    "（结构不完整：模型返回了合法 JSON，但未通过该步骤的字段或引用校验，"
                    "已重试仍失败）"
                    if invalid_structure
                    else "（无有效 JSON：模型返回了非空文本，但无法解析为合法 JSON，已重试仍失败）"
                    if invalid_json
                    else "（空响应：模型返回为空，已重试仍失败）"
                    if not ok
                    else self._preview(step_key, parsed, raw_text)
                ),
            }
        )

        return StepResult(
            step_id=step_id,
            step_key=step_key,
            text=raw_text,
            parsed=parsed,
            call_records=call_records,
            candidates=judge_result.candidates,
            lint_passed=lint_passed,
            violations=violations,
            ok=ok,
        )

    # ── 内部方法 ──────────────────────────────────────────────────

    def _emit(self, payload: dict[str, Any]) -> None:
        """若设置了进度回调，则上报一条事件（失败不影响主流程）。"""
        sink = self._deps.progress_context.get() or self._deps.progress
        if sink is None:
            return
        cancel_event = getattr(sink, "cancel_event", None)
        if cancel_event is not None and cancel_event.is_set():
            raise PipelineCancelled("run cancelled by user")
        try:
            sink(payload)
        except PipelineCancelled:
            raise
        except Exception:  # pragma: no cover - 进度上报不得影响生成
            pass

    @staticmethod
    def _preview(step_key: str, parsed: Any, raw_text: str, limit: int = 1400) -> str:
        """生成该步产物的可读预览（截断），供 UI 展示。"""
        text = ""
        if isinstance(parsed, dict):
            # 正文写作步：优先展示成稿正文
            if "full_text" in parsed and parsed["full_text"]:
                text = str(parsed["full_text"])
            elif "blocks_text" in parsed and isinstance(parsed["blocks_text"], list):
                text = "\n\n".join(
                    str(b.get("text", "")) for b in parsed["blocks_text"] if isinstance(b, dict)
                )
            else:
                try:
                    text = json.dumps(parsed, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    text = str(parsed)
        elif parsed is not None:
            text = str(parsed)
        else:
            text = raw_text or ""

        text = text.strip()
        if len(text) > limit:
            text = text[:limit] + f"\n…（已截断，共约 {len(text)} 字）"
        return text

    @staticmethod
    def _complexity_level(input_pack: dict[str, Any]) -> str:
        profile = input_pack.get("complexity_profile")
        if not isinstance(profile, dict):
            for key in ("spec00_content", "bible_content"):
                container = input_pack.get(key)
                if not isinstance(container, dict):
                    continue
                profile = container.get("complexity_profile")
                if not isinstance(profile, dict):
                    profile = (
                        container.get("_artifacts", {}).get("spec00", {}).get("complexity_profile")
                    )
                if isinstance(profile, dict):
                    break
        level = (
            str(profile.get("level", "medium")).lower() if isinstance(profile, dict) else "medium"
        )
        return level if level in {"low", "medium", "high"} else "medium"

    def _render(
        self, template_path: str, input_pack: dict[str, Any], run_id: str, extra: dict[str, Any]
    ) -> str:
        try:
            tmpl = self._jinja_env.get_template(template_path)
            return tmpl.render(input_pack=input_pack, run_id=run_id, **extra)
        except jinja2.TemplateNotFound:
            # fallback：直接把 input_pack 序列化为 prompt
            return json.dumps({"input_pack": input_pack, "run_id": run_id}, ensure_ascii=False)

    @staticmethod
    def _try_parse(text: str) -> Any:
        """尝试从文本中提取第一个合法 JSON 对象/数组。"""
        parsed, ok = StepRunner._extract_json(text)
        return parsed if ok else None

    @staticmethod
    def _extract_json(text: str) -> tuple[Any, bool]:
        """从文本中提取第一个合法 JSON 值，允许前后有说明文字或代码围栏。"""
        text = (text or "").strip()
        if not text:
            return None, False

        parsed, ok = StepRunner._decode_json_fragment(text)
        if ok:
            return parsed, True

        if "```" in text:
            parts = text.split("```")
            for block in parts[1::2]:
                block = block.strip()
                if block.lower().startswith("json"):
                    block = "\n".join(block.splitlines()[1:]).strip()
                parsed, ok = StepRunner._decode_json_fragment(block)
                if ok:
                    return parsed, True

        return None, False

    @staticmethod
    def _decode_json_fragment(text: str) -> tuple[Any, bool]:
        text = text.strip()
        try:
            return json.loads(text), True
        except (json.JSONDecodeError, ValueError):
            pass

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch not in "{[":
                continue
            try:
                parsed, _end = decoder.raw_decode(text[idx:])
                return parsed, True
            except json.JSONDecodeError:
                continue
        return None, False

    @staticmethod
    def _requires_json_response(response_format: str | dict[str, Any] | None) -> bool:
        if response_format is None:
            return False
        if isinstance(response_format, str):
            return "json" in response_format.lower()
        if isinstance(response_format, dict):
            return "json" in str(response_format.get("type", "")).lower()
        return False
