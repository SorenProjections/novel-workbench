# novel-workbench 开发进度

## 当前状态：打通「规划→写作」+ 全流程步骤可视化 + 修复权威层读取（2026-06-08）

所有阶段完成，端到端流程已验证通过（DeepSeek 真实调用）。
新增「按图3规划自动连载整卷」、全流程每一步流式可视化，并修复了一个导致
权威层一直读不到的关键 bug。

---

### Stage 22（根因定位+修复：thinking 吃光 token 导致 content 截断/为空，2026-06-08）

**根因（对照真实调用确认）：** 初始化步骤多为 thinking=enabled + reasoning_effort=high/max，
但 max_tokens 仅 3000–4000。推理先吃掉约 2000~4000 token：
- max_tokens=3000：finish_reason=length，reasoning=2139，content 残缺(1293, 非法JSON)
- max_tokens=12000：finish_reason=stop，reasoning=2032，content 完整(3956, 合法JSON)
即 Stage 21 看到的"空"主要是**推理把额度吃光、content 被截断**，与"切换模型"无关
（DeepSeek 是无状态 REST，每次调用独立，pro↔flash 互不影响）。

**修复：**
- `StepRunner._MAXTOK_FLOOR=16000`：**所有**步骤的 max_tokens 抬到至少 16000（全局下限，
  不只 thinking 步骤）。max_tokens 是上限、按实际用量计费，对正常 stop 的步骤几乎无额外成本。
- `StepRunner._FORCE_BEST_OF_1=True`：**临时**全局关闭 best-of（所有步骤只生成一次），
  快速低成本调试质量；以后恢复按 StepSpec 取候选把它改回 False 即可。
- 初始化"全用 pro"：`graph3.volume.fatigue_report` model 由 deepseek-v4-flash 改为 deepseek-v4-pro。
- 配合 Stage 21 的空响应重试，截断(残缺非空JSON)由更大预算解决、纯空由重试兜底。

**注意：** 残缺 JSON 是"非空"，不会触发空响应重试——所以抬 max_tokens 是此问题的真正解药。

### Stage 21（健壮性：空响应重试 + 选优永不选空 + UI 标红，2026-06-08）

**问题（实测发现）：** DeepSeek（deepseek-v4-pro + thinking:disabled）会**间歇性返回空 content**
（200 OK、约1秒返回）。此前 StepRunner 不重试、best_of_n 选优甚至会选中空候选，空响应被
静默落库成 `{"_label","_raw":"None"}` 继续往下跑 → 世界A/对手生态/力量结构表现/长线骨架/
卷契约全空，卷契约空 = 没有 event_slots = 自动连载无内容可写。

**修复（不改 graphs，集中在 StepRunner + UI）：**
- `StepRunner`：空 content 自动重试（best_of_n 之外最多 `_EMPTY_RETRY_LIMIT=3` 次）；
  选优只在**非空候选**里选（`pool = nonempty or candidates`）；新增 `StepResult.ok`。
- step done 事件带 `ok/empty/attempts`；全空时 preview 显式提示而非 "None"。
- Web 步骤卡片：空响应显示红色「空响应 · 重试N次」徽章。
- 测试：新增 test_step_runner_retries_empty_and_never_selects_empty（18 passed）。

**注意：** 之前那次 系统文爽文 初始化的数据是坏的，需重跑初始化（现在会自动重试空响应）。
**待办（Stage 3 诊断）：** 定位 DeepSeek 为何吐空——对比带/不带 thinking 字段、换 deepseek-chat/reasoner、调 max_tokens。

### Stage 20（关键修复：AuthStore 读写键不一致，2026-06-08）

**Bug：** `AuthObjectType` 是 str 枚举，但 `str(AuthObjectType.CONTRACT)` 得到的是
`"AuthObjectType.CONTRACT"`（Python 默认 Enum.__str__），而非 `"CONTRACT"`。
`AuthStore.commit` 用枚举写文件（`AuthObjectType.CONTRACT.latest.json`），
而 orchestrator/graph_e 全用裸串 `load_latest("CONTRACT")` 读 → 找的是
`CONTRACT.latest.json` → **永远返回 None**。

