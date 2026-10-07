"""Generate a current, inspectable index of every registered prompt contract."""

from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "server" / "src" / "novelwb" / "core"
PROMPTS = ROOT / "server" / "src" / "novelwb" / "prompts"
OUTPUT = ROOT / "PROMPTS_REVIEW.md"


def _spec_version() -> str:
    first_line = (ROOT / "SPEC_v1.md").read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"SPEC\s+(v[^\s]+)", first_line)
    if not match:
        raise ValueError("无法从 SPEC_v1.md 首行解析规范版本")
    return match.group(1)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _list_text(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(str(value) for value in values)


def generate() -> str:
    catalog = _load_yaml(CORE / "step_catalog.yaml").get("steps", [])
    registry_items = _load_yaml(PROMPTS / "registry.yaml").get("prompts", [])
    registry = {item["prompt_key"]: item for item in registry_items}

    rows: list[dict] = []
    for entry in catalog:
        step_key = entry["key"]
        spec_path = CORE / "step_specs" / f"{step_key}.yaml"
        spec = _load_yaml(spec_path) if spec_path.exists() else {
            "step_key": step_key,
            "graph": entry.get("graph"),
            "description": entry.get("description"),
            "input_schema": "未实现",
            "output_schema": "未实现",
            "commit_type": "none",
        }
        llm = spec.get("llm") or {}
        prompt_key = llm.get("prompt_key")
        registered = registry.get(prompt_key, {})
        prompt_dir = PROMPTS / str(registered.get("path", "")) if registered else None
        prompt_meta = _load_yaml(prompt_dir / "prompt.yaml") if prompt_dir else {}
        template = (
            (prompt_dir / "prompt.jinja2").read_text(encoding="utf-8").rstrip()
            if prompt_dir else ""
        )
        rows.append({
            "catalog": entry,
            "spec": spec,
            "llm": llm,
            "registry": registered,
            "meta": prompt_meta,
            "template": template,
        })

    lines = [
        "# Prompt Review Index",
        "",
        "由 `scripts/generate_prompts_review.py` 从 StepSpec、提示词注册表、`prompt.yaml` 与 `prompt.jinja2` 生成。",
        f"当前目录步骤数：{len(rows)}；已注册提示词数：{len(registry_items)}。规范版本：`{_spec_version()}`。",
        "",
        "## 运行时上下文契约",
        "",
        "- Graph1 的八个作品基座文件必须逐一生成与审核；后一步只能读取人工修改并批准后的前序权威版本。",
        "- Graph2/Graph3 先构建全书与卷 StoryRoom；逐事件设计显式引用人物、地点、场景、伏笔、故事线、议程、物品与大场面资产。",
        "- 图3按逐事件ID确定性解析 `reading_assets`；图4启动前由 `ContextCompiler` 选择本事件需要的权威片段和状态卡，不接收全量故事室或整卷事件槽。",
        "- 图4按最新状态从 `plot/character/relationship/faction/item/ecology/mystery/set_piece/aftermath/ensemble` 中选择2–6条路线，再执行世界脉冲、多轮展开、场景编织与写前检查。",
        "- 状态卡分为 `plot/character/scene/faction/item/rule`，是可重建阅读投影，不是权威真值。",
        "- `context_meta` 携带焦点、来源版本、选中/省略原因、token预算和指纹；图4与图E沿用同一指纹。",
        "- 人物知识使用 `character_knowledge`，揭秘条件使用 `revelation_gate`；无正文证据的 `CardPatch` 不得提交。",
        "- 正文结构有效后执行确定性质量评分；低于72分才追加候选，最多3次，提升低于2分提前停止并保留最佳有效稿。",
        "",
        "## 汇总",
        "",
        "| 图 | Step | Prompt | 版本 | 输入 Schema | 输出 Schema | 变量 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        entry, spec, meta = row["catalog"], row["spec"], row["meta"]
        lines.append(
            "| {graph} | `{step}` | `{prompt}` | {version} | `{input_schema}` | "
            "`{output_schema}` | {variables} |".format(
                graph=_cell(entry.get("graph")),
                step=_cell(entry.get("key")),
                prompt=_cell(meta.get("prompt_key") or "预留/未实现"),
                version=_cell(meta.get("version") or "-") ,
                input_schema=_cell(spec.get("input_schema")),
                output_schema=_cell(spec.get("output_schema")),
                variables=_cell(_list_text(meta.get("variables")) or "input_pack"),
            )
        )

    lines.extend(["", "## 完整提示词", ""])
    for row in rows:
        entry = row["catalog"]
        spec = row["spec"]
        llm = row["llm"]
        registered = row["registry"]
        meta = row["meta"]
        if not meta:
            lines.extend([
                f"### `{entry['key']}`",
                "",
                f"- 说明：{spec.get('description', entry.get('description', ''))}",
                "- 状态：预留步骤，当前规范明确跳过，尚无 StepSpec、注册提示词和运行实现。",
                "",
            ])
            continue
        lines.extend([
            f"### `{entry['key']}`",
            "",
            f"- 说明：{spec.get('description', entry.get('description', ''))}",
            f"- Prompt：`{meta.get('prompt_key')}` v{meta.get('version')}",
            f"- 模板：`server/src/novelwb/prompts/{registered.get('path')}/prompt.jinja2`",
            f"- 输入：`{spec.get('input_schema')}`；变量：{_list_text(meta.get('variables')) or '`input_pack`'}",
            f"- 输出：`{spec.get('output_schema')}`；格式：`{meta.get('output_format', llm.get('response_format', 'text'))}`",
            f"- 提交：`{spec.get('commit_type')}`；HardLint：`{_list_text((spec.get('hardlint') or {}).get('enabled_rule_groups'))}`",
            f"- 模型：`{llm.get('model')}`；temperature={llm.get('temperature')}；max_tokens={llm.get('max_tokens')}；best_of_n={llm.get('best_of_n')}",
            "",
            "```jinja2",
            row["template"],
            "```",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(generate(), encoding="utf-8")
    print(f"wrote {OUTPUT}")