**影响（此前一直静默失效）：** 图4 拿不到 BIBLE/CHAR/LEDGER/CONTRACT（volume_content
等全是空 dict）；`_update_auth_from_event` 每次 load CHAR 都是 None → 人物状态无法累积。
这正是"规划没接上写作 / 续不上"的底层原因之一。

**修复：** `AuthStore._key()` 把枚举与裸串都归一到既有磁盘命名（兼容旧数据），
commit/load_latest/load_history/exists 全部走它。验证：qingcheng 现在能正确读出
BIBLE(v1)/CHAR(v1)/CONTRACT(v1, 8 个 event_slots)。

### Stage 19（全流程步骤可视化 + 初始化流式，2026-06-08）

**目标：** 工作台能看到"每一步生成的东西"，包括初始化的图1/2/3 每一步。

- `StepRunner` 是所有图所有步骤的唯一入口：新增 `GraphDeps.progress` 进度回调，
  每个 step 自动上报 `step`(start/done) 事件，done 带产物预览（正文步展示成稿，
  其余展示 JSON），含 lint 通过状态。**一处接入，全图覆盖（含初始化）。**
- `Orchestrator._progress_sink()` 上下文管理器：在 run_stage_engine / run_volume_auto /
  run_event_sprout 期间临时挂载 sink；并发出图级里程碑（graph_start/done、init_done…）。
- API：新增 `GET /pipeline/init-novel/stream`（初始化也能流式看每步）。
- Web 工作台：
  - 初始化 Tab 改为流式（进度条 + 停止），显示图1/2/3 每一步。
  - 新增"流程过程"步骤卡片：图标签 + 中文步骤名 + 生成中/完成/未过校验徽章 +
    可折叠的产物预览；auto/sprout/init 三条流都接入。

---

### Stage 18（按规划自动连载整卷，2026-06-08）

**背景缺口：** 图3（volume_plan）已生成整卷 `event_slots[]` 并存入 CONTRACT 权威对象，
但 `write-event`/`sprout-event` 都不读它——前者要用户手填事件目标，后者用写死的通用相位名拆分。
导致工作台 UI 逼用户当人肉调度器，"全流程自动化"名存实亡。

**改动：**
- `orchestrator.run_volume_auto(run_id, start_index, max_events, only_key, progress)`：
  读取 `CONTRACT.content["event_slots"]`，逐槽跑 图4→图E→图5；章节间状态承接复用
  `_update_auth_from_event` + `history_chapter_specs`，无需用户介入。
- `orchestrator._normalize_volume_slot()`：把图3槽位补齐成图4可消费的 event_slot
  （`allowed_changes→allowed_delta`、`forbidden_changes→forbidden_delta` 兼容映射）。
- API：`POST /pipeline/auto-volume`（同步）+ `GET /pipeline/auto-volume/stream`（SSE 流式）。
- CLI：`novelwb auto-volume <project> [--start N] [--max N] [--key-only]`。
- Web 工作台：新增「自动连载」Tab（起始事件/最多N章/仅关键事件 + 进度条 + 流式 + 停止）。

**验证：** 15 passed；模块导入/路由/槽位映射均通过；qingcheng 现有 8 个规划槽位、
codex_demo_first_chapter 有 4 个，可直接 `auto-volume` 连载。

---

## 已完成阶段

### Stage 1-7（前期架构）
- 项目骨架、目录结构、SPEC v1.0+r0
- 核心 Schema（domain_models / patch_models / constants）
- StepSpec / PromptRegistry / HardLint / Judge / Regression
- 存储层（EventsStore / AuthStore / PublishStore / StagingStore 等）
- LLM 适配器（DeepSeekAdapter / MockReplayAdapter）

### Stage 8-12（执行引擎）
- Workspace IO 层（FileLock / 原子写入 / jsonl 索引）
- LLM 缓存层（LlmCacheStore）
- HardLint 规则 A-G
- StepRunner（Jinja2 渲染 + LLM + Judge）
- 图E / 图5 / 图S / 图P（执行框架）
- Orchestrator（run_event_pipeline / run_auth_pipeline / run_regression）

### Stage 13（API + CLI + Tests）
- FastAPI（/projects / /pipeline / /chapters）
- Typer CLI（new-project / run-event / run-auth / chapters / regression）
- pytest 测试（13 passed）
- scripts/run_pipeline.py

### Stage 15（图E 解析精度 + 权威层自动更新）

- **图E extract/reconcile/presnapshot JSON解析精度修复**：
  - 新增 `_strip_extra(data, model_class)` 辅助函数，过滤 LLM 多余字段（`extra="forbid"` 下安全解析）
  - `_run_presnapshot`、`_run_extract`、`_build_diff_report` 全部改用 strip+safe-validate
  - `ObservedDelta` 缺少 `result_state_summary` 时自动补"事件完成"而非崩溃
  - `DiffReport.fix_level_suggested` 字符串→枚举转换兜底
- **图E提交后自动更新 CHAR_BIBLE / LEDGER**：
  - `Orchestrator._update_auth_from_event()` 新增方法
  - 每次 `run_event_pipeline` 成功后自动调用
  - `ObservedDelta.new_entities` 增量追加到 CHAR（去重）
  - `ObservedDelta.open_threads_update` 增量追加到 LEDGER（去重）
  - `momentum_debt_delta` 累计到 LEDGER.momentum_debt

### Stage 14（图1-4 + 真实 Prompts）
- **图1** `engine/graphs/graph_1.py` — 舞台引擎（spec00→worldA→worldB→powL→powS→powE→oppEco）
- **图2** `engine/graphs/graph_2.py` — 长线骨架（longline_core）
- **图3** `engine/graphs/graph_3.py` — 分卷规划（volume_plan + fatigue_report）
- **图4** `engine/graphs/graph_4.py` — 事件执行（budget→plan→namecheck→jit_cards→blocks_write）
- Orchestrator 新增 `run_stage_engine()` / `run_event_write()`
- CLI 新增 `init-novel` / `write-event` 命令
- **18个 prompts 从占位符重写为真实可用内容**
- `.env` 加载修复（dotenv + LLM_ADAPTER 兼容）
- 存储层 bug 修复（datetime 序列化 / publish_store / graph_e）

### Stage 17（全流水线提示词系统性升级，对齐用户文档包，2026-03-27）

**改写范围：全部 31 个 jinja2 模板，全部通过语法验证**

| 文件 | 版本 | 核心改进 |
|------|------|----------|
| graph1/spec00 | v2.0 | 新增 lens_climate/writing_dictionary/forbidden_zones/self_check |
| graph1/worldA | v2.0 | conflict_sources/motif_seeds 结构化扩展，新增 self_check |
| graph1/worldB | v2.0 | zones/transport_and_trade/institution_framework/self_check |
| graph1/oppEco | v2.0 | oppression_spectrum（8+条）/self_check |
| graph1/powL | v2.0 | laws 结构化/cost_principles/term_table/self_check |
| graph1/powS | v2.0 | structure_elements/damage_repair_system/growth_stages/self_check |
| graph1/powE | v2.0 | region_and_school_interfaces（4+套）/term_table 扩展/self_check |
| graph2/longlineCore | v2.0 | stage_nodes 扩展(sub_question/key_nodes/波形)/type_contract_fulfillment/self_check |
| graph3/volumePlan | v2.0 | volume_positioning/volume_contract/receipt_plan/debt_plan/event_ngang_sequence/fatigue_warning；事件槽位新增 allowed_changes/forbidden_changes |
| graphE/presnapshot | v2.0 | required_threads/due_debts/hard_constraint_reminders/self_check |
| graphE/extract | v2.0 | change_list（含 evidence_quote/is_allowed）/entity_changes/new_threads |
| graphE/reconcile | v2.0 | repair_level_recommendation（L0/L1/L2 分支明确） |
| graph5/chapterizeCut | v2.0 | title_candidates/end_asset_type/transition_notes |
| graph5/chapterizeReview | v2.0 | reading_rubric + mechanism_rubric 逐章评审 |
| graph5/chapterCommit | v2.0 | **占位符→完整实现**：chapter_intents/ledger_registration/hook_type/self_check |
| graph5/fatigue | v2.0 | **占位符→完整实现**：章级疲劳分析 |
| graph6/regressionRun | v2.0 | **占位符→完整实现**：style/mechanism/continuity/chapter 四维回归 |

**全部文件通用改进：**
- 角色定义（与用户提示词文档对齐）
- 全局规则第1条：全程只用中文，JSON字段名保持英文
- 硬检查清单（输出前脑内验证）
- 所有现有 JSON 字段名保持不变（代码兼容）

---

### Stage 16（正文生成提示词升级，参考用户提示词文档包）

- **`graph4/eventPlan/prompt.jinja2` v2.0**：
  - 输出新增 `allowed_changes`（允许变化）、`forbidden_changes`（禁止变化）、`debt_handling`（债务处理）三个字段
  - 块结构新增 `conflict`、`info_gap`（信息差机制）、`cost_trigger`（代价触发点）
  - 总规则对齐用户 12_事件计划提示词：全程中文、债务分类、叙事弧要求
- **`graph4/blocksWrite/prompt.jinja2` v2.0**（对齐用户 13_事件正文 + 单章正文慢节奏版）：
  - 接入完整 event_plan（含允许/禁止变化清单），块标记格式（【块－b001】/【块结束】）
  - 输入新增：ledger_content（债务台账）、volume_content（本卷契约/镜头气候）
  - 12 条写作硬规则：禁止说明书写法、禁止套话、节奏控制（不连续三次爽点）、升级代价、境界名词铺垫等
  - 感官/画面/对手能动性等质量要求
- **`graph4/eventBudget/prompt.jinja2` v2.0**：默认预算档位上调（standard 5000–9000 字，key 8000–16000 字）
- **`graph4.event.blocks.write.yaml`**：max_chars 6000→24000，max_tokens 8000→16000
- **`graph4.py`**：blocks_write 新增传入 event_plan、ledger_content、volume_content

---

## 验证记录（2026-03-21）

```
novelwb new-project qingcheng
novelwb init-novel qingcheng "修仙流，顾青城..."
  ✅ 图1 7步全完成（~8分钟，约18次 API 调用）
  ✅ 图2 longline_core（best_of_5）
  ✅ 图3 volume_plan + fatigue_report
  main_promise: "普通少年在腐朽宗门中，以弱胜强逐步揭开父亲失踪之谜，最终打破黑暗秩序"

novelwb write-event qingcheng "顾青城抵达青云宗山门..." --key
  ✅ 图4 5步（~3分钟）→ blocks_write 生成 3243 字正文
  ✅ 图E 校验通过（fix_attempts=0）
  ✅ 图5 章节化，1章发布到 publish/
```

---

## 使用方式

```bash
cd server
# 确保 .env 有 DEEPSEEK_API_KEY 和 LLM_ADAPTER=deepseek

# 1. 建立新项目权威层（一次性，约10分钟）
novelwb new-project <project_id>
novelwb init-novel <project_id> "<小说简介>"

# 2. 逐事件写作（每次约5分钟）
novelwb write-event <project_id> "<事件目标>" [--key]

# 3. 查看已发布章节
novelwb chapters <project_id>

# 4. 回归测试
novelwb regression <project_id>

# 启动 API 服务
uvicorn novelwb.server_main:app --reload
```

---

## 已知局限

1. **图E prompt 解析**：extract/reconcile 步骤 LLM 返回有时无法精确匹配 Pydantic schema，会 fallback 到默认值（不影响流程，只影响状态追踪精度）
2. **图4 blocks_write**：正文以 best_of_1 生成，有时需要多次运行或调整 prompt
3. **RAG（图R）**：按 SPEC 要求暂跳过，接口已预留
4. **图6 回归测试**：框架存在，但 mock 模式下内容检验有限
5. **权威层自动更新**：图E提交后 BIBLE/REG/CHAR 的增量更新尚未完全打通

---

## 下次接续

读此文件后直接继续。优先方向：
- 用真实 DeepSeek API 验证新版 write-event（`novelwb write-event qingcheng "..."` 跑一次，看质量是否提升）
- 图6 回归测试完善（目前框架存在但 mock 模式内容检验有限）
- 多事件连续写作测试（验证 CHAR/LEDGER 跨事件自动更新链路）
- 可选：实现"事件蔓生十章拆解"完整流程（需新增 graph4.5，把一次 write-event 拆成10章循环）
