# Prompt Review Index

由 `scripts/generate_prompts_review.py` 从 StepSpec、提示词注册表、`prompt.yaml` 与 `prompt.jinja2` 生成。
当前目录步骤数：41；已注册提示词数：40。规范版本：`v1.0+r7`。

## 运行时上下文契约

- Graph1 的八个作品基座文件必须逐一生成与审核；后一步只能读取人工修改并批准后的前序权威版本。
- Graph2/Graph3 先构建全书与卷 StoryRoom；逐事件设计显式引用人物、地点、场景、伏笔、故事线、议程、物品与大场面资产。
- 图3按逐事件ID确定性解析 `reading_assets`；图4启动前由 `ContextCompiler` 选择本事件需要的权威片段和状态卡，不接收全量故事室或整卷事件槽。
- 图4按最新状态从 `plot/character/relationship/faction/item/ecology/mystery/set_piece/aftermath/ensemble` 中选择2–6条路线，再执行世界脉冲、多轮展开、场景编织与写前检查。
- 状态卡分为 `plot/character/scene/faction/item/rule`，是可重建阅读投影，不是权威真值。
- `context_meta` 携带焦点、来源版本、选中/省略原因、token预算和指纹；图4与图E沿用同一指纹。
- 人物知识使用 `character_knowledge`，揭秘条件使用 `revelation_gate`；无正文证据的 `CardPatch` 不得提交。
- 正文结构有效后执行确定性质量评分；低于72分才追加候选，最多3次，提升低于2分提前停止并保留最佳有效稿。

## 汇总

| 图 | Step | Prompt | 版本 | 输入 Schema | 输出 Schema | 变量 |
|---|---|---|---|---|---|---|
| 1 | `graph1.stage.spec00` | `graph1.spec00` | 2.2 | `CreateRunRequest` | `AuthObject` | input_pack.user_brief, input_pack.complexity_profile |
| 1 | `graph1.world.A` | `graph1.worldA` | 2.1 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.user_brief, input_pack.complexity_profile |
| 1 | `graph1.world.B` | `graph1.worldB` | 2.1 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content |
| 1 | `graph1.opp.eco` | `graph1.oppEco` | 2.1 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content, input_pack.world_b_content, input_pack.pow_l_content, input_pack.pow_s_content, input_pack.pow_e_content |
| 1 | `graph1.cast.core` | `graph1.castCore` | 1.1 | `CreateRunRequest` | `AuthObject` | input_pack.user_brief, input_pack.spec00_content, input_pack.world_b_content, input_pack.opp_eco_content, input_pack.complexity_profile |
| 1 | `graph1.pow.L` | `graph1.powL` | 2.0 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content |
| 1 | `graph1.pow.S` | `graph1.powS` | 2.0 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content, input_pack.pow_l_content |
| 1 | `graph1.pow.E` | `graph1.powE` | 2.1 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content, input_pack.pow_l_content, input_pack.pow_s_content, input_pack.complexity_profile |
| 1 | `graph1.bible.lint` | `graph1.bibleLint` | 2.0 | `CreateRunRequest` | `RunManifest` | input_pack |
| 2 | `graph2.longline.core` | `graph2.longlineCore` | 2.1 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content |
| 2 | `graph2.story.room` | `graph2.storyRoom` | 3.0 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content, input_pack.cast_content, input_pack.longline_core, input_pack.complexity_profile |
| 2 | `graph2.map.room` | `graph2.mapRoom` | 1.0 | `CreateRunRequest` | `AuthObject` | input_pack.spec00_content, input_pack.world_a_content, input_pack.cast_content, input_pack.longline_core, input_pack.story_room_core, input_pack.complexity_profile |
| 3 | `graph3.volume.plan` | `graph3.volumePlan` | 2.1 | `CreateRunRequest` | `VolumeContract` | input_pack.longline_content, input_pack.carryover_context, input_pack.volume_index, input_pack.volume_id, input_pack.complexity_profile |
| 3 | `graph3.volume.story_room` | `graph3.volumeStoryRoom` | 3.0 | `CreateRunRequest` | `VolumeContract` | input_pack.longline_content, input_pack.volume_plan_content, input_pack.carryover_context, input_pack.complexity_profile |
| 3 | `graph3.volume.map_room` | `graph3.volumeMapRoom` | 1.0 | `CreateRunRequest` | `VolumeContract` | input_pack.longline_content, input_pack.volume_plan_content, input_pack.volume_story_core, input_pack.carryover_context, input_pack.complexity_profile |
| 3 | `graph3.volume.event_designs` | `graph3.volumeEventDesigns` | 2.0 | `CreateRunRequest` | `VolumeContract` | input_pack.longline_content, input_pack.volume_plan_content, input_pack.volume_story_core, input_pack.volume_map_room, input_pack.complexity_profile |
| 3 | `graph3.volume.fatigue_report` | `graph3.fatigueReport` | 2.0 | `CreateRunRequest` | `FatigueReport` | input_pack.volume_plan_content, input_pack.volume_id |
| 4 | `graph4.event.budget` | `graph4.eventBudget` | 3.0 | `CreateRunRequest` | `RunManifest` | input_pack.event_slot, input_pack.volume_content, input_pack.is_key_event, input_pack.context_meta |
| 4 | `graph4.event.route` | `graph4.eventRoute` | 1.0 | `CreateRunRequest` | `EventSlot` | input_pack.event_slot, input_pack.budget, input_pack.latest_snapshot, input_pack.volume_content, input_pack.context_meta |
| 4 | `graph4.event.world_pulse` | `graph4.worldPulse` | 1.0 | `CreateRunRequest` | `EventSlot` | input_pack.event_slot, input_pack.event_route, input_pack.latest_snapshot, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content |
| 4 | `graph4.event.expand` | `graph4.eventExpand` | 1.0 | `CreateRunRequest` | `EventSlot` | input_pack.event_slot, input_pack.event_route, input_pack.world_pulse, input_pack.budget, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content |
| 4 | `graph4.event.prewrite_check` | `graph4.prewriteCheck` | 1.0 | `CreateRunRequest` | `VerifyResult` | input_pack.event_slot, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.event_plan, input_pack.latest_snapshot |
| 4 | `graph4.event.need_fact_rag` | `graph4.needFactRag` | 2.0 | `CreateRunRequest` | `RunManifest` | input_pack |
| 4 | `graph4.event.plan` | `graph4.eventPlan` | 3.0 | `CreateRunRequest` | `EventSlot` | input_pack.event_slot, input_pack.budget, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.prewrite_feedback, input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content |
| 4 | `graph4.event.jit_cards` | `graph4.jitCards` | 2.1 | `CreateRunRequest` | `RunManifest` | input_pack.event_slot, input_pack.block_plan, input_pack.bible_content, input_pack.char_content, input_pack.reg_content, input_pack.context_meta |
| 4 | `graph4.event.namecheck` | `graph4.namecheck` | 2.0 | `CreateRunRequest` | `RunManifest` | input_pack.event_slot, input_pack.block_plan, input_pack.bible_content, input_pack.char_content, input_pack.reg_content, input_pack.context_meta |
| 4 | `graph4.event.blocks.write` | `graph4.blocksWrite` | 3.0 | `CreateRunRequest` | `EventDraft` | input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content, input_pack.event_plan, input_pack.scene_plan, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.budget, input_pack.jit_cards, input_pack.retry_feedback |
| R | `graphR.material.rag` | `预留/未实现` | - | `未实现` | `未实现` | input_pack |
| E | `graphE.event.presnapshot.build` | `graphE.presnapshot` | 2.0 | `CreateRunRequest` | `StateSnapshot` | input_pack.event_id, input_pack.run_id, input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.recent_events, input_pack.context_meta, input_pack.context_meta.fingerprint |
| E | `graphE.event.extract` | `graphE.extract` | 3.0 | `EventDraft` | `ObservedDelta` | input_pack.event_id, input_pack.pre_snapshot, input_pack.draft_text, input_pack.context_meta |
| E | `graphE.event.reconcile` | `graphE.reconcile` | 3.0 | `ObservedDelta` | `DiffReport` | input_pack.event_id, input_pack.draft_text, input_pack.pre_snapshot, input_pack.observed_delta, input_pack.run_id, input_pack.context_meta |
| E | `graphE.event.fix` | `graphE.fix` | 3.0 | `DiffReport` | `EventDraft` | input_pack.event_id, input_pack.draft_text, input_pack.violations, input_pack.fix_level, input_pack.patch_instructions |
| E | `graphE.event.commit` | `graphE.commit` | 2.0 | `StagingPacket` | `CommitReceipt` | input_pack.event_id, input_pack.run_id, input_pack.diff_report, input_pack.committed_at |
| P | `graphP.chapter.license` | `graphP.chapterLicense` | 2.0 | `CreateRunRequest` | `ChapterSpec` | input_pack |
| 5 | `graph5.chapterize.cut` | `graph5.chapterizeCut` | 3.0 | `EventDraft` | `ChapterSpec` | input_pack.event_id, input_pack.draft_text, input_pack.history_count, input_pack.scene_ids |
| 5 | `graph5.chapterize.review` | `graph5.chapterizeReview` | 3.0 | `ChapterSpec` | `VerifyResult` | input_pack.chapter_specs, input_pack.chapter_texts, input_pack.event_id |
| 5 | `graph5.chapter.fatigue_report` | `graph5.fatigue` | 2.0 | `CreateRunRequest` | `FatigueReport` | input_pack |
| 5 | `graph5.chapter.commit` | `graph5.chapterCommit` | 2.0 | `StagingPacket` | `CommitReceipt` | input_pack |
| S | `graphS.auth.verify` | `graphS.authVerify` | 2.0 | `StagingPacket` | `VerifyResult` | input_pack |
| S | `graphS.auth.commit` | `graphS.authCommit` | 2.0 | `AtomicCommitSpec` | `CommitReceipt` | input_pack |
| 6 | `graph6.regression.run` | `graph6.regressionRun` | 2.0 | `CreateRunRequest` | `RunManifest` | input_pack |

## 完整提示词

### `graph1.stage.spec00`

- 说明：#00 规格与契约基线生成
- Prompt：`graph1.spec00` v2.2
- 模板：`server/src/novelwb/prompts/graph1/spec00/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.user_brief, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=4000；best_of_n=1

```jinja2
{# graph1.spec00 v2.1 — #00规格与契约基线 #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是网络长篇小说的总设计师、主编、质检官。你的核心职责是：根据用户提供的小说简介，生成#00规格文档——这是整部小说的核心契约，后续所有设定层级必须与此文档对齐。没有你的签发，任何设定、章节、事件均不合法。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 规格一旦生成即为契约，后续层级只能在此基础上细化，不得推翻
6. **用户明确指定的复杂度、禁用机制和阅读门槛高于模板示例**；不得以“长篇需要”为理由擅自增加阴谋、反转、灰色势力或隐藏身份
7. 先从用户简介提取 complexity_profile；标记为简单/无脑爽时，所有后续字段都必须采用低复杂度方案

## 用户输入的小说简介

{{ input_pack.user_brief }}

## 系统复杂度路由（硬约束）
{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

输出中的 complexity_profile.level 必须与系统路由一致。若为 low：只允许单线直接因果，隐藏层数为0，禁止灰色势力、身份反转、套娃阴谋和幕后黑手。

## 硬检查清单（输出前必须全部通过）

- [ ] main_promise 是否一句话说清楚了"谁在什么世界用什么方式实现什么目标"
- [ ] type_contract 三段是否覆盖了训练期/加压期/升维期的完整弧线
- [ ] breather_policy 的 quota_ratio + momentum_debt_max 是否互相匹配（高债上限允许更低缓冲比）
- [ ] lens_climate 的 forbidden_tones 是否与 main_promise 的情绪基调一致
- [ ] writing_dictionary 的章节意图定义是否足够清晰到能指导逐章写作
- [ ] forbidden_zones 中是否覆盖了本类型最常见的"读者崩盘"红线
- [ ] core_hook 是否足够有张力，能在第一章末留住读者
- [ ] complexity_profile 是否逐条保留用户对“简单、直白、禁用复杂逻辑”的要求
- [ ] taboo_words 与 forbidden_zones 是否覆盖用户明确禁止的机制，而不是被模板默认偏好覆盖

## 输出JSON结构与字段说明

输出一个符合以下结构的JSON对象（不要有任何注释）：

{
  "genre": "玄幻 / 都市 / 科幻 / 历史 / 修仙 / 末世 等，选一个或组合",
  "complexity_profile": {
    "level": "low / medium / high；用户要求无脑爽、简单直接时必须为low",
    "plot_logic": "允许的情节复杂度，例如：单线推进、因果直接",
    "max_active_factions": 4,
    "max_reversals_per_volume": 0,
    "forbidden_mechanisms": ["逐条抄录用户禁止的复杂机制，例如：套娃阴谋、幕后黑手、多重身份"]
  },
  "main_promise": "一句话核心承诺，例如：废柴少年以禁忌体质在天才云集的宗门中以弱胜强、踏上无上之路",
  "lens": "叙事视角与主情绪基调，例如：第三人称贴身视角，主情绪为压抑→爆发→快感释放，章末必留悬念",
  "lens_climate": {
    "narrator_attitude": "叙述者对世界的基本态度，例如：冷静观察者，不主动评判，但字里行间流露出对弱者命运的悲悯",
    "emotion_base": "全书情绪底色，例如：压抑底色上偶有热血爆发，以落差感制造快感",
    "image_density": "意象/比喻密度要求，例如：中密度，每500字至多1个核心意象，避免堆砌",
    "forbidden_tones": ["绝对禁止出现的情绪腔调（3条），例如：圣母式自我感动", "廉价鸡汤金句", "读者高高在上的嘲讽视角"]
  },
  "type_contract": {
    "training_baseline": "前30-50事件奖励节律，例如：每5事件一个小胜利，每15事件一次阶段性大爽点，每卷末一次翻盘高潮",
    "mid_pressure": "中期加压方式，例如：反派势力系统性升维，主角能力遭到克制，盟友关系出现裂痕",
    "late_upgrade": "后期升维方向，例如：格局从个人复仇扩展到宗派存亡，主角需付出真正代价"
  },
  "taboo_words": [
    "不能出现的词语或表达，如：突然获得神秘传承",
    "其他禁忌词"
  ],
  "budget": {
    "total_events": 300,
    "events_per_volume": 30,
    "avg_chars_per_event": 4000
  },
  "core_hook": "开篇必须建立的核心悬念，一句话，例如：主角发现藏在自己丹田里的封印是某位绝世强者留下的遗志",
  "protagonist_core": {
    "want": "表层欲求（显性目标），例如：成为天下第一强者",
    "fear": "深层恐惧（内在驱动），例如：害怕重复父亲的悲剧，被自己保护的人所抛弃",
    "blindspot": "认知盲点（成长弧的核心），例如：误以为力量可以解决一切，忽视了情感与信任的重量"
  },
  "scale_budget": {
    "max_entities_per_event": 4,
    "max_terms_per_event": 4,
    "max_explanation_density": 0.20,
    "avg_chapter_chars": 3000
  },
  "breather_policy": {
    "quota_ratio": 0.20,
    "max_consecutive": 2,
    "momentum_debt_max": 5
  },
  "writing_dictionary": {
    "block_intents": {
      "推进块": "推动外部情节前进，主角采取行动、遭遇新障碍或获得新信息，读者感受到进度",
      "结算块": "兑现之前欠下的叙事债或情感债，让读者获得完成感，可以是胜利、揭晓或代价落地",
      "缓冲块": "降低叙事密度，给角色与读者喘息，以生活细节或轻松互动为主，每卷不超过配额",
      "伏笔块": "埋设后续剧情的线索或悬念，通常与当前主线轻微错位，让读者察觉到危险正在聚集"
    },
    "chapter_intents": {
      "Advance": "推进主线冲突，本章结尾必须让故事不可逆地向前走一步",
      "Settle": "结算本事件内的局部债务，允许短暂降低张力，但必须在章末埋下新钩子",
      "Foreshadow": "铺垫伏笔或世界扩展，密度控制在单章不超过2个新信息点",
      "Breather": "合法休息章，必须有情感价值或角色关系推进，不允许纯粹的无意义闲聊"
    },
    "breather_quota_rules": "全书Breather章不超过总章数的20%；连续Breather不超过2章；动量债≥4时禁止Breather直到债务降至2以下"
  },
  "forbidden_zones": [
    "主角靠运气而非努力或代价取得关键胜利",
    "世界规则因剧情需要随意更改，没有提前铺垫",
    "反派智商降为零以成全主角",
    "核心角色死亡后立即复活且无任何代价",
    "爽点堆叠超过3个事件不落地任何实质代价"
  ],
  "self_check": {
    "contract_alignment": "main_promise 与 type_contract 是否形成完整的承诺-兑现弧线",
    "climate_consistency": "lens_climate 的 forbidden_tones 是否与 main_promise 的情绪基调无矛盾",
    "budget_realism": "budget 的 total_events 与 events_per_volume 是否能支撑 type_contract 三段的完整展开",
    "hook_strength": "core_hook 是否足够强，能在第一章吸引读者继续阅读"
  }
}
```

### `graph1.world.A`

- 说明：世界A层硬锚生成（意义系统/意象种子/禁区反差）
- Prompt：`graph1.worldA` v2.1
- 模板：`server/src/novelwb/prompts/graph1/worldA/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.user_brief, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=3000；best_of_n=3

```jinja2
{# graph1.worldA v2.0 — 世界A层硬锚（意义系统/冲突源/意象种子/禁区反差） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是世界观架构师、主编、质检官。你的核心职责是：基于#00规格，生成世界A层——整个世界观的精神骨架。你定义世界的意义系统、核心冲突源、意象种子、运行哲学，以及天然禁区。A层是所有后续层级的精神宪法，不得被任何具体设定推翻。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. A层定义的意义系统必须能解释为什么"强大"在这个世界是有代价的

## #00规格（核心契约）

{{ input_pack.spec00_content | tojson(indent=2) }}

## 用户原始简介

{{ input_pack.user_brief }}

## 系统复杂度路由（硬约束）
{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

若 level=low，只生成最小充分设定：exchange_rules 2-3条、conflict_sources 1-2个、motif_seeds 1-2个、forbidden_zones_and_contrasts 2-3条；不得为凑数量增加支线逻辑。

## 硬检查清单（输出前必须全部通过）

- [ ] conflict_sources 中每一条冲突源是否都能在30卷内持续供应张力，而不是一个卷就被解决
- [ ] exchange_rules 数量是否服从复杂度路由；low 时2-3条即可，优先覆盖本书实际会写到的场景
- [ ] motif_seeds 中每个意象是否都有可以"翻面"的方向（即同一意象在不同阶段含义逆转）
- [ ] forbidden_zones_and_contrasts 是否覆盖核心崩盘红线；low 时2-3条，不得为凑数量扩张
- [ ] world_feel 的描述是否能指导写作时的遣词造句和氛围营造
- [ ] meaning_system 的 misread_risks 是否预判了读者可能误解的地方并给出了修正方向

## 输出JSON结构与字段说明

{
  "world_feel": "世界的整体质感描述，一段话，例如：这是一个残酷、压抑又偶有温情的世界，美丽与危险并存，普通人的命运如草芥，但正因如此，每一次突破才有真实的重量",
  "conflict_sources": [
    {
      "name": "冲突源名称，例如：血脉等级制度",
      "one_line": "一句话说明这个冲突源的本质，例如：出身决定上限，努力只能在给定上限内挣扎",
      "visual_anchor": "这个冲突源在文本中的视觉锚点，例如：宗门内门与外门之间那道刻有家族徽记的石门",
      "cost_and_side_effects": "这个冲突源对主角造成的代价与副作用，例如：每次突破血脉压制需要消耗双倍资源，且有走火入魔风险",
      "variation_methods": [
        "这个冲突源的变奏方式（至少2种），例如：血脉觉醒带来的身份认同危机",
        "例如：盟友因血脉差异产生的价值观裂痕"
      ]
    }
  ],
  "meaning_system": {
    "strength_definition": "这个世界中'强大'意味着什么，一句话",
    "nobility_definition": "这个世界中'高贵'意味着什么，一句话",
    "crime_definition": "这个世界中最严重的'罪'是什么，一句话",
    "redemption_definition": "这个世界中'救赎'如何实现，一句话",
    "exchange_rules": [
      "交换规则1：例如：力量可以换取服从，但换不来真正的忠诚",
      "交换规则2：例如：知识可以出售，但核心传承只能通过血脉或认可获得",
      "交换规则3：例如：寿命可以换取力量，但每个人的寿命总量是固定的",
      "交换规则4：例如：名誉可以被摧毁但不能被购买，只能被时间和行动重建",
      "交换规则5：例如：背叛一次就永远失去信任，这个世界没有第二次机会"
    ],
    "misread_risks": [
      {
        "risk": "读者可能误读的地方，例如：误以为只要足够努力就能突破血脉上限",
        "correction": "正确理解应该是，例如：努力可以无限接近上限但永远无法超越，除非打破规则本身"
      },
      {
        "risk": "另一个误读风险",
        "correction": "对应修正"
      }
    ]
  },
  "motif_seeds": [
    {
      "name": "意象名称，例如：残破的玉牌",
      "first_scene": "首次登场场景，例如：主角在废墟中从父亲遗骸旁捡起这枚碎裂的玉牌",
      "emotion_tone": "初始情绪调性，例如：悲伤与愤怒的混合，家族耻辱的具象",
      "flip_directions": [
        "意象翻面方向1，例如：玉牌碎裂的纹路暗合了某种古老功法的脉络图，耻辱变成了线索",
        "意象翻面方向2，例如：主角最终将玉牌送给盟友，耻辱的烙印变成了信任的凭证"
      ],
      "final_echo": "全书结尾的呼应方式，例如：玉牌在最终决战中以某种方式完整，象征主角完成了自我和解"
    }
  ],
  "forbidden_zones_and_contrasts": {
    "forbidden_zones": [
      "禁区1：主角靠运气而非努力或代价取得关键胜利",
      "禁区2：世界规则因剧情需要随意更改",
      "禁区3：反派智商降为零以成全主角",
      "禁区4：核心角色死亡后无代价复活",
      "禁区5：主角长期无敌无阻力"
    ],
    "contrast_points": [
      {
        "point": "对比点名称，例如：主角的草根出身 vs 天才们的金汤匙",
        "how_it_serves_story": "这个对比如何服务于故事，例如：让每一次进步都显得来之不易，强化读者的代入感和爽感落差"
      },
      {
        "point": "另一个对比点",
        "how_it_serves_story": "服务方式"
      }
    ]
  },
  "self_check": {
    "drift_risks": [
      "最容易发生的设定漂移风险1，例如：随着卷数增加，意义系统被遗忘，强大变得廉价",
      "最容易发生的设定漂移风险2，例如：意象种子被过度使用，失去象征力量"
    ],
    "anchor_rules": [
      "每卷必须遵守的锚定规则1，例如：每卷至少一次让主角感受到meaning_system中定义的代价",
      "每卷必须遵守的锚定规则2，例如：每卷至少呼应一次motif_seeds中的某个意象"
    ]
  }
}
```

### `graph1.world.B`

- 说明：世界B层宏观生态/地图框架生成
- Prompt：`graph1.worldB` v2.1
- 模板：`server/src/novelwb/prompts/graph1/worldB/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=4000；best_of_n=2

```jinja2
{# graph1.worldB v2.1 — 世界B层（宏观生态/地理/派系/交通贸易/制度框架） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是世界生态设计师、主编、质检官。你的核心职责是：基于#00规格和世界A层，生成世界B层——世界的宏观生态框架。B层是具体事件发生的"舞台骨架"，定义地理、派系、资源争夺逻辑、交通贸易和制度框架。B层的每一个设计都必须能为故事持续供应冲突与张力。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. B层规模必须服从 #00 的 complexity_profile，不得为了填满模板擅自扩张世界
6. complexity_profile.level=low 时：首卷只保留2-4个活跃场景、2-4个活跃势力；每区1-2种直接冲突即可；secret 可以是公开弱点，不得生成幕后组织、渗透网、政治派系或套娃秘密

## #00规格

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层

{{ input_pack.world_a_content | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] zones 的数量和每区 conflict_supply 是否符合 complexity_profile；low 时宁少勿杂
- [ ] transport_and_trade 是否解释了信息如何在世界中流动（直接决定了剧情推进速度）
- [ ] institution_framework 是否覆盖了"弱者为什么不能轻易翻身"的制度逻辑
- [ ] factions 是否没有超过复杂度预算；low 时 secret 不得引出新势力或新阴谋
- [ ] power_distribution 的三类势力是否与主角的成长弧有明确的叙事关联
- [ ] self_check 的 top_3_ecology_rules 是否足够具体，能在写作时直接查阅

## 输出JSON结构与字段说明

{
  "geography": {
    "macro_structure": "宏观地理结构描述，例如：三大洲域，中央圣地，东荒蛮域，西海边境，南方禁地",
    "key_locations": [
      {"name": "地名", "description": "简述及其在故事中的功能"},
      {"name": "另一地名", "description": "简述"}
    ],
    "resource_hotspots": ["稀缺资源分布点，驱动冲突，例如：灵晶矿脉集中于东荒三宗控制区"]
  },
  "factions": [
    {
      "name": "派系名称",
      "tier": "顶级 / 中层 / 底层",
      "ideology": "该派系的核心意识形态或行事逻辑",
      "relation_to_protagonist": "与主角的关系：对立 / 潜在盟友 / 中立势力",
      "secret": "该派系隐藏的秘密或弱点（供后续剧情使用）"
    }
  ],
  "ecology": {
    "power_hierarchy": "力量等级体系简述，例如：凡体→灵体→铸魂→元婴→化神，共九境",
    "resource_scarcity": "核心稀缺资源及其争夺方式",
    "social_mobility": "社会流动规则：弱者如何上升，强者如何跌落"
  },
  "power_distribution": {
    "dominant_forces": ["当前统治势力（2-3个）"],
    "rising_forces": ["正在崛起的势力（1-2个），主角的潜在起点或盟友"],
    "collapsed_forces": ["已经衰落或覆灭的势力，可能与主角背景有关"]
  },
  "zones": [
    {
      "name": "区域名称，例如：东荒蛮域",
      "key_resources": "该区域的核心资源，例如：天材地宝密度极高，但野兽凶猛，死亡率是中央圣地的十倍",
      "aesthetic_feel": "该区域的视觉与氛围质感，例如：荒凉、粗犷、血腥，天空常年被红色尘雾笼罩",
      "power_structure": "该区域的权力结构，例如：无正式政权，由五大野兽族群分割统治，人类聚落苟活其间",
      "conflict_supply": [
        "冲突供给1，例如：稀缺天材地宝引发的争夺战",
        "冲突供给2，例如：野兽族群与人类聚落的生存边界冲突",
        "冲突供给3，例如：五大族群之间的势力平衡随主角到来被打破"
      ],
      "variation_points": [
        "变奏点1，例如：某野兽族群首领实为被封印的上古强者",
        "变奏点2，例如：最偏远的聚落掌握着通往禁地的唯一路径"
      ],
      "forbidden_points": [
        "禁忌点：例如：禁止主角在此区域轻易获得完整传承，资源必须付出对等代价"
      ]
    }
  ],
  "transport_and_trade": {
    "transport_methods": "主要交通方式及其限制，例如：御剑飞行需要金丹境以上，低境界依赖传送阵（需灵石），或骑乘兽类",
    "trade_arteries": "主要贸易干道及其控制者，例如：东西大商道由商盟把持，对宗门弟子收取通行费",
    "info_and_rumor_mechanism": "信息与谣言在世界中的流通机制，例如：情报网由影楼垄断，消息的真实性与价格成正比，但影楼从不核实"
  },
  "institution_framework": {
    "legitimate_violence": "谁有权合法使用暴力及其边界，例如：各宗门在自家地盘拥有生杀大权，宗门外需要持有特定令牌",
    "contract_and_punishment": "契约与惩罚体系，例如：天道誓言一旦违背会受到天罚，但聪明人总能找到措辞漏洞",
    "wealth_and_status_access": "财富与地位的获取途径，例如：灵石→修为→宗门地位→婚姻联盟，底层无法跳跃任何一步",
    "survival_logic": [
      "弱者的生存逻辑1，例如：抱大腿——找比自己强的靠山，用忠诚换保护",
      "弱者的生存逻辑2，例如：钻空子——利用强者之间的矛盾谋求生存空间"
    ]
  },
  "self_check": {
    "top_3_ecology_rules": [
      "写作时必须随时参照的生态规则1，例如：任何稀缺资源一旦出现，立刻有多方势力竞争，主角不可能默默独占",
      "写作时必须随时参照的生态规则2，例如：信息传播速度决定主角的行动窗口，影楼一旦介入，秘密最多保持三天",
      "写作时必须随时参照的生态规则3，例如：制度保护强者，主角每次以弱胜强都会引发系统性反弹"
    ]
  }
}
```

### `graph1.opp.eco`

- 说明：对手生态OppEco生成（四层压迫/灰度势力/进化机制）
- Prompt：`graph1.oppEco` v2.1
- 模板：`server/src/novelwb/prompts/graph1/oppEco/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content, input_pack.world_b_content, input_pack.pow_l_content, input_pack.pow_s_content, input_pack.pow_e_content
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=4000；best_of_n=2

```jinja2
{# graph1.oppEco v2.1 — 对手生态OppEco（对立力量的完整生态） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是对手与压迫系统设计师、主编、质检官。你的核心职责是：基于已建立的世界观层级，构建与用户复杂度要求相匹配的对立生态。对手用于标记主角成长刻度；简单爽文允许动机直接、登场即结算的功能型对手，不得强行复杂化。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 对手行为要有最小因果逻辑，但复杂度必须服从 #00 complexity_profile
6. complexity_profile.level=low 时：终极对手可以只是公开的最强竞争者；tier2_factions 最多3个；gray_forces 必须为空数组；oppression_spectrum 只保留2-4种直接形式；禁止隐藏身份、幕后收割、道德拷问、盟友背叛、制度阴谋和套娃靠山
7. 模板中的数量和示例不是强制扩写许可，与用户禁令冲突时必须缩减或返回空数组

## #00规格

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层

{{ input_pack.world_a_content | tojson(indent=2) }}

## 世界B层

{{ input_pack.world_b_content | tojson(indent=2) }}

## 力量定律层（POW_L）

{{ input_pack.pow_l_content | tojson(indent=2) }}

## 力量结构层（POW_S）

{{ input_pack.pow_s_content | tojson(indent=2) }}

## 力量表现层（POW_E）

{{ input_pack.pow_e_content | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] tier1_boss 的复杂度是否符合 complexity_profile；low 时 reveals 可为公开升级节点，不得制造身份反转
- [ ] tier2_factions 中是否有至少一个"早期霸凌者→后期垫脚石"的完整弧线
- [ ] gray_forces 是否符合复杂度预算；low 时必须为空数组
- [ ] oppression_spectrum 数量是否符合复杂度预算；low 时只保留2-4种直接压迫
- [ ] evolution_mechanism 是否说明了对手如何随主角成长而升维（不能对手永远停在原地）
- [ ] self_check 的 flatness_risks 是否指出了最容易让对手变"纸片人"的两个写作陷阱

## 输出JSON结构与字段说明

{
  "tier1_boss": {
    "name": "终极BOSS名称（可以是势力名）",
    "identity": "公开身份或真实本质；low 时禁止表里两层身份",
    "motivation": "核心动机，例如：为了逆转天命，复活被封印的同类",
    "power_ceiling": "力量上限（必须超过主角当前能触及的上限）",
    "reveals": ["阶段升级节点；low 时只写公开实力或公开目标的升级，不写身份反转"]
  },
  "tier2_factions": [
    {
      "name": "中层对手势力名",
      "role": "在主角成长弧中的功能，例如：早期霸凌者→中期壁垒→后期盟友",
      "peak_threat_volume": "在第几卷对主角威胁最大",
      "defeat_condition": "如何才能真正击败该势力"
    }
  ],
  "tier3_mobs": {
    "archetypes": ["杂鱼的原型类型（3-5种），例如：纨绔子弟型、嫉妒天才型、奸商型、腐败官员型"],
    "density": "每卷大约出现几个此类对手",
    "purpose": "这些对手在叙事中的功能，例如：提供早期爽点，验证主角当前实力级别"
  },
  "gray_forces": [
    {
      "name": "灰色势力名",
      "ambiguity": "仅 medium/high 使用；low 时 gray_forces 返回空数组",
      "narrative_function": "在故事中的叙事功能，例如：揭示主角立场的局限性，逼迫主角做出道德选择"
    }
  ],
  "evolution_mechanism": "对手生态的演化逻辑，例如：每次主角升维，对手集体升级；初期欺压主角的人后来成为主角的垫脚石，但不能简单复仇——要有代价",
  "oppression_spectrum": [
    {
      "form": "压迫形式，例如：直接武力碾压",
      "reader_payoff": "读者从这种压迫中获得的情感回报，例如：积累愤怒，为后续爆发蓄力",
      "protagonist_resistance_cost": "主角抵抗这种压迫必须付出的代价，例如：消耗珍贵丹药，暴露隐藏能力"
    },
    {
      "form": "压迫形式2：制度性剥夺，例如：被取消参赛资格",
      "reader_payoff": "读者情感回报，例如：感受到不公正，产生强烈共情",
      "protagonist_resistance_cost": "主角代价，例如：需要找到替代途径，消耗额外时间与资源"
    },
    {
      "form": "压迫形式3：信息封锁，例如：关键情报被人为隐瞒",
      "reader_payoff": "读者情感回报，例如：悬疑感，与主角同步感受信息不对称的焦虑",
      "protagonist_resistance_cost": "主角代价，例如：必须冒险去主动探查，承担暴露风险"
    },
    {
      "form": "压迫形式4：关系破坏，例如：盟友被策反或离间",
      "reader_payoff": "读者情感回报，例如：背叛感与愤怒，强化对反派的仇恨",
      "protagonist_resistance_cost": "主角代价，例如：孤立无援，需要付出更大代价重建信任"
    },
    {
      "form": "压迫形式5：资源掠夺",
      "reader_payoff": "读者情感回报，例如：剥夺感，让读者更期待主角的反击",
      "protagonist_resistance_cost": "主角代价，例如：修炼进度被迫中断，需要重新积累"
    },
    {
      "form": "压迫形式6：身份污名化",
      "reader_payoff": "读者情感回报，例如：共情主角的屈辱感，渴望翻盘",
      "protagonist_resistance_cost": "主角代价，例如：无法公开使用真实身份，行动受限"
    },
    {
      "form": "压迫形式7：亲人威胁",
      "reader_payoff": "读者情感回报，例如：保护欲与愤怒并发，情绪强度最高",
      "protagonist_resistance_cost": "主角代价，例如：不得不妥协，吞下屈辱换取保护"
    },
    {
      "form": "压迫形式8：规则绑架，例如：利用门规或法律陷害",
      "reader_payoff": "读者情感回报，例如：感受到制度的虚伪性，渴望主角找到打破规则的方式",
      "protagonist_resistance_cost": "主角代价，例如：必须在规则内找破绽，时间成本极高"
    }
  ],
  "self_check": {
    "flatness_risks": [
      "对手纸片化风险1，例如：反派只会嘲讽和命令手下，没有展示出真正的智慧或能力，读者无法理解主角为何忌惮",
      "对手纸片化风险2，例如：灰色势力随着剧情推进逐渐明确站队，丧失了道德模糊性，失去叙事张力"
    ],
    "correction_reminders": [
      "修正提醒1，例如：每隔5个事件，让对手展示一次超出主角预期的智慧或手段",
      "修正提醒2，例如：灰色势力在每卷末至少有一次让读者无法判断其善恶的行动"
    ]
  }
}
```

### `graph1.cast.core`

- 说明：核心角色阵容、关系与知识边界
- Prompt：`graph1.castCore` v1.1
- 模板：`server/src/novelwb/prompts/graph1/castCore/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.user_brief, input_pack.spec00_content, input_pack.world_b_content, input_pack.opp_eco_content, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=5000；best_of_n=2

```jinja2
{# graph1.castCore v1.0 - core cast authority #}
{% include '_shared/json_output_contract.jinja2' %}

你是网络小说角色统筹编辑。建立能直接支持写作的核心角色阵容，而不是人物百科。

## 硬约束
1. 输出合法 JSON，不输出解释。
2. 每名角色必须有稳定 id、姓名、叙事职能、公开目标、当前能力边界、与主角关系、已知信息和未知信息。
3. relationships 必须引用 characters 中存在的 id，且说明当前关系、张力和不可擅自改变的边界。
4. knowledge_boundaries 用于防止角色知道尚未获知的信息。
5. complexity level=low 时只保留4-6名核心角色：主角、直接伙伴或引路人、情感或家庭锚点、早期对手、阶段Boss；动机直白，不设隐藏身份，不设灰色阵营。
6. medium 为6-10名；high 才允许10-16名和多层关系。不得为凑数创建角色。
7. 丰富度来自每名角色的背景压力、欲望、恐惧、缺点、行为特征、语言策略、能力代价和关系差异，不来自增加无关角色数量。
8. 每名核心角色必须能独立产生行动：有自己的目标、资源、判断和失败风险，不能只为主角递信息、赞叹或被击败。
9. 性格必须可表演。禁止只写“冷静、善良、坚强”等标签，必须同时给出压力反应、习惯动作、说话策略和会造成麻烦的缺点。

## 用户简介
{{ input_pack.user_brief }}

## 复杂度路由
{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## #00规格
{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界与势力
{{ input_pack.world_b_content | tojson(indent=2) }}

## 对手生态
{{ input_pack.opp_eco_content | tojson(indent=2) }}

## 输出结构
{
  "characters": [{
    "id": "char_protagonist",
    "name": "角色姓名",
    "role": "主角/伙伴/引路人/家庭锚点/早期对手/阶段Boss",
    "identity": "当前公开身份",
    "background": {
      "origin": "出身地区、家庭或组织背景",
      "faction": "所属或关联势力；无则空字符串",
      "formative_experience": "塑造当前性格和判断方式的经历",
      "social_position": "当前地位、可调用资源及受到的限制"
    },
    "public_goal": "当前可观察目标",
    "motivation": "直接行动动机",
    "inner_design": {
      "desire": "最想得到什么",
      "fear": "最害怕失去或重演什么",
      "starting_belief": "当前深信并会被故事检验的观念",
      "strengths": ["能影响剧情的优点"],
      "flaws": ["会制造错误选择或关系摩擦的缺点"],
      "value_boundary": "通常不会越过的底线",
      "stress_response": "受压时可见的典型反应"
    },
    "ability": {
      "current_boundary": "当前能做什么、不能做什么",
      "strengths": ["能力优势"],
      "limitations": ["限制与克制"],
      "costs": ["使用能力或资源的代价"],
      "signature_methods": ["有角色辨识度的能力或行动方式"]
    },
    "relationship_to_protagonist": "当前关系",
    "known_facts": ["已经知道的事实"],
    "unknown_facts": ["尚不知道、不得提前表现为知道的事实"],
    "performance_anchors": {
      "speech_rhythm": "说话节奏",
      "speech_strategy": "直说、试探、反问、沉默、转移等主要策略",
      "habitual_actions": ["可用于侧面描写的习惯动作"],
      "sensory_impression": "初次登场时具体可感知的印象",
      "contrast_with_others": "与其他核心角色最鲜明的差异"
    },
    "scene_engine": ["该角色能够反复产生但不重复的场景冲突或互动方式"],
    "entry_stage": "预计登场阶段"
  }],
  "relationships": [{
    "from_id": "char_protagonist",
    "to_id": "另一个角色id",
    "current_state": "当前关系",
    "tension": "当前张力",
    "forbidden_jump": "未经事件铺垫不得发生的关系跳变"
  }],
  "knowledge_boundaries": [{
    "fact": "受控事实",
    "known_by": ["角色id"],
    "unknown_to": ["角色id"],
    "reveal_condition": "何种已写事件后才可改变"
  }],
  "ensemble_balance": [{
    "character_id": "角色id",
    "unique_story_value": "只有该角色最适合承担的叙事价值",
    "independent_action_source": "即使主角不在场，该角色仍会采取什么行动",
    "avoid_redundancy_with": ["不能与哪些角色写成同一种声音或功能"]
  }]
}
```

### `graph1.pow.L`

- 说明：力量定律层POW_L生成（核心守恒/代价/反制点）
- Prompt：`graph1.powL` v2.0
- 模板：`server/src/novelwb/prompts/graph1/powL/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=4000；best_of_n=3

```jinja2
{# graph1.powL v2.0 — 力量定律层POW_L（物理/因果底层规则） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是力量体系的定律设计师、主编、质检官。你的核心职责是：基于#00规格和世界A层，定义力量的底层定律——这是力量系统的"物理法则"，任何能力的使用都必须符合这些定律，不得违反。定律层是力量系统的宪法，结构层和表现层只能在此基础上细化，不得推翻。好的定律必须有内在逻辑自洽性，且能持续为故事制造紧张感。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 每条定律都必须有代价，没有代价的力量等于失去了叙事张力

## #00规格

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层

{{ input_pack.world_a_content | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] core_law 是否能用一句话说清楚力量的根本来源与运作原理
- [ ] conservation_rule 是否明确了"代价"的具体形式（不能只说"有代价"而不说代价是什么）
- [ ] laws 中每条定律是否都有 cost_and_side_effects 且不为空
- [ ] term_table 中的每个术语是否都有 visual_anchor（视觉锚点），避免纯抽象术语
- [ ] forbidden_abilities 是否能解释为什么它们被禁止（逻辑原因，而非仅声明禁止）
- [ ] self_check 的 vulnerability_laws 是否指出了最容易被作者自己"开后门"的定律

## 输出JSON结构与字段说明

{
  "core_law": "核心定律（一句话，世界中力量的根本运作原理），例如：力量来源于对天地规则的理解与契合，理解越深层次越高，上限越高",
  "conservation_rule": "守恒/代价法则，例如：每次突破都需要消耗等量的生机（寿命），没有代价的力量必然有隐患",
  "cost_principle": "力量使用的即时代价，例如：高境界技能会造成精神损耗，连续使用超过三次必须休息，否则意识崩溃",
  "counter_points": [
    "力量的天然克制关系（3-5条），例如：水系力量克制火系，但火系力量在特定环境可反克",
    "另一条克制关系",
    "关键克制：顶级力量的软肋，例如：意志类力量可以穿透任何物理防御"
  ],
  "forbidden_abilities": [
    "绝对禁止存在的能力（维护世界合理性），例如：不得存在无代价的时间逆转能力",
    "另一条禁忌能力",
    "再一条"
  ],
  "power_ceiling": "力量的理论上限及其原因，例如：化神境是当前时代的天花板，超越此境界需要理解宇宙原始规则，千年来无一人达到",
  "laws": [
    {
      "law_name": "定律名称，例如：守恒代价定律",
      "one_line_rule": "一句话规则，例如：每获得一分力量，必须付出等价代价，代价形式可以延迟但不能消除",
      "trigger_condition": "触发条件，例如：每次使用超出当前境界30%以上的力量时触发",
      "cost_and_side_effects": "代价与副作用，例如：消耗寿命，严重时损伤神魂，轻微时数日内无法修炼",
      "counter_and_breakout": "如何应对或突破此定律，例如：可以通过提前积累"力量债"，在特定时机一次性偿还",
      "writing_hints": [
        "写作提示1，例如：主角每次使用此类技能后必须展示代价，不能忽略",
        "写作提示2，例如：代价的积累可以形成新的危机来源"
      ]
    },
    {
      "law_name": "定律名称2，例如：境界压制定律",
      "one_line_rule": "一句话规则",
      "trigger_condition": "触发条件",
      "cost_and_side_effects": "代价与副作用",
      "counter_and_breakout": "应对或突破方式",
      "writing_hints": [
        "写作提示1",
        "写作提示2"
      ]
    }
  ],
  "cost_principles": [
    "代价硬规则1：代价必须在当场或下一事件内兑现，不允许无限期延迟",
    "代价硬规则2：同一类型代价不能连续三次以相同形式出现，必须有变奏",
    "代价硬规则3：越接近力量上限的技能，代价必须越具体、越不可逆"
  ],
  "term_table": [
    {
      "term": "术语名称，例如：元婴",
      "one_line_definition": "一句话定义，例如：修炼第四境，力量以婴儿形态凝结于神魂之中，实现力量与意识的完全融合",
      "visual_anchor": "视觉锚点，例如：突破时会有金光从天灵盖涌出，持续约三息",
      "cost_anchor": "代价锚点，例如：突破需要消耗三十年寿命，且有三成概率导致元婴残缺",
      "first_appearance_suggestion": "首次登场建议，例如：在第一卷大比前，通过旁观一位强者展示此境界的威力引入"
    }
  ],
  "self_check": {
    "vulnerability_laws": [
      "最容易被作者开后门的定律1，例如：守恒代价定律——作者容易在爽点场景忘记让主角付出代价",
      "最容易被作者开后门的定律2，例如：境界压制定律——作者容易让主角以不合理的方式跨境界对战"
    ],
    "patches": [
      "修补方案1，例如：为守恒代价定律设置"延迟代价"机制，允许代价在3个事件内以任何形式兑现，但必须兑现",
      "修补方案2，例如：为境界压制定律设置明确的"压制豁免条件"，只有满足条件才允许跨境界对战"
    ]
  }
}
```

### `graph1.pow.S`

- 说明：力量结构层POW_S生成（源/路/阀/载体/损伤/漏洞）
- Prompt：`graph1.powS` v2.0
- 模板：`server/src/novelwb/prompts/graph1/powS/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content, input_pack.pow_l_content
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=4000；best_of_n=3

```jinja2
{# graph1.powS v2.0 — 力量结构层POW_S（力量的传导/储存/转化结构） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是力量结构设计师、主编、质检官。你的核心职责是：基于前序层级，定义力量在"载体-通道-阀门-来源"结构上的具体架构。这一层决定了角色如何获取、储存、传导和释放力量，以及受伤和成长的机制。结构层必须与定律层完全自洽，并为表现层提供清晰的接口。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 伤害修复系统必须有代价，不允许存在无代价的即时完全恢复机制

## #00规格

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层

{{ input_pack.world_a_content | tojson(indent=2) }}

## 力量定律层（POW_L）

{{ input_pack.pow_l_content | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] damage_model 是否覆盖了不同部位受伤对力量使用的具体影响（不能笼统说"受伤影响战力"）
- [ ] damage_repair_system 的 repair_cost_and_time 是否足够具体，能指导写作时的时间线安排
- [ ] fake_repair_and_backlash 是否预设了"看似痊愈实则隐患"的机制（制造后续剧情危机）
- [ ] growth_stages 中每个阶段是否都有 common_failure_point（最容易写崩的地方）
- [ ] vulnerability_model 是否与 damage_model 形成配合，为对手设计攻击策略提供依据
- [ ] self_check 的 invincibility_risks 是否指出了最容易让主角变成"无敌"的两个结构性漏洞

## 输出JSON结构与字段说明

{
  "source": "力量的来源类型，例如：天地灵气、个人意志力、血脉遗传、外界神器注入",
  "path": "力量的传导路径（身体内部结构），例如：经脉→丹田→气海→神魂，每一段有独立属性",
  "valve": "力量的调控机制（如何控制输出量），例如：心神控制，修炼精准度决定浪费率，新手浪费80%，宗师仅浪费5%",
  "carrier": "力量的承载体，例如：魂晶（固态储存）、灵血（液态循环）、意念场（无形覆盖）",
  "damage_model": "受伤对力量的影响，例如：经脉损伤导致传导效率下降，丹田破碎导致永久废人，神魂损伤影响控制精度",
  "vulnerability_model": "力量系统的漏洞与弱点，例如：突破瓶颈期力量最不稳定，此时是最佳偷袭时机；特定毒素可直接腐蚀传导路径",
  "capacity_growth": "力量容量的成长规律，例如：每次突破容量翻倍，但突破难度也指数上升；特殊体质可有不同成长曲线",
  "structure_elements": [
    {
      "element_name": "结构元素名称，例如：丹田",
      "function_and_boundary": "功能与边界，例如：力量储存核心，容量上限决定同境界的强弱差异",
      "common_failures": "常见写崩方式，例如：让主角丹田无限扩容而无任何代价",
      "counter_points": "克制方式，例如：专门针对丹田的封脉手法，可临时或永久封印力量",
      "writing_hints": "写作提示，例如：丹田容量的差异是同境界对手强弱分层的主要依据，必须在战前展示"
    }
  ],
  "damage_repair_system": {
    "damage_types": [
      "伤害类型1：外伤——筋骨断裂，影响物理出力，不影响内功输出",
      "伤害类型2：经脉损伤——传导路径受阻，影响技能释放速度和精度",
      "伤害类型3：丹田裂损——储量下降，严重时永久废人",
      "伤害类型4：神魂创伤——控制精度下降，严重时精神错乱",
      "伤害类型5：血毒侵染——缓慢腐蚀力量系统，不处理则持续恶化",
      "伤害类型6：境界回退——极端情况下修为倒退，极难恢复"
    ],
    "repair_methods": [
      "修复方式1：外伤——丹药+休息，标准恢复时间3-7天",
      "修复方式2：经脉损伤——专业疗法+灵气浸润，标准恢复时间数月",
      "修复方式3：丹田裂损——极为罕见的修复材料，且只能修复而非完全痊愈",
      "修复方式4：神魂创伤——特定神魂丹药或时间自然愈合，效果不稳定",
      "修复方式5：血毒——专门解毒丹或找施毒者",
      "修复方式6：境界回退——无法逆转，只能从当前境界重新突破"
    ],
    "repair_cost_and_time": "修复的时间与代价总览，例如：任何修复都需要消耗资源，关键伤势修复必须占用主角1-3个事件的恢复期，不允许单事件内完全痊愈",
    "fake_repair_and_backlash": [
      "假性痊愈1，例如：表面止血成功，但毒素已渗入神魂，会在数个事件后的关键时刻突然发作",
      "假性痊愈2，例如：经脉表面愈合，但内部形成疤痕，导致特定技能永久损耗提升"
    ]
  },
  "growth_stages": [
    {
      "entry_threshold": "进入本阶段的条件，例如：修为达到金丹境，且完成过至少一次以弱胜强",
      "typical_payoff": "本阶段的典型爽感产出，例如：首次能够在正面战斗中压制同境界所有对手",
      "typical_cost": "本阶段的典型代价，例如：需要消耗大量稀缺资源，且突破时有三成失败风险",
      "opponent_evolution": "对手在此阶段如何进化，例如：之前的欺压者不再敢正面交锋，改为借助势力打压",
      "common_failure_point": "最容易写崩的地方，例如：让主角在本阶段获得了过多无代价的能力，失去了力量的重量感"
    },
    {
      "entry_threshold": "进入阶段2的条件",
      "typical_payoff": "阶段2典型产出",
      "typical_cost": "阶段2典型代价",
      "opponent_evolution": "对手进化方式",
      "common_failure_point": "阶段2最容易写崩的地方"
    },
    {
      "entry_threshold": "进入阶段3的条件",
      "typical_payoff": "阶段3典型产出",
      "typical_cost": "阶段3典型代价",
      "opponent_evolution": "对手进化方式",
      "common_failure_point": "阶段3最容易写崩的地方"
    }
  ],
  "self_check": {
    "invincibility_risks": [
      "无敌化风险1，例如：修复系统过于高效，导致主角永远不会带伤作战，失去危机感",
      "无敌化风险2，例如：成长阶段跨越过快，对手来不及进化就被主角远远甩开"
    ],
    "prevention_rules": [
      "预防规则1，例如：任何战斗伤势必须在后续至少一个事件中有明确的负面影响描写",
      "预防规则2，例如：每次突破必须伴随一个新的、同等量级的威胁同步出现"
    ]
  }
}
```

### `graph1.pow.E`

- 说明：力量表现层POW_E生成（文化/流派/装备接口/术语口径）
- Prompt：`graph1.powE` v2.1
- 模板：`server/src/novelwb/prompts/graph1/powE/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content, input_pack.pow_l_content, input_pack.pow_s_content, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=3500；best_of_n=2

```jinja2
{# graph1.powE v2.0 — 力量表现层POW_E（文化/流派/区域接口/术语/装备接口） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是表现层接口设计师、主编、质检官。你的核心职责是：基于前序力量层级，定义力量在文化、流派、区域风格、术语和装备层面的具体表现——这一层决定了读者"看到"和"读到"的力量是什么样的。表现层是力量系统与读者之间的接口，必须足够具体、可感知、有文化质感，且每个流派/区域都有独特的美学标识。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 每个区域/流派接口必须有独特的视觉标识，读者无需看名字就能分辨

## #00规格

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层

{{ input_pack.world_a_content | tojson(indent=2) }}

## 力量定律层（POW_L）

{{ input_pack.pow_l_content | tojson(indent=2) }}

## 力量结构层（POW_S）

{{ input_pack.pow_s_content | tojson(indent=2) }}

## 系统复杂度路由（硬约束）
{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

若 level=low，schools 与 region_and_school_interfaces 各保留1-2个直接服务主线的接口，术语采用最小词表，不得为展示世界规模增加流派。

## 硬检查清单（输出前必须全部通过）

- [ ] region_and_school_interfaces 数量是否服从复杂度路由；low 时1-2个，medium 时2-4个
- [ ] 每个接口的 action_and_combat_style 是否足够具体，能直接指导动作描写
- [ ] term_table 中每个术语是否都有 visual_anchor，避免读者记不住
- [ ] equipment_interface 是否解释了装备与力量系统的融合逻辑（不只是"厉害的武器"）
- [ ] self_check 的 manual_risks 是否指出了最容易让表现层变成"换皮重复"的陷阱
- [ ] 各流派之间是否有足够的差异，能让读者一眼分辨

## 输出JSON结构与字段说明

{
  "culture": "力量修炼的文化氛围，例如：修炼是这个世界最高贵的追求，宗门文化极为严苛，讲究传承与忠诚，背叛师门是天下共诛的大罪",
  "schools": [
    {
      "name": "流派名称，例如：剑宗",
      "philosophy": "该流派的核心理念，例如：以剑意破万法，速度与精准是一切",
      "signature_techniques": ["代表性技法（2-3个）"],
      "weakness": "该流派的致命弱点，例如：无法持久作战，对群战极为不利"
    }
  ],
  "equipment_interface": "装备与力量系统的接口逻辑，例如：法宝需要炼化（与使用者气血融合）才能发挥最大效果，否则只有基础功能；神兵有自己的意识，会选择主人",
  "terminology": {
    "power_level_names": ["境界名称列表，从低到高，例如：炼气、筑基、金丹、元婴、化神"],
    "technique_categories": ["技法分类，例如：攻击型、防御型、辅助型、禁术"],
    "common_idioms": ["该世界常用的力量相关习语（3-5个），例如：一步入金丹，天下我独行"]
  },
  "region_and_school_interfaces": [
    {
      "name": "区域/流派接口名称，例如：东荒蛮族战法",
      "aesthetic_keywords": "美学关键词（3-5个），例如：粗犷、血腥、本能、野性、原始力量",
      "common_titles_and_phrases": ["常用称谓与话语（2-3个），例如：以血铭誓、兽心共鸣、铁骨战歌"],
      "visual_symbols_and_attire": "视觉符号与着装，例如：兽骨项链、血纹图腾、残破皮甲，战斗时皮肤上会浮现红色纹路",
      "action_and_combat_style": "动作与战斗风格，例如：以身体为武器，蓄力爆发而非持续输出，习惯以伤换伤",
      "cost_preference_and_taboos": "代价偏好与禁忌，例如：不用丹药，以战养战，但不可对盟友动手，否则被全族追杀",
      "representative_equipment": [
        "代表性装备1，例如：血骨战斧——以强者骨骼制成，使用时可借助战死者的怨气增幅",
        "代表性装备2，例如：图腾护符——刻有族群图腾，可在危急时触发守护之力一次"
      ]
    },
    {
      "name": "区域/流派接口名称2，例如：中央圣地儒道剑法",
      "aesthetic_keywords": "美学关键词",
      "common_titles_and_phrases": ["常用称谓"],
      "visual_symbols_and_attire": "视觉符号与着装",
      "action_and_combat_style": "动作与战斗风格",
      "cost_preference_and_taboos": "代价偏好与禁忌",
      "representative_equipment": [
        "代表性装备1",
        "代表性装备2"
      ]
    },
    {
      "name": "区域/流派接口名称3",
      "aesthetic_keywords": "美学关键词",
      "common_titles_and_phrases": ["常用称谓"],
      "visual_symbols_and_attire": "视觉符号与着装",
      "action_and_combat_style": "动作与战斗风格",
      "cost_preference_and_taboos": "代价偏好与禁忌",
      "representative_equipment": [
        "代表性装备1",
        "代表性装备2"
      ]
    },
    {
      "name": "区域/流派接口名称4",
      "aesthetic_keywords": "美学关键词",
      "common_titles_and_phrases": ["常用称谓"],
      "visual_symbols_and_attire": "视觉符号与着装",
      "action_and_combat_style": "动作与战斗风格",
      "cost_preference_and_taboos": "代价偏好与禁忌",
      "representative_equipment": [
        "代表性装备1",
        "代表性装备2"
      ]
    }
  ],
  "term_table": [
    {
      "term": "术语，例如：炼气期",
      "one_line_definition": "一句话定义，例如：修炼第一境，以吸纳天地灵气为主，尚无法独立成型",
      "visual_anchor": "视觉锚点，例如：修炼时体表有淡淡灵光流动，新手勉强可见",
      "cost_anchor": "代价锚点，例如：每次修炼至少消耗半块低品灵石",
      "typical_usage_scenario": "典型使用场景，例如：开篇阶段，主角与其他外门弟子处于同一起跑线时"
    }
  ],
  "self_check": {
    "manual_risks": [
      "手册化风险1，例如：各流派的战斗描写趋于雷同，只是换了名字，读者无法分辨谁在打谁",
      "手册化风险2，例如：术语越堆越多，但读者无法在脑中形成具体画面，成为信息噪音"
    ],
    "restraint_strategies": [
      "克制策略1，例如：每个战斗场景只允许引入1个新术语，其余均用已知概念描述",
      "克制策略2，例如：每写完一个战斗场景，检查是否能只凭视觉/动作描写判断双方所属流派"
    ]
  }
}
```

### `graph1.bible.lint`

- 说明：BIBLE全量Lint集中检查（主承诺/Lens/术语/训练基线/对手生态）
- Prompt：`graph1.bibleLint` v2.0
- 模板：`server/src/novelwb/prompts/graph1/bibleLint/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A, B, D, E, F`
- 模型：`deepseek-v4-pro`；temperature=0.3；max_tokens=3000；best_of_n=1

```jinja2
{# graph1.bibleLint v2.0 — BIBLE全量Lint #}
{% include '_shared/json_output_contract.jinja2' %}

# 角色定义

你是权威层一致性审计员。你的任务不是重写设定，而是检查 BIBLE、REG、CHAR、LEDGER、CONTRACT、MOTIF 等权威对象之间是否存在硬冲突、缺口、漂移风险，以及后续写作会踩雷的地方。

# 输入

以下输入可能包含多个权威对象，也可能只包含其中一部分。只审计输入中真实存在的对象；缺失对象记入 missing，不要自行脑补。

{{ input_pack | tojson(indent=2) }}

# 审计重点

1. 承诺一致性：main_promise、type_contract、volume_contract、事件槽位是否互相支撑。
2. 世界规则一致性：WorldA 意义系统、WorldB 生态、POW_L、POW_S、POW_E 是否存在互相推翻。
3. 角色与势力一致性：CHAR 中角色目标、关系、势力立场是否能被 BIBLE/REG 支撑。
4. 台账一致性：LEDGER 中承诺、钩子、情感债是否有 due/settled 状态，是否存在无主债。
5. 状态卡可读性：如输入已有 status_cards，检查 plot/character/scene/faction/item/rule 卡是否能支撑当前阅读，不要求全量展开。
6. 禁止变化：标出任何会让后续事件非法的 forbidden change、规则漂移或命名冲突。

# 输出JSON结构

{
  "passed": true,
  "violations": [
    "硬冲突，必须修复。格式：对象A.字段 与 对象B.字段 冲突：具体原因"
  ],
  "missing": [
    "缺失项。格式：缺少对象/字段：为什么影响后续写作"
  ],
  "drift": [
    "软风险。格式：风险位置：可能如何在后续章节漂移"
  ],
  "fix_plan": null
}

如果未通过，fix_plan 使用：

{
  "fix_level": "L0",
  "patch_instructions": [
    "可执行修复指令，只改权威对象中最小必要字段，不改事件因果"
  ],
  "target_block_ids": [],
  "rewrite_chars_hint": null,
  "reason": "选择该修复级别的原因"
}
```

### `graph2.longline.core`

- 说明：长线骨架生成（全书DQ/阶段节点/事件波形/动量债/不可回头选择/意象轨迹）
- Prompt：`graph2.longlineCore` v2.1
- 模板：`server/src/novelwb/prompts/graph2/longlineCore/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=6000；best_of_n=5

```jinja2
{# graph2.longlineCore v2.1 — 长线骨架（全书DQ/阶段节点/动量债/意象轨迹/类型契约兑现） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是长篇网络小说的总策划、主编、质检官。你的核心职责是：基于#00规格和世界A层，生成全书的长线骨架——这是整部小说的"故事脊柱"，定义了从第一事件到最终结局的核心戏剧问题(DQ)、分阶段推进节点、动量债规划和意象轨迹。骨架必须足够稳固，能支撑数百个事件，并在每个阶段明确说明类型契约如何兑现。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 每个阶段的 irrevocable_choice 表示路线确定；只有 medium/high 才要求沉重且不可逆的代价
6. complexity_profile.level=low 时必须采用单线升级结构：目标公开、因果直接、每阶段一个明确地图或赛事；key_reversals 为0-1个且不能改变系统规则或人物身份；禁止背叛、阴谋套娃、道德困境和隐藏世界真相
7. 用户禁令高于“长篇骨架”模板，不能为了制造深度违反 forbidden_mechanisms

## #00规格（核心契约）

{{ input_pack.spec00_content | tojson(indent=2) }}

## 世界A层（意义系统）

{{ input_pack.world_a_content | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] dq_promise 是否包含了"谁、在什么世界、面对什么阻碍、能否实现什么目标"四个要素
- [ ] stage_nodes 中每个阶段是否有明确路线选择；low 时不得强塞惨重代价
- [ ] motif_arc 中每个意象是否在至少3个阶段有明确的含义演化（不能只在开头和结尾出现）
- [ ] type_contract_fulfillment 是否覆盖了训练期/加压期/升维期/终局期四段
- [ ] key_reversals 数量是否符合 complexity_profile；low 时只能为0-1个直接局势变化
- [ ] self_check 的 supply_risk 是否指出了全书最容易枯竭的爽感类型

## 输出JSON结构与字段说明

{
  "dq_promise": "全书核心戏剧问题（DQ），一句话，例如：被废丹田的少年能否在这个弱肉强食的世界活下来，并亲手覆灭杀死父母的家族？",
  "total_stages": 5,
  "stage_nodes": [
    {
      "stage_index": 1,
      "stage_name": "阶段名称，例如：破茧——从废物到初窥门径",
      "volumes_span": "跨越第1-2卷",
      "key_event_type": "该阶段的核心事件类型，例如：初次胜利证明自己 / 关键盟友出现 / 反派首次正面交锋",
      "protagonist_state_start": "阶段开始时主角的状态，例如：一无所有的废物，被所有人瞧不起",
      "protagonist_state_end": "阶段结束时主角的状态，例如：小有名气，被特定人物认可，但仍远不及顶尖强者",
      "sub_question": "本阶段的子戏剧问题，例如：废物能否在宗门立足并找到突破的方向？",
      "key_nodes": [
        "台阶节点：例如——主角首次在公开场合击败同境界对手",
        "翻面节点：例如——曾经的恩人揭示自己其实是对立势力的探子"
      ],
      "event_wave_pattern": "本阶段事件波形描述，例如：前三卷高压推进（每5事件一个小胜利），中间插入两个缓冲事件展示日常，末尾蓄力爆发章末高潮",
      "momentum_delta": 3,
      "momentum_debt_strategy": "本阶段的动量债管理策略，例如：控制在3以内，利用每卷末的胜利大幅偿还，避免欠债过多拖慢节奏",
      "irrevocable_choice": "阶段路线选择；low 时可写报名比赛、进入新学院等公开选择，不要求悲剧代价",
      "opponent_evolution": "对手在本阶段如何进化，例如：从嘲讽型杂鱼升级为有组织的针对性打压",
      "motif_evolution": "该阶段意象的演化，例如：残破玉牌从装饰品变成了复仇的烙印"
    }
  ],
  "momentum_debt_cap": 5,
  "motif_arc": [
    {
      "motif": "意象名称，例如：残破玉牌",
      "stage_1_meaning": "第一阶段的含义，例如：家族的耻辱与牵挂",
      "stage_3_meaning": "第三阶段的含义，例如：复仇的契约与代价",
      "final_meaning": "全书结尾的含义，例如：放下仇恨，重新定义自我的宣言"
    }
  ],
  "key_reversals": [
    {
      "reversal_index": 1,
      "reversal_description": "关键局势变化；数量服从 complexity_profile，low 时不得使用身份反转或盟友背叛"
    }
  ],
  "type_contract_fulfillment": {
    "training_phase": [
      "训练期机制1：例如——每5事件设置一个小型胜利，主角通过努力而非运气获得",
      "训练期机制2：例如——每15事件设置一次阶段性大爽点，伴随明确的代价落地",
      "训练期机制3：例如——每卷末设置一次翻盘高潮，读者在此时感受到主角真正成长"
    ],
    "pressure_phase": [
      "加压期转折点1：例如——反派势力系统性升维，主角之前的策略全部失效",
      "加压期转折点2：例如——盟友因立场分歧出现裂痕，主角开始孤立",
      "加压期转折点3：例如——主角的核心能力遭到专门克制，需要找到新的出路"
    ],
    "upgrade_phase": [
      "升维期规则翻转1：例如——主角发现整个权力体系建立在一个谎言上，推翻规则而非遵守规则",
      "升维期规则翻转2：例如——主角曾经的弱点（禁忌体质）成为打破旧格局的关键武器"
    ],
    "finale_phase": [
      "终局期回响方式1：例如——主角在最终决战中以开篇相同的处境面对最强敌人，但结果完全不同",
      "终局期回响方式2：例如——全书所有意象种子在终局汇聚，形成情感上的完整闭环"
    ]
  },
  "self_check": {
    "supply_risk": "全书最容易枯竭的爽感类型，例如：以弱胜强的战斗爽感——随着主角变强，这类场景会越来越难以设计",
    "supply_strategy": "补充策略，例如：持续引入更强的对手，同时增加非战斗类爽感（智斗、情感满足、世界扩展），避免单一依赖战斗爽点"
  }
}
```

### `graph2.story.room`

- 说明：全书故事室深化（总纲/故事线/角色成长/物品/大场面/资产生命周期）
- Prompt：`graph2.storyRoom` v3.0
- 模板：`server/src/novelwb/prompts/graph2/storyRoom/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content, input_pack.cast_content, input_pack.longline_core, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.75；max_tokens=14000；best_of_n=2

```jinja2
{# graph2.storyRoom v2.0 - 全书故事核心，不在本步生成地图 #}
{% include '_shared/json_output_contract.jinja2' %}

你是长篇小说总编剧。长线骨架已经确定类型承诺和阶段节点，本步只深化全书故事核心：总纲因果、主要伏笔、核心角色成长线和群像关系。主要地图由下一步独立生成，不要在本输出中夹带地图清单。

## 设计原则
1. 总纲必须形成可持续推进的因果链：主角主动目标、阶段阻力、关键选择、代价、不可逆变化和终局兑现。
2. 伏笔必须有载体、误读空间、递进信息和回收窗口，禁止只有“以后揭晓”。
3. 每名主要角色必须有自己的目标与行动线，不得只围绕主角待机。
4. 成长必须通过选择、失败、关系变化和能力代价可见，不能只写心理概括。
5. low 复杂度保持直接因果和清晰目标，但人物反应、关系与爽点铺垫仍需具体。
6. 不新增无用术语、套娃阴谋和与主线无关的角色。

## 输入
规格：{{ input_pack.spec00_content | tojson(indent=2) }}

世界硬锚：{{ input_pack.world_a_content | tojson(indent=2) }}

核心角色：{{ input_pack.cast_content | default({}) | tojson(indent=2) }}

长线骨架：{{ input_pack.longline_core | tojson(indent=2) }}

复杂度：{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## 输出结构
{
  "master_story_design": {
    "central_dramatic_question": "全书核心问题",
    "story_engine": "能够持续制造目标、阻力、选择、代价与新局面的机制",
    "opening_state": "主角开篇能力、资源、关系、处境和认知",
    "inciting_change": "迫使主角行动的具体变化",
    "active_goal_chain": [
      {"stage_id": "引用长线阶段ID", "goal": "主动目标", "pressure": "主要阻力", "choice": "关键选择", "cost": "代价", "irreversible_change": "不可逆变化", "payoff": "阶段满足"}
    ],
    "main_conflict_escalation": ["冲突如何逐级扩大但保持直接因果"],
    "emotional_progression": ["主角与核心关系的分阶段情绪变化"],
    "climax_design": {"location_requirement": "留给地图步骤落实的空间要求", "choice": "终局选择", "cost": "终局代价", "promise_payoff": "类型承诺如何兑现"},
    "ending_state": "结局时能力、资源、关系、身份、认知与世界局面的变化"
  },
  "major_foreshadowing": [
    {
      "hook_id": "hook_稳定ID",
      "name": "伏笔名",
      "story_question": "制造的问题",
      "truth": "作者层真相",
      "visible_carriers": ["动作/物件/规则异常/对话缺口/场景痕迹"],
      "plant_stage_id": "首次埋设阶段",
      "reinforcement_plan": [{"stage_id": "阶段ID", "new_information": "比上次多透露的信息", "surface_interpretation": "读者当时可形成的解释"}],
      "payoff_window": "回收窗口",
      "payoff_action": "通过什么行动或后果回收",
      "involved_character_ids": ["角色ID"],
      "early_reveal_guard": "禁止提前说破的内容"
    }
  ],
  "character_growth_arcs": [
    {
      "character_id": "必须引用核心角色ID",
      "name": "角色名",
      "story_role": "全书叙事职能",
      "background_pressure": "出身与旧经历持续施加的压力",
      "external_goal": "主动追求",
      "inner_need": "真正需要改变之处",
      "desire": "欲望",
      "fear": "恐惧",
      "false_belief": "错误信念",
      "strengths": ["优势"],
      "flaws": ["会制造后果的缺点"],
      "ability_start": "初始能力边界与代价",
      "relationship_anchors": [{"other_character_id": "角色ID", "start_dynamic": "初始关系", "end_dynamic": "终局关系"}],
      "growth_stages": [{"stage_id": "阶段ID", "pressure": "压力", "choice": "选择", "cost": "代价", "behavioral_change": "可见行为变化", "ability_change": "能力变化", "relationship_change": "关系变化"}],
      "climax_choice": "终局主动选择",
      "end_state": "终局多维状态",
      "voice_markers": ["语言节奏或行为辨识点"]
    }
  ],
  "ensemble_relationship_arcs": [
    {
      "relationship_id": "rel_稳定ID",
      "character_ids": ["角色A", "角色B"],
      "start_dynamic": "初始关系",
      "shared_interest": "可合作基础",
      "core_friction": "持续摩擦",
      "turning_stages": [{"stage_id": "阶段ID", "event": "关系事件", "visible_change": "行为上的变化"}],
      "end_dynamic": "终局关系",
      "forbidden_jump": "不得无铺垫跨越的变化"
    }
  ],
  "narrative_line_registry": [
    {
      "line_id": "line_稳定ID",
      "line_type": "main / subplot / hidden / relationship / faction / item / ecology",
      "name": "故事线名",
      "owner_ids": ["主动推动该线的角色、势力或资产ID"],
      "independent_goal": "即使主角不介入，该线上的实体仍会追求什么",
      "visibility": "明线 / 暗线 / 作者层",
      "lifecycle": "seed / active / converging / paid_off / dormant / retired",
      "start_state": "开篇状态",
      "progression_stages": [{"stage_id": "长线阶段ID", "pressure": "自然发展压力", "movement": "推进、碰撞、误导或暂压", "visible_trace": "读者可见载体"}],
      "collision_line_ids": ["会发生碰撞的其他故事线ID"],
      "convergence_or_payoff": "汇流或回收方式",
      "retirement_condition": "何时可结束或转为背景"
    }
  ],
  "key_item_arcs": [
    {"item_id": "item_稳定ID", "name": "关键物品", "story_function": "线索/权力/关系/规则载体", "custody_chain": [{"stage_id": "阶段ID", "holder_id": "持有者ID", "goal": "持有者为何使用或隐藏", "state_change": "物品状态变化"}], "reveals": ["分层揭示"], "cost_or_limit": "使用代价", "payoff": "最终作用"}
  ],
  "major_set_piece_seeds": [
    {"set_piece_id": "set_稳定ID", "name": "大场面", "stage_window": "阶段窗口", "participating_line_ids": ["线ID"], "build_up_requirements": ["可跨多个事件的铺垫"], "non_protagonist_arcs": ["主角登场前后其他人物与势力的行动弧"], "spatial_requirement": "交给地图步骤落实", "aftermath_scope": ["人物、势力、地点、物件、舆论后果"]}
  ],
  "asset_lifecycle_policy": {
    "persistent": "贯穿全书资产何时必须保留",
    "volume": "卷级资产如何继承或结算",
    "transient": "过渡人物、物品、场景和线索何时创建与退休",
    "promotion": "临时资产何时升级为长期资产",
    "retirement": "退场时必须留下哪些状态和影响"
  },
  "entity_autonomy_rules": ["人物、势力、生物、物件和环境系统不得只在主角出现时行动的约束"],
  "story_room_rules": {
    "must_preserve": ["后续卷纲不得破坏的核心因果、成长边界和伏笔时序"],
    "flexible_zones": ["允许卷级调整的内容"],
    "anti_bloat_rules": ["限制无效角色、设定、支线和秘密的规则"]
  }
}
```

### `graph2.map.room`

- 说明：全书主要地图深化（区域/路线/势力/人物联系）
- Prompt：`graph2.mapRoom` v1.0
- 模板：`server/src/novelwb/prompts/graph2/mapRoom/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.spec00_content, input_pack.world_a_content, input_pack.cast_content, input_pack.longline_core, input_pack.story_room_core, input_pack.complexity_profile
- 输出：`AuthObject`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=8500；best_of_n=2

```jinja2
{# graph2.mapRoom v1.0 - 全书主要地图 #}
{% include '_shared/json_output_contract.jinja2' %}

你是长篇小说空间架构师。根据已经完成的总纲、伏笔、角色成长线和世界硬锚，建立全书主要地图系统。地图必须参与叙事因果和人物成长，不是地点名录。

## 原则
1. 先定义空间层级和阶段开放，再定义区域；不得一次开放全世界。
2. 每个主要区域必须关联角色、势力、资源、风险、规则和叙事任务。
3. 路线必须有耗时、门槛和风险，空间移动不能瞬移或无成本。
4. 人物在熟悉地、敌对地和陌生地应有不同优势、压力与行为。
5. 只生成长期反复使用或承担关键转折的主要区域；卷内小地点留给卷地图步骤。

## 输入
规格：{{ input_pack.spec00_content | tojson(indent=2) }}

世界硬锚：{{ input_pack.world_a_content | tojson(indent=2) }}

角色：{{ input_pack.cast_content | default({}) | tojson(indent=2) }}

长线骨架：{{ input_pack.longline_core | tojson(indent=2) }}

全书故事核心：{{ input_pack.story_room_core | tojson(indent=2) }}

复杂度：{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## 输出结构
{
  "major_map_system": {
    "map_progression": "空间规模如何随阶段扩大并服务成长",
    "world_hierarchy": [{"level": "城市/区域/国家等", "meaning": "叙事意义", "unlock_rule": "开放条件"}],
    "major_regions": [
      {
        "map_id": "map_稳定ID",
        "name": "区域名",
        "scale": "空间尺度",
        "parent_map_id": "父级ID；顶层为空字符串",
        "connected_map_ids": ["可达区域ID"],
        "active_stage_ids": ["主要使用阶段ID"],
        "unlock_condition": "进入条件",
        "travel_rules": ["常用路线、耗时、身份门槛和风险"],
        "physical_identity": "地形、空间结构与可行动特征",
        "social_order": "公开秩序、礼法与权力结构",
        "controlling_factions": ["势力ID"],
        "resources": ["可争夺和消耗的资源"],
        "hazards": ["自然、制度、人物或能力风险"],
        "narrative_functions": ["承担的情节、关系、成长和伏笔作用"],
        "character_connections": [{"character_id": "角色ID", "connection": "归属/创伤/利益/优势/弱点", "behavior_change_here": "在此地不同的表现"}],
        "signature_locations": [{"location_seed_id": "seed_稳定ID", "name": "标志地点", "future_volume_use": "留给哪类卷深化"}],
        "first_impression": "首次出现的小说化感知重点",
        "later_contrast": "后期重返时如何形成变化对照",
        "state_change_windows": ["哪些阶段允许区域持续改变"]
      }
    ],
    "major_routes": [
      {"route_id": "route_稳定ID", "from_map_id": "起点", "to_map_id": "终点", "travel_time": "故事内耗时", "access_condition": "开放条件", "risks": ["风险"], "character_opportunities": ["途中可承载的关系或事件"]}
    ],
    "reveal_plan": [{"stage_id": "阶段ID", "new_map_ids": ["新开放区域"], "reader_learns": "读者新增空间认知", "character_change": "人物因此发生的行动或认知变化"}],
    "continuity_rules": ["后续卷地图必须遵守的空间连续性规则"]
  }
}
```

### `graph3.volume.plan`

- 说明：分卷规划（卷契约/事件槽位表/Sequence/疲劳预警配置）
- Prompt：`graph3.volumePlan` v2.1
- 模板：`server/src/novelwb/prompts/graph3/volumePlan/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.longline_content, input_pack.carryover_context, input_pack.volume_index, input_pack.volume_id, input_pack.complexity_profile
- 输出：`VolumeContract`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E, F`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=5000；best_of_n=3

```jinja2
{# graph3.volumePlan v2.0 — 分卷规划（卷定位/卷契约/收支计划/事件序列/疲劳预警） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是分卷策划、主编、质检官。你的核心职责是：基于长线骨架，为指定卷生成具体的卷定位、卷契约、叙事收支计划、事件槽位表和疲劳预警。每个事件槽位是写作时的最小执行单元，必须清晰定义目标、产出和约束。卷规划是长线骨架与具体写作之间的桥梁，必须同时考虑读者体验（不疲劳）和叙事债务管理（不失控）。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 卷末必须有明确的结算类型，不允许卷末既不结算也不留悬念

## 长线骨架

{{ input_pack.longline_content | tojson(indent=2) }}

## 系统复杂度路由（硬约束）
{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

若 level=low：本卷保持单一主目标、直接因果和线性升级；同时活跃势力不超过3个，冲突形态1-2种，禁止灰色阵营、隐藏身份和为反转而反转。

{% if input_pack.carryover_context %}
## 上卷承接上下文

以下内容来自已发布章节、最新状态快照、角色状态与台账。规划第2卷及后续卷时必须承接这些状态，不得重置主角能力、资源、关系、伤势、未偿还钩子或世界局势。

{{ input_pack.carryover_context | tojson(indent=2) }}
{% endif %}

## 本卷信息

- 卷编号：{{ input_pack.volume_index }}
- 卷ID：{{ input_pack.volume_id }}

## 硬检查清单（输出前必须全部通过）

- [ ] volume_positioning 的 sub_question 是否是长线骨架中本阶段子问题的具体化
- [ ] volume_contract 的 breather_strategy 三个字段是否互相匹配（配额/最大连续/偿还方式）
- [ ] receipt_plan 和 debt_plan 是否平衡（不能只欠债不还，也不能一次性把所有债务还清）
- [ ] event_ngang_sequence 是否覆盖了本卷所有事件，且每个事件都有收/债标注
- [ ] fatigue_warning 的 indicators 是否按复杂度给出最小充分集；low 时2-3条即可
- [ ] event_slots 中关键事件（is_key_event=true）是否都有 forbidden_changes 约束

## 输出JSON结构与字段说明

{
  "volume_id": "{{ input_pack.volume_id }}",
  "title": "本卷标题，例如：废物崛起",
  "volume_promise": "本卷对读者的承诺（必须在卷末兑现），例如：主角从最底层出发，经历关键胜利，完成第一阶段的成长蜕变",
  "sub_question": "本卷的戏剧子问题（回答后推进主DQ），例如：废物少年能在宗门大比中活到最后吗？",
  "conflict_form_rotation": ["本卷主要冲突形态（3-4种，保持多样性），例如：一对一战斗", "团队对抗", "身份暴露危机", "资源争夺"],
  "breather_quota": 0.25,
  "max_consecutive_breather": 2,
  "momentum_debt_max": 5,
  "end_settlement_type": "卷末如何收尾，例如：大胜利 / 惨胜 / 转折 / 悬念留存",
  "promise_scenes": ["本卷必须出现的场景（3-5个），例如：主角第一次在众目睽睽下碾压昔日嘲讽者"],
  "motif_steps": ["本卷意象的具体演化步骤（2-3个）"],
  "volume_positioning": {
    "sub_question": "本卷子戏剧问题（与上方 sub_question 保持一致），例如：废物少年能在宗门大比中活到最后吗？",
    "result_target": "本卷结束时世界状态的目标描述，例如：主角完成第一次真正的以弱胜强，宗门内开始有人刮目相看",
    "main_payoff_ratio": "本卷主要爽感类型及比例，例如：战斗爽感60% + 信息揭晓30% + 情感满足10%",
    "main_cost_tone": "本卷主要代价基调，例如：以资源消耗为主（消耗丹药、暴露底牌），辅以情感代价（盟友受伤）"
  },
  "volume_contract": {
    "conflict_and_evolution": "本卷冲突的演化路径，例如：从单纯的资源争夺开始，逐渐升级为针对主角身份的存亡威胁",
    "breather_strategy": {
      "quota": "缓冲配额，例如：本卷共30事件，允许最多6个缓冲事件（20%）",
      "max_consecutive": 2,
      "repay_method": "缓冲后的偿还方式，例如：缓冲事件后下一事件必须是Advance，且需引入新的张力点"
    },
    "momentum_debt_threshold": "动量债警戒线，例如：超过4时必须在两个事件内插入偿还机制，超过5时为警报状态",
    "end_settlement_type": "卷末结算类型，例如：惨胜型——主角胜利但付出了预料外的高代价，且引出下一卷的核心危机",
    "motif_step": "本卷意象演化步骤简述，例如：残破玉牌在本卷中从私人信物变成了与盟友的共同契约"
  },
  "receipt_plan": {
    "plot_receipts": [
      {"item": "剧情收款1，例如：上卷埋下的神秘来袭者终于现身", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_005"},
      {"item": "剧情收款2，例如：主角首次展示真正实力", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_012"},
      {"item": "剧情收款3，例如：卷末大比胜利，兑现卷首承诺", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_025"}
    ],
    "emotion_receipts": [
      {"item": "情感收款1，例如：主角获得第一个真正认可自己的人", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_008"},
      {"item": "情感收款2，例如：与最初嘲讽者之间的关系翻转", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_018"},
      {"item": "情感收款3，例如：与核心盟友关系升温", "suggested_slot": "evt_vol{{ input_pack.volume_index }}_022"}
    ]
  },
  "debt_plan": {
    "hook_debts": [
      {"item": "钩子债务1，例如：神秘炼丹师的真实身份", "recovery_window": "下卷前三个事件"},
      {"item": "钩子债务2，例如：主角突破时发出的异象被谁注意到了", "recovery_window": "本卷末"},
      {"item": "钩子债务3，例如：长老的真实立场", "recovery_window": "下一卷中期"}
    ],
    "emotion_debts": [
      {"item": "情感债务1，例如：盟友因主角的决定受伤，需要和解", "recovery_window": "下卷开篇"},
      {"item": "情感债务2，例如：主角对师父的误解", "recovery_window": "本卷末"},
      {"item": "情感债务3，例如：与灰色势力之间的未解恩怨", "recovery_window": "下一阶段"}
    ],
    "overdue_redline": "逾期红线：例如：任何债务超过15个事件未处理即为逾期，必须在下一事件强制结算"
  },
  "event_ngang_sequence": [
    "事件1（收款：兑现上卷悬念X）：主角回到宗门，发现情况有变，简短适应期",
    "事件2（欠债：埋下新悬念Y）：神秘人出现，意图不明，留下钩子",
    "事件3（推进）：大比前准备，展示主角当前真实实力基线"
  ],
  "fatigue_warning": {
    "stats_period": "统计周期，例如：每10个事件统计一次",
    "indicators": [
      "冲突形态重复率：同一冲突形态连续超过3次即为警报",
      "钩子类型重复率：连续3章使用相同类型钩子即为警报",
      "缓冲比例：实际缓冲比例超过配额+5%即为警报",
      "动量债趋势：连续5个事件债务未下降即为警报",
      "角色互动多样性：同一对角色之间的互动超过5个事件未引入第三方即为警报",
      "战斗结果单调性：连续4次战斗以相同模式（主角压制/主角被压制）结束即为警报"
    ],
    "adjustment_suggestions": [
      "调整建议1：发现冲突单调时，在下一事件切换冲突类型，优先选择当前卷中使用最少的冲突形态",
      "调整建议2：发现动量债堆积时，设计一个小型胜利事件偿还债务，但不能让胜利来得太容易",
      "调整建议3：发现钩子重复时，检查本卷已有的未解线头，选一个提前兑现而非新增"
    ]
  },
  "event_slots": [
    {
      "slot_id": "evt_vol{{ input_pack.volume_index }}_001",
      "event_goal": "本事件的叙事目标（一句话），例如：主角在资源争夺中以弱胜强，获得第一件法宝",
      "result_target": "事件结束时世界的状态变化，例如：主角获得入门级法宝，与另一名弟子结下恩怨",
      "conflict_form": "冲突形态，例如：一对一战斗 / 信息博弈 / 资源抢夺",
      "key_deliverables": ["本事件必须完成的叙事交付物（2-3个），例如：展示主角的隐藏能力", "制造与反派的直接对立", "结尾留下新的悬念"],
      "is_key_event": false,
      "need_ethics_cost": false,
      "forbid_breather_dilution": false,
      "allowed_changes": [
        "允许的变化：例如：主角可以选择不同的获胜方式（正面硬拼或智取）",
        "允许的变化：例如：法宝的品质可以在低品和中品之间浮动"
      ],
      "forbidden_changes": [
        "禁止的变化：例如：不允许主角在此事件获得任何境界突破",
        "禁止的变化：例如：不允许本事件的恩怨在本事件内解决"
      ],
      "block_intent_distribution": "建议积木意图分布，例如：2个推进块 + 1个伏笔块，不建议使用缓冲块"
    }
  ]
}
```

### `graph3.volume.story_room`

- 说明：本卷故事深化（成长线/实体议程/关键物品/大场面/临时资产）
- Prompt：`graph3.volumeStoryRoom` v3.0
- 模板：`server/src/novelwb/prompts/graph3/volumeStoryRoom/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.longline_content, input_pack.volume_plan_content, input_pack.carryover_context, input_pack.complexity_profile
- 输出：`VolumeContract`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E, F`
- 模型：`deepseek-v4-pro`；temperature=0.75；max_tokens=15000；best_of_n=2

```jinja2
{# graph3.volumeStoryRoom v2.0 - 本卷故事核心与角色，不生成地图和逐事件设计 #}
{% include '_shared/json_output_contract.jinja2' %}

你是本卷故事主编和人物编剧。本步只深化卷故事引擎、卷伏笔、角色成长、卷角色卡和关系轨迹。地图与场景由下一步生成，逐事件设计由再下一步生成。

## 原则
1. 严格继承全书总纲、伏笔和成长线，只细化本卷，不得一卷耗尽全书成长。
2. 本卷角色卡必须写清背景、个性、主动目标、能力边界、当前状态、知识边界、语言和行为辨识点。
3. 新增卷角色必须有个人目标、行动能力、退出或转长期条件，不能只是工具人。
4. 卷伏笔引用全书 hook_id 或标记 volume_only，并明确本卷埋设、递进和回收。
5. 内容丰富来自具体压力、选择、反应、代价与关系变化，不来自增加秘密层数。

## 输入
全书长线与故事室：{{ input_pack.longline_content | tojson(indent=2) }}

卷纲骨架：{{ input_pack.volume_plan_content | tojson(indent=2) }}

上卷承接：{{ input_pack.carryover_context | default({}) | tojson(indent=2) }}

复杂度：{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## 输出结构
{
  "volume_story_engine": {
    "volume_center": "本卷唯一核心行动与变化",
    "opening_state": "卷首人物、关系、资源和局势",
    "causal_spine": [{"cause": "前因", "event_slot_id": "已有槽位ID", "choice": "选择", "result": "结果", "next_pressure": "新压力"}],
    "emotional_curve": ["开卷、中段、高峰、卷末的读者体验"],
    "midpoint_turn": "中点如何改变目标或代价",
    "climax_choice": "卷高潮的主动选择与代价",
    "ending_state": "卷末多维状态与下卷接口"
  },
  "volume_foreshadowing": [
    {
      "hook_id": "全书hook_id或volume_only_稳定ID",
      "purpose": "本卷作用",
      "plant_slots": ["事件槽ID"],
      "reinforce_slots": ["事件槽ID"],
      "payoff_slot": "事件槽ID或下卷窗口",
      "visible_carriers": ["具体载体"],
      "information_progression": ["每次新增信息"],
      "involved_character_ids": ["角色ID"],
      "early_reveal_guard": "不能提前说破的内容"
    }
  ],
  "volume_character_arcs": [
    {
      "character_id": "稳定角色ID",
      "name": "姓名",
      "volume_role": "本卷叙事职能",
      "start_state": "卷首能力、资源、关系、情绪和认知",
      "volume_goal": "本卷主动目标",
      "pressure_points": ["持续压力"],
      "key_choices": [{"event_slot_id": "槽位ID", "choice": "选择", "cost": "代价", "visible_change": "可见变化"}],
      "relationship_progress": ["分阶段关系变化"],
      "ability_progress": ["能力试用、受限、掌握与代价"],
      "end_state": "卷末多维状态",
      "carry_to_next_volume": "未完成部分"
    }
  ],
  "volume_cast_cards": [
    {
      "character_id": "稳定角色ID",
      "name": "姓名",
      "story_status": "主角/核心配角/对手/导师/关系锚点/功能配角",
      "background": {"origin": "出身", "faction_id": "势力ID或空字符串", "formative_experience": "塑造经历", "social_position": "社会位置与资源"},
      "personality": {"surface_traits": ["外显性格"], "inner_traits": ["内层性格"], "desire": "欲望", "fear": "恐惧", "flaw": "缺点", "value_boundary": "底线", "stress_response": "受压反应"},
      "ability": {"current_level": "当前水平", "strengths": ["优势"], "limitations": ["限制"], "signature_methods": ["辨识性手段"], "costs": ["代价"]},
      "current_state": {"location_requirement": "卷首所需空间类型", "resources": ["资源"], "condition": "身体或特殊状态", "knowledge": ["确知信息"], "blind_spots": ["未知或误解"], "relationship_positions": ["关键关系"]},
      "voice_and_presence": {"speech_rhythm": "说话节奏与策略", "habitual_actions": ["习惯动作"], "sensory_impression": "登场印象", "contrast": "与他人的鲜明差异"},
      "scene_functions": ["适合承担的场景作用"],
      "entry_slot": "首次或重新登场槽位ID",
      "exit_or_persist_condition": "退场、转场或延续条件"
    }
  ],
  "relationship_tracks": [
    {
      "relationship_id": "rel_稳定ID",
      "character_ids": ["角色A", "角色B"],
      "start_dynamic": "卷初关系",
      "friction": "摩擦来源",
      "interaction_modes": ["可轮换的互动方式"],
      "turn_slots": ["关系变化槽位ID"],
      "end_dynamic": "卷末关系",
      "forbidden_jump": "禁止无铺垫跨越"
    }
  ],
  "volume_line_ledger": [
    {"line_id": "引用全书线ID或创建vol_line_卷级ID", "line_type": "main/subplot/hidden/relationship/faction/item/ecology", "volume_goal": "本卷目标", "start_state": "卷初状态", "scheduled_movements": [{"event_slot_id": "槽位ID", "action": "推进/碰撞/误导/暂压/回收", "visible_trace": "正文载体"}], "end_state": "卷末状态", "carryover": "是否及如何带入下一卷"}
  ],
  "entity_agendas": [
    {"agenda_id": "agenda_稳定ID", "subject_id": "角色、势力、生物或组织ID", "subject_type": "character/faction/creature/ecology", "independent_goal": "不依附主角的目标", "resources": ["可调用资源"], "constraints": ["限制"], "planned_actions": [{"event_slot_id": "槽位ID", "action": "主动行动", "offscreen_possible": true, "visible_trace": "结果如何显形"}], "collision_ids": ["会碰撞的议程或故事线ID"], "fallback_action": "主角不介入时仍会采取的行动"}
  ],
  "key_item_tracks": [
    {"item_id": "物品ID", "source_arc_id": "全书关键物品ID或空", "current_holder_id": "当前持有者", "holder_goal": "为何持有", "state": "当前状态", "event_movements": [{"event_slot_id": "槽位ID", "custody_or_state_change": "持有/损坏/激活/误读/隐藏变化", "evidence_carrier": "载体"}], "knowledge_boundary": "谁知道什么", "volume_payoff_or_carryover": "卷内回收或带出"}
  ],
  "set_piece_plans": [
    {"set_piece_id": "大场面ID", "source_seed_id": "全书种子ID或空", "event_slot_ids": ["可跨多个槽位"], "build_up": [{"event_slot_id": "铺垫槽位", "development": "其他人物、势力、场地或风险如何发展"}], "parallel_fronts": ["同时发展的战线"], "spectator_arcs": ["旁观者/天骄/对手/民众的预期与受挫"], "protagonist_entry": "主角何时、为何进入；可后置", "escalation_ladder": ["逐级升级"], "aftermath": ["多实体后果"]}
  ],
  "transient_assets": [
    {"asset_id": "临时资产ID", "asset_type": "character/faction/item/scene/creature/clue", "purpose": "过渡作用", "active_slot_ids": ["槽位ID"], "promotion_condition": "升级为长期资产条件", "retirement_condition": "何时退出", "residual_effect": "退出后留下的影响"}
  ]
}
```

### `graph3.volume.map_room`

- 说明：本卷地图与场景深化
- Prompt：`graph3.volumeMapRoom` v1.0
- 模板：`server/src/novelwb/prompts/graph3/volumeMapRoom/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.longline_content, input_pack.volume_plan_content, input_pack.volume_story_core, input_pack.carryover_context, input_pack.complexity_profile
- 输出：`VolumeContract`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=9000；best_of_n=2

```jinja2
{# graph3.volumeMapRoom v1.0 - 本卷地图与场景 #}
{% include '_shared/json_output_contract.jinja2' %}

你是本卷场景统筹。只深化本卷真正会使用的已开放主要区域，建立可供人物行动、冲突、对话、观察和状态变化的卷地图与场景资产。

## 原则
1. 新地点必须引用 parent_map_id，说明进入条件、移动耗时和持续状态。
2. 地图必须结合人物：谁熟悉、谁受限、谁控制、谁会在这里暴露不同一面。
3. 地点结构必须能影响视线、调度、追逐、隐瞒、对话和冲突结果。
4. 每个地点安排 scheduled_slots；每个事件涉及的地点必须可追踪。
5. 场景资产是可复用的戏剧装置，不重复制造同功能地点。
6. map_and_character_progression 必须覆盖每个事件槽，明确至少一名角色在该空间中的优势、压力及可见反应。

## 输入
全书长线与主要地图：{{ input_pack.longline_content | tojson(indent=2) }}

卷纲：{{ input_pack.volume_plan_content | tojson(indent=2) }}

卷故事核心与角色：{{ input_pack.volume_story_core | tojson(indent=2) }}

上卷状态：{{ input_pack.carryover_context | default({}) | tojson(indent=2) }}

复杂度：{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## 输出结构
{
  "volume_map_system": {
    "active_major_map_ids": ["引用全书major_map_system中的map_id"],
    "volume_spatial_arc": "人物如何进入、熟悉、争夺、改变或离开这些空间",
    "locations": [
      {
        "location_id": "loc_稳定ID",
        "parent_map_id": "全书主要地图ID",
        "name": "地点名",
        "location_type": "地点类型",
        "access_condition": "身份、时间、事件或代价条件",
        "travel_from_previous": "常用上一个地点、路线、耗时和风险",
        "physical_layout": "影响行动、视线、隐瞒、对话和冲突的空间结构",
        "social_rules": ["礼仪、禁令、权力关系或公开规则"],
        "controlling_faction_ids": ["势力ID"],
        "resources": ["可争夺、交易、使用或消耗的资源"],
        "hazards": ["环境、制度、人物或能力风险"],
        "interactive_objects": ["可操作、破坏、隐藏、误认或作为证据的物件"],
        "sensory_identity": ["稳定而具体的感官特征"],
        "character_connections": [{"character_id": "卷角色ID", "connection": "联系", "behavior_change_here": "在此地的不同表现"}],
        "plot_functions": ["可承担的情节、关系、成长与伏笔功能"],
        "scheduled_slots": ["将使用此地的事件槽ID"],
        "start_state": "首次使用前状态",
        "planned_state_changes": [{"event_slot_id": "槽位ID", "change": "持续变化"}],
        "end_state": "卷末状态"
      }
    ],
    "route_matrix": [{"route_id": "route_稳定ID", "from_location_id": "起点", "to_location_id": "终点", "travel_time": "耗时", "availability": "开放条件", "story_opportunities": ["途中可自然发生的互动"]}],
    "spatial_continuity_rules": ["移动、时间、封锁、可见范围和地点状态规则"],
    "map_and_character_progression": [{"event_slot_id": "槽位ID", "location_id": "地点ID", "character_id": "角色ID", "spatial_advantage_or_pressure": "空间优势或压力", "visible_effect": "正文中可见表现"}]
  },
  "scene_assets": [
    {
      "scene_id": "scene_稳定ID",
      "name": "场景资产名",
      "location_id": "所属地点ID",
      "function": "适合承载的冲突和关系",
      "spatial_constraints": ["限制行动的条件"],
      "interactive_objects": ["可参与行动的物件"],
      "sensory_palette": ["具体感官资产"],
      "faction_pressure": "势力如何在此显形",
      "state_changes": ["可持续保留的变化"],
      "suggested_slots": ["适合使用的事件槽ID"]
    }
  ]
}
```

### `graph3.volume.event_designs`

- 说明：本卷逐事件中心、动态路由与按需资产引用
- Prompt：`graph3.volumeEventDesigns` v2.0
- 模板：`server/src/novelwb/prompts/graph3/volumeEventDesigns/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.longline_content, input_pack.volume_plan_content, input_pack.volume_story_core, input_pack.volume_map_room, input_pack.complexity_profile
- 输出：`VolumeContract`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, B, D, E, F`
- 模型：`deepseek-v4-pro`；temperature=0.55；max_tokens=12000；best_of_n=1

```jinja2
{# graph3.volumeEventDesigns v1.0 - 逐事件中心与资产引用 #}
{% include '_shared/json_output_contract.jinja2' %}

你是本卷执行编辑。当前输入可能只是整卷事件槽的一批窗口；为本批 `event_slots` 中的每个槽生成一条且仅一条事件设计。这里只确定事件中心、线索生命周期和按需资产引用，不预设章节字数与切章点；Graph4 会在临写前结合最新状态动态路由并多轮展开。

## 强制规则
1. event_designs 必须覆盖每个 event_slot.slot_id，不得遗漏、重复或新增槽位。
2. character_focus_ids 必须引用 volume_cast_cards.character_id，建议1-4名。
3. location_ids 必须引用 volume_map_system.locations.location_id，建议1-3处，移动事件同时列起点和终点。
4. scene_asset_ids 和 foreshadowing_ids 可以为空，但非空时必须精确引用已有ID。
5. 本事件只设一个戏剧中心；必须写内容应可落成动作、对话、发现、关系反应或后果。
6. 不在此处写通用“多用对话、加强环境”等空泛写法建议。
7. active_line_ids、entity_agenda_ids、item_track_ids、set_piece_id、transient_asset_ids 只能按本事件需要引用，不得全量加载。
8. expansion_routes 只选择真正需要在正文前展开的维度；大场面可跨多个槽位铺垫，主角不必最先登场。

## 输入
全书长线：{{ input_pack.longline_content | tojson(indent=2) }}

卷纲事件槽：{{ input_pack.volume_plan_content | tojson(indent=2) }}

卷故事核心：{{ input_pack.volume_story_core | tojson(indent=2) }}

卷地图与场景：{{ input_pack.volume_map_room | tojson(indent=2) }}

复杂度：{{ input_pack.complexity_profile | default({}) | tojson(indent=2) }}

## 输出结构
{
  "event_designs": [
    {
      "slot_id": "精确引用事件槽ID",
      "dramatic_center": "谁为了什么，在何种阻力下作出什么选择",
      "reader_payoff": "读完本事件获得的主要满足或新期待",
      "surface_goal": "本章开场人物正在主动完成的具体目标",
      "content_must_include": ["必须写到的动作、对话、发现、关系反应或后果；2-6项"],
      "content_must_mention": ["需要自然提及但不必展开的信息；0-3项"],
      "content_must_avoid": ["不能提前写、概述跳过、重复或越权揭示的内容"],
      "character_focus_ids": ["1-4个角色ID"],
      "character_scene_goals": [{"character_id": "角色ID", "scene_goal": "本章具体目标", "pressure_response": "受压时的可见反应"}],
      "location_ids": ["1-3个地点ID"],
      "scene_asset_ids": ["0-3个场景资产ID"],
      "foreshadowing_ids": ["0-4个伏笔ID"],
      "active_line_ids": ["本事件实际推进、碰撞、误导、暂压或回收的故事线ID"],
      "entity_agenda_ids": ["需要推演自主行动的议程ID"],
      "item_track_ids": ["实际作用的关键物品轨迹ID"],
      "set_piece_id": "大场面ID或null",
      "transient_asset_ids": ["本事件实际使用的临时资产ID"],
      "expansion_routes": ["plot/character/relationship/faction/item/ecology/mystery/set_piece/aftermath/ensemble中的2-6项"],
      "narrative_weight": "small/standard/large/epic，不等于章节数量或字数",
      "offscreen_required": true,
      "map_constraints": ["移动耗时、进入条件、空间限制与地点状态"],
      "foreshadow_actions": [{"hook_id": "伏笔ID", "action": "埋设/递进/回收", "visible_carrier": "正文载体"}],
      "growth_actions": [{"character_id": "角色ID", "growth_node": "推进节点", "visible_behavior": "必须通过什么选择或行为可见"}],
      "relationship_change": "本章关系是否变化以及变化幅度；无变化也要说明维持方式",
      "ending_requirement": "事件写完后必须形成的事实结果、压力、余波或新驱动力；不是强制章末钩"
    }
  ]
}
```

### `graph3.volume.fatigue_report`

- 说明：卷级疲劳报告生成（变形/钩子/Breather/MomentumDebt趋势统计）
- Prompt：`graph3.fatigueReport` v2.0
- 模板：`server/src/novelwb/prompts/graph3/fatigueReport/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.volume_plan_content, input_pack.volume_id
- 输出：`FatigueReport`；格式：`json`
- 提交：`none`；HardLint：`A`
- 模型：`deepseek-v4-pro`；temperature=0.3；max_tokens=2000；best_of_n=1

```jinja2
{# graph3.fatigueReport v2.0 — 卷级疲劳报告（冲突变形/钩子重复/Breather比例/动量债趋势） #}
{% include '_shared/json_output_contract.jinja2' %}

你是一位专注于读者体验的叙事质量分析师。分析卷规划的事件槽位序列，评估叙事疲劳风险：冲突形态单调性、钩子重复率、Breather事件分布、动量债累积趋势。输出具体的风险警告和调整建议。

输出必须只包含 FatigueReport 允许字段：chapter_range、conflict_form_ratio、advance_delta_frequency、hook_repeat_rate、breather_usage_rate、max_consecutive_breather_seen、momentum_debt_trend、recommendations、intent_rotation_advice。风险等级、警告、状态卡建议都写入 recommendations 字符串，不要新增顶层字段。

## 卷规划内容

{{ input_pack.volume_plan_content | tojson(indent=2) }}

## 卷ID

{{ input_pack.volume_id }}

## 输出JSON结构与字段说明

{
  "chapter_range": null,
  "conflict_form_ratio": {
    "一对一战斗": 0.4,
    "团队对抗": 0.2,
    "信息博弈": 0.2,
    "资源争夺": 0.2
  },
  "advance_delta_frequency": 0.6,
  "hook_repeat_rate": 0.15,
  "breather_usage_rate": 0.2,
  "max_consecutive_breather_seen": 1,
  "momentum_debt_trend": [1, 2, 3, 2],
  "recommendations": [
    "风险等级：low / medium / high；量化依据写在本条中",
    "具体警告：前5个事件均为一对一战斗，建议插入一个信息博弈场景",
    "调整建议：建议将 slot_id evt_vol1_007 改为 Breather 类型，缓解连续战斗疲劳",
    "状态卡建议：本卷事件执行时优先按情节/人物/场景/势力抽取阅读焦点，不要向单事件塞入全量设定"
  ],
  "intent_rotation_advice": "整体意图轮换建议，例如：建议采用3:1:1的Advance:Settle:Foreshadow比例，当前规划偏重Advance"
}
```

### `graph4.event.budget`

- 说明：事件预算（常规/关键分流：实体上限/解释密度/伦理代价标记）
- Prompt：`graph4.eventBudget` v3.0
- 模板：`server/src/novelwb/prompts/graph4/eventBudget/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.volume_content, input_pack.is_key_event, input_pack.context_meta
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A, B`
- 模型：`deepseek-v4-flash`；temperature=0.3；max_tokens=1000；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是长篇小说事件体量编辑。判断完成“整个叙事事件”需要多少展开空间和多少轮构思；这不是章节字数预算，事件写完后才会自然切章。不得为了适配单章而压缩铺垫、群像、反应链、大场面或余波。

参考档位：small 约2500-5000字；standard 约4500-8500字；large 约7000-10000字；epic 约9000-12000字。`total_chars` 是覆盖目标而非截断上限，正文可以因完整性自然超过。

事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
本卷契约：{{ input_pack.volume_content | tojson(indent=2) }}
关键事件：{{ input_pack.is_key_event }}
上下文：{{ input_pack.context_meta | tojson(indent=2) }}

输出：
{
  "narrative_weight": "small / standard / large / epic",
  "total_chars": 5600,
  "scene_count_hint": 4,
  "expansion_passes": 3,
  "coverage_dimensions": ["因果", "人物反应", "关系", "势力动作", "物件线索", "环境余波"],
  "max_new_entities": 3,
  "max_new_terms": 4,
  "max_explanation_density": 0.12,
  "budget_rationale": "为什么需要这个事件体量；禁止用‘一章需要’作为理由"
}
```

### `graph4.event.route`

- 说明：按事件当前状态动态选择叙事展开维度与阅读资产
- Prompt：`graph4.eventRoute` v1.0
- 模板：`server/src/novelwb/prompts/graph4/eventRoute/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.budget, input_pack.latest_snapshot, input_pack.volume_content, input_pack.context_meta
- 输出：`EventSlot`；格式：`json`
- 提交：`none`；HardLint：`A, B, G`
- 模型：`deepseek-v4-pro`；temperature=0.35；max_tokens=2500；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是事件阅读路由器。依据事件槽、最新事实状态和已裁剪资产，只选择本事件真正需要展开的叙事维度。不要为了齐全而全选，也不要默认只看主角。

可选 expansion_routes：plot、character、relationship、faction、item、ecology、mystery、set_piece、aftermath、ensemble。

输入：
事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
事件体量：{{ input_pack.budget | tojson(indent=2) }}
最新状态：{{ input_pack.latest_snapshot | tojson(indent=2) }}
本卷资产：{{ input_pack.volume_content | tojson(indent=2) }}
上下文追踪：{{ input_pack.context_meta | tojson(indent=2) }}

输出：
{
  "narrative_weight": "small / standard / large / epic",
  "expansion_routes": ["必须选择2-6项"],
  "active_line_ids": ["本事件实际推进、碰撞或暂时压住的故事线ID"],
  "entity_agenda_ids": ["本事件需要推演的角色、势力、生物或组织议程ID"],
  "asset_ids": ["需要读取的物品、生态、地点或大场面资产ID"],
  "offscreen_required": true,
  "routing_reasons": [{"route": "faction", "reason": "为什么本事件必须展开", "expected_effect": "应产生什么叙事作用"}],
  "routes_not_selected": [{"route": "未选择维度", "reason": "为什么本次不读"}]
}
```

### `graph4.event.world_pulse`

- 说明：推演人物、势力、物件与生态的自主行动
- Prompt：`graph4.worldPulse` v1.0
- 模板：`server/src/novelwb/prompts/graph4/worldPulse/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.event_route, input_pack.latest_snapshot, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content
- 输出：`EventSlot`；格式：`json`
- 提交：`none`；HardLint：`A, B, G`
- 模型：`deepseek-v4-pro`；temperature=0.55；max_tokens=4500；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是叙事世界模拟编辑。先暂时把主角移出画面，推演本事件时间窗内其他人物、势力、生物群落、关键物品持有者和场景系统会自主做什么；再指出这些行动会怎样与事件目标碰撞。只推演路由选中的资产，不新增无关支线。

事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
动态路由：{{ input_pack.event_route | tojson(indent=2) }}
最新状态：{{ input_pack.latest_snapshot | tojson(indent=2) }}
人物状态：{{ input_pack.char_content | tojson(indent=2) }}
台账：{{ input_pack.ledger_content | tojson(indent=2) }}
本卷资产：{{ input_pack.volume_content | tojson(indent=2) }}

输出：
{
  "story_time_window": "本事件覆盖的故事内时间",
  "entity_actions": [{"agenda_id": "议程ID", "subject_id": "实体ID", "goal": "自己的目标", "action": "即使主角不出现也会采取的行动", "resource_or_cost": "调用资源或代价", "visible_trace": "正文可见痕迹"}],
  "faction_movements": [{"faction_id": "势力ID", "order_or_policy": "命令/资源/制度变化", "executor": "执行者", "affected_ids": ["对象ID"]}],
  "line_movements": [{"line_id": "故事线ID", "from_state": "当前态", "pressure": "自然压力", "possible_next_state": "若无人阻止将到达的状态"}],
  "item_and_ecology_movements": [{"asset_id": "物品或生态ID", "change": "自主变化", "cause": "原因", "trace": "可被感知的痕迹"}],
  "offscreen_actions": [{"subject_id": "实体ID", "action": "场外动作", "later_evidence": "本事件中如何以消息、结果或痕迹显现"}],
  "collision_candidates": [{"participants": ["实体/故事线/资产ID"], "collision": "目标如何冲突", "narrative_value": "为什么值得写", "must_not_resolve": "本次不能一次解决什么"}]
}
```

### `graph4.event.expand`

- 说明：按路由对因果、人物、多线与场面做多轮展开
- Prompt：`graph4.eventExpand` v1.0
- 模板：`server/src/novelwb/prompts/graph4/eventExpand/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.event_route, input_pack.world_pulse, input_pack.budget, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content
- 输出：`EventSlot`；格式：`json`
- 提交：`none`；HardLint：`A, B, D, G`
- 模型：`deepseek-v4-pro`；temperature=0.68；max_tokens=7000；best_of_n=2

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是事件扩写室。把槽位目标与世界脉冲做多轮展开，先产生足够的因果、关系、信息和场面材料，再交给下一步编织。这里不是正文，也不是按章列任务；禁止把每条材料都安排成必须完成的清单。

事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
路由：{{ input_pack.event_route | tojson(indent=2) }}
世界脉冲：{{ input_pack.world_pulse | tojson(indent=2) }}
事件体量：{{ input_pack.budget | tojson(indent=2) }}
人物/台账/卷资产：{{ input_pack.char_content | tojson(indent=2) }} {{ input_pack.ledger_content | tojson(indent=2) }} {{ input_pack.volume_content | tojson(indent=2) }}

输出：
{
  "dramatic_core": "谁为了什么，因何与谁碰撞，最终必须作出什么选择",
  "expansion_passes": [
    {"pass": 1, "focus": "因果与阻力", "findings": ["展开结果"], "selected": ["保留项"], "discarded": [{"item": "舍弃项", "reason": "不服务中心"}]},
    {"pass": 2, "focus": "人物与关系", "findings": ["不同角色目标、误解、反应与选择"]},
    {"pass": 3, "focus": "明线暗线、物件、势力或生态", "findings": ["非主角线如何显形"]},
    {"pass": 4, "focus": "写法与场面", "findings": ["哪些内容应慢写、侧写、留白或拉远镜头"]}
  ],
  "line_interactions": [{"line_id": "线ID", "action": "推进/碰撞/误导/压住/回收", "visible_layer": "读者本次能看到什么", "hidden_layer": "作者层实际发生什么"}],
  "character_and_entity_material": [{"subject_id": "实体ID", "scene_goal": "自己的目标", "choice": "选择", "reaction_chain": ["即时反应", "行为后果", "余波"]}],
  "set_piece_material": {"set_piece_id": null, "build_up": ["铺垫节点"], "spectator_or_parallel_reactions": ["旁观者、对手或其他战线"], "entrance_timing": "主角何时出现；可为空", "aftermath": ["结果不能只落到主角身上"]},
  "candidate_scenes": [{"scene_purpose": "场景作用", "participants": ["实体ID"], "location": "地点", "entry_pressure": "入场压力", "turn": "转折", "exit_consequence": "离场后果", "line_ids": ["线ID"]}],
  "continuity_risks": ["需要编织步骤处理的风险"]
}
```

### `graph4.event.prewrite_check`

- 说明：正文前一致性、资产覆盖与清单化风险检查
- Prompt：`graph4.prewriteCheck` v1.0
- 模板：`server/src/novelwb/prompts/graph4/prewriteCheck/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.event_plan, input_pack.latest_snapshot
- 输出：`VerifyResult`；格式：`json`
- 提交：`none`；HardLint：`A, B, C, D, G`
- 模型：`deepseek-v4-pro`；temperature=0.2；max_tokens=2800；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是正文前一致性审校。检查事件计划是否忠于事实状态、地图、知识边界和故事线生命周期，同时判断它是否仍像“逐项完成任务”。发现问题时给出可执行的重织指令，不要重写正文。

事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
路由：{{ input_pack.event_route | tojson(indent=2) }}
世界脉冲：{{ input_pack.world_pulse | tojson(indent=2) }}
展开结果：{{ input_pack.event_expansion | tojson(indent=2) }}
事件计划：{{ input_pack.event_plan | tojson(indent=2) }}
最新状态：{{ input_pack.latest_snapshot | tojson(indent=2) }}

输出：
{
  "passed": true,
  "checks": {"causality": true, "timeline": true, "map": true, "knowledge_boundary": true, "entity_agency": true, "line_lifecycle": true, "asset_coverage": true, "non_checklist_rhythm": true},
  "issues": [{"severity": "hard / soft", "dimension": "检查维度", "problem": "具体问题", "evidence": "计划中的证据"}],
  "repair_instructions": ["重织时如何调整场景、视角、铺垫或结果"],
  "protected_strengths": ["修订时不得丢失的有效设计"]
}
```

### `graph4.event.need_fact_rag`

- 说明：真值细节需求判断（RAG触发判断，当前版本跳过联网）
- Prompt：`graph4.needFactRag` v2.0
- 模板：`server/src/novelwb/prompts/graph4/needFactRag/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A`
- 模型：`deepseek-v4-flash`；temperature=0.1；max_tokens=500；best_of_n=1

```jinja2
{# graph4.needFactRag v2.0 — RAG需求判断 #}
{% include '_shared/json_output_contract.jinja2' %}

# 角色定义

你是事实需求分诊员。当前系统默认离线写作，不能实际联网。你的任务是判断本事件是否需要外部事实、命名资料或风格素材；如果需要，给出可离线执行的替代约束和后续查询建议。

# 输入

{{ input_pack | tojson(indent=2) }}

# 判断规则

1. 只有当事件涉及真实历史、现实地理、专业技术、真实制度、具体器物细节或跨文化命名时，才标记需要 RAG。
2. 纯架空设定优先使用 BIBLE/REG/CHAR/status_cards，不触发外部事实。
3. 如果当前素材不足但可以靠降细节写法规避，给出 local_fallback。
4. 不要提出泛泛搜索词；每个 query 必须说明要解决的写作风险。
5. 输出只描述需求，不生成外部事实，不把猜测写成真值。

# 输出JSON结构

{
  "rag_required": false,
  "offline_safe": true,
  "needs": [
    {
      "need_type": "FACT_CARD / STYLE_MATERIAL / PLATFORM_CONSTRAINT / NAMECHECK",
      "priority": "low / medium / high",
      "applies_to": ["event", "block:b001", "name:某名称"],
      "risk_if_missing": "缺失会导致的具体问题"
    }
  ],
  "queries": [
    {
      "query": "后续可执行的精确查询语句",
      "purpose": "这条查询要验证什么",
      "acceptable_sources": ["官方资料", "百科资料", "专业资料"]
    }
  ],
  "local_fallback": [
    "离线写作时的规避策略，例如：避免写具体年份和真实制度名称，只写架空等价物"
  ]
}
```

### `graph4.event.plan`

- 说明：将动态多轮展开编织为连续场景与变化护栏
- Prompt：`graph4.eventPlan` v3.0
- 模板：`server/src/novelwb/prompts/graph4/eventPlan/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.budget, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.prewrite_feedback, input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content
- 输出：`EventSlot`；格式：`json`
- 提交：`none`；HardLint：`A, B, G`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=7000；best_of_n=3

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是事件编织导演。将事件槽、世界脉冲和多轮展开结果编成一个完整连续的叙事事件。场景是戏剧动作单位，不是按字数分配的正文块；不要让每个场景机械完成一项任务，不要预先决定章节边界。

## 核心规则
1. 继承 `chapter_design` 中的既定中心，但在本步统一称为 `dramatic_center`；不得为了凑交付物另换中心。
2. 主线、暗线、关系、势力、物件和生态只选路由激活者；每条线可以推进、碰撞、误导、暂压或回收，不必本次全部完成。
3. 非主角实体必须依据自己的目标行动。大场面应允许长铺垫、旁观者与平行战线反应，主角可后置登场。
4. 每个核心变化展开“触发-阻力-选择-即时反应-行为后果-余波”，但应融入场景因果，不得写成逐项打卡。
5. 明确知识边界、地图耗时、能力限制、伏笔门禁和不可越权变化。
6. 表现手法必须服务具体节点：对话有不同目标与潜台词；环境影响行动；侧写显示他人认知；内心只留给关键选择。
7. `prewrite_feedback` 非空时必须修复其中问题，同时保留 protected_strengths。

事件槽：{{ input_pack.event_slot | tojson(indent=2) }}
事件体量：{{ input_pack.budget | tojson(indent=2) }}
动态路由：{{ input_pack.event_route | tojson(indent=2) }}
世界脉冲：{{ input_pack.world_pulse | tojson(indent=2) }}
多轮展开：{{ input_pack.event_expansion | tojson(indent=2) }}
修订反馈：{{ input_pack.prewrite_feedback | default({}) | tojson(indent=2) }}
权威/人物/台账/本卷：{{ input_pack.bible_content | tojson(indent=2) }} {{ input_pack.char_content | tojson(indent=2) }} {{ input_pack.ledger_content | tojson(indent=2) }} {{ input_pack.volume_content | tojson(indent=2) }}

输出：
{
  "event_summary": {"event_hook": "直接进入压力", "dramatic_center": "唯一戏剧中心", "main_conflict": "主要冲突", "key_turn": "关键转折", "result_state": "事件完成后的事实状态"},
  "event_composition": {
    "reader_experience": "期待、满足与新问题如何变化",
    "pov_strategy": [{"scene_id": "s001", "pov_or_camera": "视角或短暂拉远", "knowledge_boundary": "可知边界", "reason": "为何使用"}],
    "line_weave": [{"line_id": "故事线ID", "function": "推进/碰撞/误导/暂压/回收", "entry_scene_id": "s001", "exit_state": "本事件后状态"}],
    "rhythm": {"slow_down": ["必须展开的选择、对话、反应或场面"], "speed_up": ["可压缩过渡"], "withhold": ["暂不解释内容"]},
    "ending_design": "先落后果和余波，再形成驱动力；不是强制章末钩"
  },
  "scenes": [
    {
      "scene_id": "s001",
      "block_intent": "Advance / Settle / Breather / Foreshadow",
      "scene_summary": "场景中实际发生什么",
      "location_id_or_name": "地点",
      "participants": ["实体ID"],
      "active_line_ids": ["线ID"],
      "scene_goal": "各方可碰撞的目标",
      "conflict": "阻力",
      "beat_chain": ["进入压力", "互动", "升级", "选择", "即时反应", "后果与余波"],
      "turn": "本场转折",
      "exit_consequence": "推动下一场的事实后果",
      "method_plan": [{"method": "对话/动作/侧写/环境/物件/有限内心/留白", "content_node": "具体节拍", "execution": "具体写法"}],
      "deliverables": ["可由正文证据验收的交付"],
      "state_card_focus": {"plot": [], "character": [], "scene": [], "faction": [], "item": [], "ecology": []}
    }
  ],
  "allowed_changes": [{"change_id": "chg001", "change": "允许变化", "trigger": "触发", "evidence": "可见证据", "must_land_in_scenes": ["s001"]}],
  "forbidden_changes": [{"forbidden_id": "forbid001", "change": "禁止变化", "reason": "原因", "check_method": "正文检查方式"}],
  "debt_handling": [{"debt": "债务", "action": "兑现/递进/延期解释", "scene_ids": ["s001"], "visible_evidence": "载体"}],
  "post_event_writeback_targets": {"line_ids": [], "agenda_ids": [], "asset_ids": [], "card_ids": []}
}
```

### `graph4.event.jit_cards`

- 说明：JIT实例化（新增要素短卡/淘汰合并清单/命名候选）
- Prompt：`graph4.jitCards` v2.1
- 模板：`server/src/novelwb/prompts/graph4/jitCards/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.block_plan, input_pack.bible_content, input_pack.char_content, input_pack.reg_content, input_pack.context_meta
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A, B, C, D`
- 模型：`deepseek-v4-flash`；temperature=0.5；max_tokens=1500；best_of_n=2

```jinja2
{# graph4.jitCards v2.0 — JIT素材卡实例化（Just-In-Time写作前准备） #}
{% include '_shared/json_output_contract.jinja2' %}

你是一位精通细节落地的场景顾问。在正式写作前，为本事件生成Just-In-Time素材卡——这些是写作时需要的即时参考信息，包括：场景环境细节、人物当前状态、新技法的具体描述、关键道具的外观和功能。素材卡必须具体、可直接在正文中使用。

JIT 卡不是全量设定库。只生成当前 event_slot 和 block_plan 真正需要读取的卡片，优先覆盖：情节推进卡、人物状态卡、场景卡、势力态势卡、道具卡、规则边界卡。每张卡都要说明 applies_to_blocks，避免把无关设定带入正文。

JIT 卡必须提供“可展开材料”，而不只是摘要：
- 场景卡：可互动的物件、空间限制、感官变化、进入和离开条件。
- 人物卡：本场目标、隐藏顾虑、可见习惯动作、对主角行动的两种可能反应。
- 势力卡：本场能调用的人手/资源/制度压力，以及不能越过的边界。
- 情节卡：本场必须推进的因果节点、不能提前兑现的部分、可留下的余波。
- 道具或规则卡：本场可见用法、代价和失败表现。

每张卡给出2-5条可直接转化为动作、对白、环境变化或后果的 details。不要生成纯背景百科。

输入已由 ContextCompiler 筛选。不得从常识补写 context_meta 未列出的项目内设定，也不得绕过人物知识边界或揭秘前置条件。

## 上下文编译追踪

{{ input_pack.context_meta | tojson(indent=2) }}

## 事件槽位

{{ input_pack.event_slot | tojson(indent=2) }}

## 块级大纲

{{ input_pack.block_plan | tojson(indent=2) }}

## BIBLE参考

{{ input_pack.bible_content | tojson(indent=2) }}

## REG参考

{{ input_pack.reg_content | tojson(indent=2) }}

## 角色设定参考

{{ input_pack.char_content | tojson(indent=2) }}

## 输出JSON结构与字段说明

{
  "cards": [
    {
      "card_type": "PLOT / CHARACTER_STATE / SCENE / FACTION / ITEM / RULE / TECHNIQUE / FACT",
      "card_id": "card_001",
      "title": "素材卡标题，例如：战斗场景环境描述",
      "content": "具体内容（可直接用于写作的细节），例如：废墟广场，中央有一口干涸的石井，四角矗立着残破的石柱，地面布满裂纹，空气中弥漫着旧日辉煌的气息。黄昏时分，落日将所有东西染成血红色。",
      "why_needed": "为什么当前事件必须读取这张卡，例如：b001-b002 都发生在该场景，环境会影响战斗调度",
      "source_basis": ["来自 event_slot.result_target", "来自 BIBLE.world_b"],
      "applies_to_blocks": ["b001", "b002"]
    },
    {
      "card_type": "CHARACTER_STATE",
      "card_id": "card_002",
      "title": "主角当前状态",
      "content": "精气神状态：刚经历了三天连续修炼，精神稍显疲惫但斗志昂扬。身体状态：右臂有轻微旧伤，剧烈运动会加重。心理状态：对即将到来的对抗既期待又有些不安。",
      "why_needed": "b001 的行动选择受伤势和心理预期影响",
      "source_basis": ["来自 CHAR.current_state", "来自 recent status card"],
      "applies_to_blocks": ["b001"]
    }
  ],
  "omitted_scope": [
    "明确说明未读取的全量设定范围，例如：未读取其他卷势力年表，因为本事件不涉及"
  ]
}
```

### `graph4.event.namecheck`

- 说明：命名去重检查（NAMECHECK证据卡，当前版本跳过联网）
- Prompt：`graph4.namecheck` v2.0
- 模板：`server/src/novelwb/prompts/graph4/namecheck/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_slot, input_pack.block_plan, input_pack.bible_content, input_pack.char_content, input_pack.reg_content, input_pack.context_meta
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A, D`
- 模型：`deepseek-v4-flash`；temperature=0.1；max_tokens=500；best_of_n=1

```jinja2
{# graph4.namecheck v2.0 — 命名去重检查 #}
{% include '_shared/json_output_contract.jinja2' %}

你是一位负责把关命名质量的编辑。检查本事件块级大纲中涉及的所有人名、地名、术语、技法名称，与已有BIBLE中的命名进行对比，识别以下问题：
1. 与已有命名高度相似（可能造成读者混淆）
2. 与禁用词列表冲突
3. 音感或含义与世界观不符
4. 与当前 status_cards 中的情节、人物、场景、势力、道具、规则卡名称冲突

只检查本事件会出现或新引入的命名，不要扫描全量设定后输出无关风险。

## 上下文编译追踪

{{ input_pack.context_meta | tojson(indent=2) }}

## 事件槽位

{{ input_pack.event_slot | tojson(indent=2) }}

## 块级大纲（包含可能的命名）

{{ input_pack.block_plan | tojson(indent=2) }}

## BIBLE中已有命名（用于去重）

{{ input_pack.bible_content | tojson(indent=2) }}

## REG中本事件相关注册实体

{{ input_pack.reg_content | tojson(indent=2) }}

## 角色设定中已有命名

{{ input_pack.char_content | tojson(indent=2) }}

## 输出JSON结构与字段说明

{
  "passed": true,
  "collisions": [
    {
      "new_name": "大纲中出现的新名称（如果有问题）",
      "conflict_type": "similar / forbidden / style_mismatch / card_collision",
      "existing_name": "与之冲突的已有名称（如适用）",
      "evidence": "造成混淆的证据，例如：读音只差一个字，且同属同一势力",
      "suggestion": "建议的替代名称"
    }
  ],
  "style_violations": [
    "命名风格违规说明（如有），例如：'约翰'这个名字与东方玄幻世界观不符"
  ],
  "checked_scope": [
    "本次实际检查的名称范围，例如：event_slot 中的新地名、block_plan 中的新招式、status_cards 中的相关势力名"
  ]
}
```

### `graph4.event.blocks.write`

- 说明：一次生成完整事件连续正文，场景ID仅用于证据回指
- Prompt：`graph4.blocksWrite` v3.0
- 模板：`server/src/novelwb/prompts/graph4/blocksWrite/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.volume_content, input_pack.event_plan, input_pack.scene_plan, input_pack.event_route, input_pack.world_pulse, input_pack.event_expansion, input_pack.budget, input_pack.jit_cards, input_pack.retry_feedback
- 输出：`EventDraft`；格式：`json`
- 提交：`event`；HardLint：`A, B, E, G`
- 模型：`deepseek-v4-pro`；temperature=0.8；max_tokens=20000；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是长篇小说正文作者。根据完整事件构思，一次写完连续事件正文。此时不要考虑一章多少字，后端会在事件完成后按自然边界切章。

## 写作原则
1. `full_text` 必须是可直接阅读的小说正文，不得出现场景标题、块标记、提纲、收据或“本场完成”等元叙述。
2. 不逐项照抄计划。计划是素材和护栏，正文靠欲望、行动、阻力、选择、反应与后果自然推进。
3. 重要选择、关系转折、群像反应、大场面铺垫和余波必须展开；赶路、重复说明和无变化过渡可以压缩。
4. 角色、势力、生物和物件都按自己的目标与规则作用。允许主角暂时离场，允许先写其他人受挫、误判或准备，再让主角在合适时机进入。
5. 明线与暗线通过行动、消息、物件痕迹、场景变化、信息差和侧面反应交织，不能由旁白一次解释完。
6. 对话必须有不同目的和潜台词；环境必须限制或改变行动；能力展示必须带边界或代价；关键后果应波及相关人物、势力和地点。
7. 不为了制造章末钩强行中断。事件应写到上游规定的结果态和必要余波完整落地。
8. `scene_receipts` 只在正文写完后填写，用短引文标出场景交付证据；不得把 scene_id 写进正文。

事件与构思：{{ input_pack.event_plan | tojson(indent=2) }}
场景编织：{{ input_pack.scene_plan | tojson(indent=2) }}
动态路由：{{ input_pack.event_route | tojson(indent=2) }}
世界脉冲：{{ input_pack.world_pulse | tojson(indent=2) }}
多轮展开：{{ input_pack.event_expansion | tojson(indent=2) }}
事件体量：{{ input_pack.budget | tojson(indent=2) }}
临时素材：{{ input_pack.jit_cards | tojson(indent=2) }}
人物/台账/本卷/规则：{{ input_pack.char_content | tojson(indent=2) }} {{ input_pack.ledger_content | tojson(indent=2) }} {{ input_pack.volume_content | tojson(indent=2) }} {{ input_pack.bible_content | tojson(indent=2) }}
重写反馈：{{ input_pack.retry_feedback | default([]) | tojson(indent=2) }}

输出：
{
  "full_text": "连续完整小说正文，不含任何内部标记",
  "scene_receipts": [
    {
      "scene_id": "s001",
      "delivered_items": [{"item": "已兑现内容", "evidence_quote": "正文短引文"}],
      "line_movements": [{"line_id": "线ID", "movement": "推进/碰撞/误导/暂压/回收", "evidence_quote": "正文短引文"}],
      "entity_actions": [{"subject_id": "实体ID", "action": "自主行动", "evidence_quote": "正文短引文"}],
      "end_state": "该场结束后的事实状态"
    }
  ],
  "event_self_check": {"result_state_landed": true, "forbidden_changes_avoided": true, "knowledge_boundaries_kept": true, "non_protagonist_agency_visible": true, "unfinished_plan_items": []}
}
```

### `graphR.material.rag`

- 说明：RAG素材卡生成（当前版本不实现）
- 状态：预留步骤，当前规范明确跳过，尚无 StepSpec、注册提示词和运行实现。

### `graphE.event.presnapshot.build`

- 说明：Pre-Event Snapshot构建（从权威层切片生成事件前状态快照）
- Prompt：`graphE.presnapshot` v2.0
- 模板：`server/src/novelwb/prompts/graphE/presnapshot/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack.event_id, input_pack.run_id, input_pack.bible_content, input_pack.char_content, input_pack.ledger_content, input_pack.recent_events, input_pack.context_meta, input_pack.context_meta.fingerprint
- 输出：`StateSnapshot`；格式：`json`
- 提交：`none`；HardLint：`A, G`
- 模型：`deepseek-v4-pro`；temperature=0.1；max_tokens=1500；best_of_n=1

```jinja2
{# graphE.presnapshot v2.0 — Pre-Event StateSnapshot构建 #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是连续性管理员、主编、质检官。你的核心职责是：在本事件开始之前，根据权威层信息和历史事件记录，生成当前世界的"事件前状态快照"（PreSnapshot）。这个快照不是全量资料库，而是"本事件阅读所需状态卡集合"：只抽取本事件读者理解和后续对账需要的情节、人物、场景、势力等卡片。快照必须精确——它是整个事件质检链的起点，任何关键遗漏都会导致后续对账失效。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 快照必须只记录已在文本中确认发生的信息，不得推断或预测
6. 状态卡可以有很多类型，但本次只输出"阅读所需"卡片；不要把所有角色、地点、势力全量搬进快照
7. 大类至少支持：情节卡、人物卡、场景卡、势力卡；道具卡、规则卡只在本事件确实需要时输出
8. 每张卡必须说明为什么本事件需要它，以及来源依据；没有来源依据的卡不要输出

## 事件信息

- 事件ID：{{ input_pack.event_id }}
- 运行ID：{{ input_pack.run_id }}

## 上下文编译追踪

{{ input_pack.context_meta | tojson(indent=2) }}

## 已知权威层与最近状态

### 世界/规则层
{{ input_pack.bible_content | tojson(indent=2) }}

### 人物层（包含当前人物状态，如果已有）
{{ input_pack.char_content | tojson(indent=2) }}

### 台账层
{{ input_pack.ledger_content | tojson(indent=2) }}

### 最近事件索引
{{ input_pack.recent_events | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] required_threads 是否覆盖了所有上一事件末尾标记为"必须承接"的线头
- [ ] due_debts 的 overdue_items 是否列出了所有已逾期（超过15事件未处理）的债务
- [ ] hard_constraint_reminders 的 taboo_and_scale 是否与当前#00规格的 forbidden_zones 保持一致
- [ ] ability_boundary 是否基于已确认的文本证据，而非推断
- [ ] open_threads 是否按优先级排序（最紧迫的排在最前）
- [ ] result_state_summary 是否能在一句话内准确描述当前局势
- [ ] reading_focus 是否只列出本事件阅读需要的卡片，而不是全量设定
- [ ] status_cards 是否覆盖本事件会用到的主要人物、势力、场景和情节线程

## 输出JSON结构与字段说明

{
  "snapshot_key": "pre_{{ input_pack.event_id }}",
  "event_id": "{{ input_pack.event_id }}",
  "context_fingerprint": "{{ input_pack.context_meta.fingerprint | default('') }}",
  "location": "主角当前所在地点（具体到场景级别），例如：青云宗外门弟子区，丙字号宿舍",
  "time_in_story": "故事内时间（模糊精确均可），例如：第三年春末，入门大比前三日",
  "resources": {
    "protagonist_qi_level": "当前修为境界，例如：炼气七层",
    "spirit_stones": "灵石数量（如有台账记录），例如：37枚低品灵石",
    "key_items": ["当前持有的关键道具（列表）"]
  },
  "hp": {
    "protagonist": "主角状态，例如：右臂旧伤未愈，影响力量输出约20%",
    "key_npcs": {}
  },
  "ability_boundary": [
    "当前已确认可用的能力（3-5条），例如：可稳定释放炼气七层级别攻击",
    "例如：尚未掌握飞行法术，移动依赖步行"
  ],
  "relationship_state": {
    "ally_A_name": "关系状态，例如：互相信任，已结成临时同盟",
    "rival_B_name": "关系状态，例如：公开对立，上次冲突中主角获胜"
  },
  "entity_states": {
    "char_protagonist_001": {
      "name": "角色名",
      "role": "主角 / 队友 / 对手 / 旁观者",
      "location": "当前可确认位置",
      "hp": "当前身体状态",
      "resources": {},
      "ability_boundary": [],
      "state_summary": "本事件阅读所需状态摘要"
    }
  },
  "open_threads": [
    "当前尚未解决的叙事线程（按优先级列出），例如：父母失踪之谜尚未有任何线索",
    "例如：上一事件中神秘人的身份悬而未决"
  ],
  "result_state_summary": "本快照的一句话总结，例如：主角处于短暂平静期，正在休整准备大比，但多条危机线索正在汇聚",
  "reading_focus": [
    {
      "focus_id": "focus_001",
      "card_type": "情节卡 / 人物卡 / 场景卡 / 势力卡 / 道具卡 / 规则卡",
      "card_id": "char_protagonist_001",
      "why_needed": "为什么本事件阅读需要这张卡，例如：本事件会让主角与赵铁心发生试探性谈判",
      "priority": "high",
      "requested_fields": ["current_state", "constraints", "character_knowledge"]
    }
  ],
  "status_cards": {
    "plot_cards": [
      {
        "card_id": "plot_thread_001",
        "card_type": "plot",
        "card_name": "父母失踪线",
        "subject_id": "plot_thread_001",
        "summary": "这条情节线的阅读所需摘要",
        "current_state": "当前读者已知状态，一到三句，只写已确认事实",
        "reader_needs": ["本事件阅读需要知道的点，例如：这条线已拖延过久，本事件至少要给一个新触点"],
        "reader_knowledge": ["读者已经确认的事实"],
        "character_knowledge": {},
        "open_questions": ["仍未解决的问题"],
        "source_refs": [{"authority": "LEDGER", "path": "open_threads", "evidence": "已确认来源依据"}],
        "source_version": 1,
        "last_touched_event_id": null,
        "revelation_gate": null,
        "attributes": {}
      }
    ],
    "character_cards": [
      {
        "card_id": "char_protagonist_001",
        "card_type": "character",
        "card_name": "角色名",
        "subject_id": "char_protagonist_001",
        "summary": "该角色与本事件有关的阅读摘要",
        "current_state": "身体、资源、能力、心理压力的阅读所需摘要",
        "constraints": ["能力边界、伤势、誓言、资源限制等"],
        "reader_needs": ["本事件读者必须知道的点"],
        "reader_knowledge": [],
        "character_knowledge": {
          "char_protagonist_001": {
            "known_facts": ["角色已经确认的事实"],
            "suspicions": ["角色只能怀疑的内容"],
            "blind_spots": ["角色仍不知道的内容"]
          }
        },
        "open_questions": [],
        "source_refs": [{"authority": "CHAR", "path": "character_states.char_protagonist_001", "evidence": "已确认来源依据"}],
        "source_version": 1,
        "last_touched_event_id": null,
        "revelation_gate": null,
        "attributes": {"role": "主角 / 队友 / 对手 / 旁观者 / 暂时离场", "location": "当前可确认位置", "relationship_edges": ["与其他关键角色的当前关系"]}
      }
    ],
    "scene_cards": [
      {
        "card_id": "scene_001",
        "card_type": "scene",
        "card_name": "场景名",
        "current_state": "场景当前状态，例如：外门广场封锁，执法堂弟子巡逻",
        "active_props": ["本事件会影响阅读的物件、痕迹、地形"],
        "constraints": ["场景规则或风险"],
        "source": "已确认来源"
      }
    ],
    "faction_cards": [
      {
        "card_id": "faction_001",
        "card_type": "faction",
        "card_name": "势力名",
        "stance": "对主角/事件的当前立场",
        "visible_power": "读者已知的可见力量或资源",
        "current_goal": "本事件相关目标，只写已知事实",
        "constraints": ["该势力不能/不敢直接做什么"],
        "source": "已确认来源"
      }
    ],
    "item_cards": [],
    "rule_cards": []
  },
  "required_threads": [
    {
      "thread_id": "必须承接的线头ID，例如：thread_mysterious_elder_001",
      "one_line": "线头内容一句话，例如：上事件末尾神秘长老留下的暗示必须在本事件内响应"
    }
  ],
  "due_debts": {
    "overdue_items": [
      {
        "id": "债务ID，例如：debt_missing_parents_001",
        "what_to_do": "本事件必须处理的内容，例如：至少提供一条新线索，不允许再拖延"
      }
    ],
    "deferred_items": [
      {
        "id": "延期债务ID，例如：debt_sect_elder_secret_003",
        "must_explain_deferral": "延期原因说明，例如：本事件聚焦战斗，无合理场景处理此债，计划在下一事件冒险前揭示"
      }
    ]
  },
  "hard_constraint_reminders": {
    "taboo_and_scale": "当前生效的禁忌词与尺度约束提醒，例如：禁止使用'突然获得神秘传承'类情节；战斗场面不可超过30%；本事件为关键事件，禁止使用缓冲写法",
    "breather_quota_and_momentum_status": "当前缓冲配额与动量债状态，例如：本卷已用缓冲3/6，当前动量债为3（安全线以下），允许一个缓冲事件但不建议连续"
  },
  "self_check": {
    "easily_ignored": [
      "最容易被忽略的连续性细节1，例如：主角右臂旧伤——上事件已明确描写，本事件必须在战斗时体现",
      "最容易被忽略的连续性细节2，例如：盟友离开的借口——上事件给出了理由，本事件开始时必须与之一致"
    ],
    "reminder_passwords": [
      "快检口令1：所有人物当前都在他们上一次出现的地方吗？",
      "快检口令2：上一事件末尾留下的悬念，本事件有没有在开篇响应？"
    ]
  }
}
```

### `graphE.event.extract`

- 说明：从正文抽取多实体状态、故事线、议程、资产生命周期与时间线变化
- Prompt：`graphE.extract` v3.0
- 模板：`server/src/novelwb/prompts/graphE/extract/prompt.jinja2`
- 输入：`EventDraft`；变量：input_pack.event_id, input_pack.pre_snapshot, input_pack.draft_text, input_pack.context_meta
- 输出：`ObservedDelta`；格式：`json`
- 提交：`none`；HardLint：`A, G`
- 模型：`deepseek-v4-pro`；temperature=0.2；max_tokens=6500；best_of_n=1

```jinja2
{# graphE.extract v2.0 — Post-Event Extract（从正文抽取实际变化） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是信息抽取官、连续性管理员、质检官。你的核心职责是：仔细阅读本事件的正文草稿，与事件前状态快照对比，抽取本事件实际发生的所有状态变化。这是对账的基础数据，必须准确——不要添加正文中没有的内容，不要遗漏正文中明确发生的变化。抽取必须覆盖正文触碰到的情节卡、人物卡、场景卡、势力卡、资源变化、关系迁移、规则使用、新实体、新线头等观察维度。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. change_list 中的每条变化必须注明是否为允许变化/禁止违规/计划外变化
6. 只抽取正文中已经发生的事实；没有正文证据的内容不得写入 state_after、changed_items、new_entities 或 open_threads_update
7. 每条变化必须标注 source_scene_id，并给出正文短引文；场景ID来自事件计划与收据，不要求正文出现内部标记。无法定位时填写"跨场景"并说明
8. 状态快照要采用"继承 + 覆盖"原则：正文没有改变的状态沿用 pre_snapshot，不要擅自清空或改写
9. 状态卡更新采用"触碰才更新"原则：只更新正文实际改变、确认或新增的卡；不要全量重写所有卡
10. 如果正文首次引入重要人物、势力、场景或情节线，必须创建对应 card_updates，并在 state_after.status_cards 中加入或更新该卡
11. 任何在正文中有具名对白、主动行为、关键反应或造成阻力的人物，都属于“被触碰人物”，必须创建或更新人物卡；不能只更新主角
12. 势力通过成员命令、资源调动、制度限制、声望压力或公开立场实际作用于场景时，必须创建或更新势力卡；仅被随口提及则不更新
13. 场景发生了封锁、破坏、占领、暴露、规则变化或新增可持续互动资产时，必须更新场景卡；只发生普通经过则不制造冗余卡
14. card_updates 是字段级补丁，state_after.status_cards 是事件后的可读投影；两者必须覆盖相同的被触碰对象，不能只写投影不写补丁
11. 所有人物状态统一写入 entity_states，以实体ID为键；不得只维护主角。location/resources/hp 等旧字段只作为兼容摘要
12. card_updates 必须使用 create/update/retire，并提供 changed_fields、完整 card、evidence；没有正文短证据就不得生成补丁
13. 正文发生信息获知或揭秘时，必须更新 character_knowledge，并在补丁 revealed_to 中列出实际获知者；不得把读者知识自动复制给角色
14. 故事线、实体议程、关键物品、临时资产和大场面只按正文事实更新生命周期；计划中想发生但正文未发生的内容写入 plan_adjustment_requests，不能伪造为已发生事实
15. 正文后的状态回写必须覆盖相关人物、势力、场景、物品、生态与时间线，不得只回写主角

## 上下文编译追踪

{{ input_pack.context_meta | tojson(indent=2) }}

## 事件ID

{{ input_pack.event_id }}

## 事件前状态快照（PreSnapshot）

{{ input_pack.pre_snapshot | tojson(indent=2) }}

## 事件正文草稿

{{ input_pack.draft_text }}

## 硬检查清单（输出前必须全部通过）

- [ ] change_list 是否覆盖了所有人物状态、资源、关系、能力的变化
- [ ] 每条 change_list 条目是否都有 evidence_quote（正文引文，不超过两句话）
- [ ] entity_changes 是否检查了新实体的命名冲突风险
- [ ] new_threads 是否列出了本事件新产生的所有悬念或未解决问题
- [ ] result_state_one_line 是否准确概括了本事件的最终状态
- [ ] momentum_debt_delta 是否有合理依据（爽感/代价的比值变化）
- [ ] 每条变化是否都能回指到块号和正文证据
- [ ] 是否避免把计划目标、设定推测、作者意图误当成已经发生的事实
- [ ] card_updates 是否只包含正文触碰到的卡片变化
- [ ] 人物、势力、场景、情节四类是否按阅读需要更新，而不是只更新主角
- [ ] 每个有具名对白、主动行为、关键反应或造成阻力的人物是否都有对应人物卡更新
- [ ] 通过人员、资源、命令或制度压力实际介入的势力是否有势力卡更新

## 输出JSON结构与字段说明

{
  "state_after": {
    "snapshot_key": "post_{{ input_pack.event_id }}",
    "event_id": "{{ input_pack.event_id }}",
    "location": "事件结束时主角所在地点",
    "time_in_story": "事件结束时的故事内时间",
    "resources": {
      "protagonist_qi_level": "修为是否有变化（如果正文中有突破描写则更新，否则与快照一致）",
      "spirit_stones": "灵石数量（如有增减则更新）",
      "key_items": ["事件后持有的关键道具"]
    },
    "hp": {
      "protagonist": "事件后主角受伤/痊愈情况（仅记录正文中明确描写的）"
    },
    "ability_boundary": ["事件后已确认的能力边界（如有新能力首次展示则添加）"],
    "relationship_state": {
      "角色名": "关系变化（仅记录正文中明确发生的）"
    },
    "entity_states": {
      "char_001": {
        "name": "角色名",
        "role": "主角 / 队友 / 对手 / 旁观者",
        "location": "事件后可确认位置",
        "hp": "事件后身体状态",
        "resources": {},
        "ability_boundary": [],
        "state_summary": "只写正文证据支持的状态摘要"
      }
    },
    "narrative_line_states": {"line_001": {"lifecycle": "active", "current_state": "正文后事实状态", "last_movement": "推进/碰撞/误导/暂压/回收", "evidence": "正文短引文"}},
    "entity_agendas": {"agenda_001": {"subject_id": "实体ID", "goal": "仍在追求的目标", "last_action": "本事件实际行动", "next_pressure": "由事实产生的下一压力"}},
    "asset_states": {"item_001": {"asset_type": "item/faction/scene/ecology/set_piece/transient", "lifecycle": "active/dormant/promoted/retired", "holder_or_controller": "持有或控制者", "current_state": "事实状态"}},
    "timeline_events": [{"time": "故事内时间", "location": "地点", "actor_ids": ["实体ID"], "event": "已发生事实", "evidence": "正文短引文"}],
    "open_threads": ["事件后仍未解决的线程，加上本事件新产生的悬念"],
    "result_state_summary": "事件结束状态的一句话总结",
    "reading_focus": [
      {
        "focus_id": "focus_001",
        "card_type": "情节卡 / 人物卡 / 场景卡 / 势力卡 / 道具卡 / 规则卡",
        "card_id": "char_protagonist_001",
        "why_needed": "下一事件仍需阅读的原因；如果后续不需要，可不保留",
        "priority": "high",
        "requested_fields": ["current_state", "constraints", "character_knowledge"]
      }
    ],
    "status_cards": {
      "plot_cards": [
        {
          "card_id": "plot_thread_001",
          "card_type": "plot",
          "card_name": "情节线名",
          "subject_id": "plot_thread_001",
          "summary": "后续阅读所需的一句话摘要",
          "current_state": "事件后读者已知状态，只写正文证据支持的内容",
          "reader_needs": ["后续阅读需要知道的点"],
          "reader_knowledge": ["读者已经明确知道的事实"],
          "character_knowledge": {
            "char_001": {
              "known_facts": ["该角色已经确认的事实"],
              "suspicions": ["该角色仅仅怀疑的内容"],
              "blind_spots": ["该角色仍不知道的关键点"]
            }
          },
          "open_questions": ["仍未解决的问题"],
          "source_refs": [{"authority": "EVENT", "event_id": "{{ input_pack.event_id }}", "path": "b003", "evidence": "正文短引文"}],
          "source_version": 1,
          "last_touched_event_id": "{{ input_pack.event_id }}",
          "revelation_gate": null,
          "attributes": {"last_touched_block": "b003"}
        }
      ],
      "character_cards": [
        {
          "card_id": "char_001",
          "card_type": "character",
          "card_name": "角色名",
          "subject_id": "char_001",
          "summary": "该角色对后续阅读最重要的一句话",
          "current_state": "事件后身体、资源、能力、心理压力的阅读所需摘要",
          "constraints": ["事件后仍有效的限制"],
          "reader_needs": ["后续阅读为什么需要该角色"],
          "reader_knowledge": [],
          "character_knowledge": {},
          "open_questions": [],
          "source_refs": [{"authority": "EVENT", "event_id": "{{ input_pack.event_id }}", "path": "b002", "evidence": "正文短引文"}],
          "source_version": 1,
          "last_touched_event_id": "{{ input_pack.event_id }}",
          "revelation_gate": null,
          "attributes": {"role": "主角 / 队友 / 对手 / 旁观者 / 暂时离场", "location": "事件后可确认位置", "relationship_edges": ["事件后关系状态"]}
        }
      ],
      "scene_cards": [],
      "faction_cards": [],
      "item_cards": [],
      "rule_cards": []
    }
  },
  "changed_items": [
    "发生变化的具体条目（精确描述），例如：主角获得了一枚品质不明的戒指"
  ],
  "new_entities": [
    "本事件中首次出现的新实体（人/地/物），例如：赵铁心（外门长老，中立态度）"
  ],
  "has_bridge_segment": false,
  "result_state_summary": "整体变化的一句话摘要",
  "result_state_one_line": "一句话状态结论，例如：主角险胜，但付出重创代价，神秘敌人身份暴露了一半",
  "open_threads_update": ["新增的开放线程"],
  "momentum_debt_delta": 0,
  "card_updates": {
    "plot_cards": [
      {
        "patch_id": "patch_plot_thread_001",
        "operation": "update",
        "card_id": "plot_thread_001",
        "card_type": "plot",
        "changed_fields": ["current_state", "reader_knowledge", "open_questions"],
        "card": {
          "card_id": "plot_thread_001",
          "card_type": "plot",
          "card_name": "情节线名",
          "subject_id": "plot_thread_001",
          "summary": "后续阅读所需摘要",
          "current_state": "只写正文证据支持的事件后状态",
          "reader_knowledge": ["本事件新确认的读者事实"],
          "open_questions": ["仍未解决的问题"],
          "source_refs": [{"authority": "EVENT", "event_id": "{{ input_pack.event_id }}", "path": "b003", "evidence": "正文短引文"}],
          "source_version": 2,
          "last_touched_event_id": "{{ input_pack.event_id }}"
        },
        "evidence": ["b003：正文短证据，不超过两句"],
        "revealed_to": [],
        "base_version": 1,
        "new_version": 2
      }
    ],
    "character_cards": [
      {
        "patch_id": "patch_char_001",
        "operation": "update",
        "card_id": "char_001",
        "card_type": "character",
        "changed_fields": ["current_state", "character_knowledge"],
        "card": {
          "card_id": "char_001",
          "card_type": "character",
          "card_name": "角色名",
          "subject_id": "char_001",
          "summary": "事件后人物阅读摘要",
          "current_state": "只写正文证据支持的状态",
          "constraints": ["仍有效的能力、伤势或资源限制"],
          "character_knowledge": {
            "char_001": {"known_facts": ["本事件确认的新事实"], "suspicions": [], "blind_spots": []}
          },
          "source_refs": [{"authority": "EVENT", "event_id": "{{ input_pack.event_id }}", "path": "b002", "evidence": "正文短引文"}],
          "source_version": 2,
          "last_touched_event_id": "{{ input_pack.event_id }}"
        },
        "evidence": ["b002：正文短证据，不超过两句"],
        "revealed_to": ["char_001"],
        "base_version": 1,
        "new_version": 2
      }
    ],
    "scene_cards": [],
    "faction_cards": [],
    "item_cards": [],
    "rule_cards": []
  },
  "narrative_line_updates": [{"line_id": "线ID", "operation": "advance/collide/misdirect/hold/payoff/dormant/retire", "before": "事件前状态", "after": "正文后状态", "source_scene_id": "s001", "evidence_quote": "正文短引文"}],
  "entity_agenda_updates": [{"agenda_id": "议程ID", "subject_id": "实体ID", "action": "实际行动", "goal_state": "目标是否推进或受挫", "next_pressure": "下一压力", "source_scene_id": "s001", "evidence_quote": "正文短引文"}],
  "asset_lifecycle_updates": [{"asset_id": "物品/场景/势力/生态/大场面/临时资产ID", "asset_type": "类型", "operation": "update/promote/dormant/retire", "after": "事件后状态", "source_scene_id": "s001", "evidence_quote": "正文短引文"}],
  "timeline_updates": [{"time": "故事内时间", "location": "地点", "actor_ids": ["实体ID"], "event": "事实", "source_scene_id": "s001", "evidence_quote": "正文短引文"}],
  "plan_adjustment_requests": [{"target_id": "未来计划或资产ID", "reason": "正文事实与原计划产生偏差", "suggested_adjustment": "后续重规划建议；不得在此直接改权威规划"}],
  "change_list": [
    {
      "change_content": "变化内容描述，例如：主角修为从炼气六层突破至炼气七层",
      "source_scene_id": "s002",
      "evidence_quote": "正文引文（最多两句话），例如：'丹田中的灵气突然涌动，一道金光从天灵盖冲天而起……'",
      "is_allowed": "allowed_change",
      "confidence": "high",
      "state_field": "resources.protagonist_qi_level"
    },
    {
      "change_content": "变化内容描述，例如：主角在无事前铺垫的情况下突然获得了某种特殊传承",
      "source_scene_id": "s003",
      "evidence_quote": "正文引文，例如：'一道神秘光芒射入他的意识，一套绝世功法的残卷凭空出现……'",
      "is_allowed": "forbidden_violation",
      "confidence": "high",
      "state_field": "ability_boundary"
    }
  ],
  "entity_changes": {
    "new_entities": [
      {
        "id": "实体ID，例如：npc_zhao_tiexin_001",
        "one_line": "一句话描述，例如：赵铁心，外门长老，态度中立偏善，可能成为潜在线人",
        "has_naming_collision_risk": false
      }
    ],
    "merge_or_deprecate": ["需要合并或废弃的旧实体记录，例如：'神秘黑衣人'与新出场的'影楼暗使'实为同一人，合并为entity_shadow_envoy_001"],
    "new_term_specs": [
      {
        "term": "新术语，例如：封脉针",
        "visual": "视觉描述，例如：三寸银针，刺入穴位后会发出轻微蓝光",
        "cost": "代价说明，例如：被刺者三日内无法运功，强行破除会损伤经脉"
      }
    ]
  },
  "new_threads": [
    "本事件新开启的叙事线头，例如：赵铁心在离开前留下的半句话暗示他认识主角的父亲"
  ],
  "extraction_warnings": [
    "抽取不确定项，例如：某处没有块标记，或证据只能弱支持变化"
  ]
}
```

### `graphE.event.reconcile`

- 说明：多实体、故事线、资产生命周期与正文证据的Reconcile对账
- Prompt：`graphE.reconcile` v3.0
- 模板：`server/src/novelwb/prompts/graphE/reconcile/prompt.jinja2`
- 输入：`ObservedDelta`；变量：input_pack.event_id, input_pack.draft_text, input_pack.pre_snapshot, input_pack.observed_delta, input_pack.run_id, input_pack.context_meta
- 输出：`DiffReport`；格式：`json`
- 提交：`none`；HardLint：`A, B, C, D, E, G`
- 模型：`deepseek-v4-pro`；temperature=0.2；max_tokens=5000；best_of_n=1

```jinja2
{# graphE.reconcile v2.0 — Reconcile对账（深度规则检查 + 修复方案） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是对账官、质检官、修复策略制定者。你的核心职责是：对事件草稿进行深度对账检查——对比事件前快照和提取到的变化，判断是否存在规则违反、状态跳变、动量债溢出等问题。你的检查结果将决定这一事件是否能通过审核入库。如果不通过，你必须给出具体的分级修复方案，让写作者知道如何以最小代价修复问题。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：发现任何以下问题立即标记为不通过，不允许通融
4. 所有字段必须有实质内容，如果某项无问题则填写"无"，不允许留空
5. 每个不通过项必须给出正文证据、状态证据或缺失证据；不能只写判断结论
6. fix_level_suggested 只能是 null、"L0"、"L1"、"L2" 四种之一
7. patch_instructions 必须是写作者能直接执行的最小修复动作，不能写"优化节奏"、"加强描写"这类空话
8. 如果 ObservedDelta 声称发生变化但正文证据不足，优先标为 unbridged_state_jump 或 soft_defects，不要默认通过
9. status_cards、card_updates、故事线、实体议程和资产生命周期更新必须遵守"正文触碰才更新"原则；无证据新增、删除或改写视为状态跳变
10. context_fingerprint 必须与本次 context_meta.fingerprint 一致；发现模型使用未加载设定时，记入 rule_drift
11. 检查 character_knowledge 与 revelation_gate：角色越权知情、前置伏笔不足或提前揭秘，记入 unbridged_state_jump 并判定不通过

## 上下文编译追踪

{{ input_pack.context_meta | tojson(indent=2) }}

## 事件ID

{{ input_pack.event_id }}

## 事件正文草稿

{{ input_pack.draft_text }}

## 事件前快照（PreSnapshot）

{{ input_pack.pre_snapshot | tojson(indent=2) }}

## 实际变化（ObservedDelta）

{{ input_pack.observed_delta | tojson(indent=2) }}

## 对账检查项目（硬性不通过条件）

1. **violated_forbidden**：正文中是否使用了BIBLE中的禁忌词或违反了力量定律——任何一条即不通过
2. **unbridged_state_jump**：主角或重要NPC的状态是否出现了无合理过渡的跳变——任何一条即不通过
3. **missing_due_debts**：是否有已到期（超过15事件）的台账债务没有在本事件中处理——任何一条即不通过
4. **name_collision**：是否出现了与已有实体混淆的新命名——任何一条即不通过
5. **rule_drift**：力量系统的使用是否符合已建立的定律和结构规则——任何一条即不通过
6. **momentum_overflow**：动量债是否超过上限——超过即不通过
7. **card_update_drift**：情节卡、人物卡、场景卡、势力卡是否被无证据改写、全量重写或遗漏关键正文变化——严重者不通过
8. **knowledge_boundary_drift**：角色是否说出 blind_spots 中的内容，或在无获知证据时新增 known_facts——任何一条即不通过
9. **revelation_gate_drift**：揭秘是否满足前置事实、伏笔和允许知情者——任何一条即不通过

## 修复等级选择

- L0：边界补丁。只需要在正文锚点附近补一小段过渡、代价、证据或延期解释。
- L1：局部回滚。需要重写一到两个场景或连续文本范围，才能移除违规变化或补足缺失债务。
- L2：整事件回滚。事件目标、关键转折或结果态本身越界，局部修补会继续污染权威层。

优先选择能解决问题的最低等级；不要为了稳妥滥用 L2。

## 输出JSON结构与字段说明

{
  "event_id": "{{ input_pack.event_id }}",
  "run_id": "{{ input_pack.run_id }}",
  "violated_forbidden": ["违反禁忌的具体描述（如有）"],
  "missing_due_debts": ["未处理的到期债务（如有）"],
  "unbridged_state_jump": ["无过渡的状态跳变（如有），要引用具体正文片段"],
  "name_collision": ["命名冲突（如有）"],
  "rule_drift": ["规则漂移描述（如有）"],
  "momentum_overflow": false,
  "passed": true,
  "fix_level_suggested": null,
  "patch_instructions": ["如果不通过，给出带正文短锚点或场景ID的最小修复指令，例如：在‘他抬起右臂’之后补出旧伤反噬及停止追击的因果"],
  "soft_defects": ["不影响通过但建议改进的问题"],
  "evidence_table": [
    {
      "issue_type": "禁忌违规 / 到期债务缺失 / 状态跳变 / 命名冲突 / 规则漂移 / 动量债溢出 / 软缺陷",
      "source_scene_id": "s002或跨场景",
      "evidence_quote": "正文证据或缺失说明，不超过两句",
      "why_it_matters": "为什么这会影响连续性、权威层或读者理解",
      "minimal_fix": "最小修复动作"
    }
  ],
  "card_update_audit": [
    {
      "card_type": "情节卡 / 人物卡 / 场景卡 / 势力卡 / 道具卡 / 规则卡",
      "card_id": "char_001",
      "passed": true,
      "source_scene_id": "s002或跨场景",
      "evidence_quote": "支持这张卡更新的正文证据；若无证据，说明缺失",
      "problem": "无问题 / 无证据更新 / 遗漏更新 / 全量重写 / 命名冲突",
      "minimal_fix": "若有问题，给出最小修复动作"
    }
  ],
  "repair_level_recommendation": {
    "level": "L0",
    "reasons": [
      "选择此修复级别的原因1，例如：只有局部描写违规，整体结构完整",
      "选择此修复级别的原因2，例如：违规内容可以在不改动上下文的情况下直接替换",
      "选择此修复级别的原因3，例如：核心剧情转折点未受影响"
    ],
    "minimal_repair_steps": [
      "最小修复步骤1（最优先），例如：删除第三段中'突然获得传承'的描写，改为通过努力解锁",
      "最小修复步骤2，例如：在第五段补充主角受伤后的明显行动限制",
      "最小修复步骤3，例如：在章末添加两句话触及已逾期债务线索"
    ],
    "patch_target_location": "L0修补的目标位置，例如：第三段第二句至第四句",
    "patch_content_items": [
      "L0修补内容1，例如：将'传承突然涌现'改为'在极度危机下意外触发了早年师父留下的封印记忆'",
      "L0修补内容2，例如：在追逐段落添加一句'右臂的旧伤在这一刻刺痛地提醒了他'"
    ]
  }
}

注：当 repair_level_recommendation.level 为 L1 时，额外输出：
"text_ranges_to_redo": [{"start_anchor": "起始短引文", "end_anchor": "结束短引文", "scene_id": "s002"}],
"scenes_to_keep": ["可保留场景ID"],
"bridge_reconnect_method": "重写部分与保留部分之间的衔接方式"

当 repair_level_recommendation.level 为 L2 时，额外输出：
"must_hold_forbidden": ["重写时绝对不能出现的内容（3条）"],
"must_complete_receipts": ["重写时必须兑现的叙事收款（3条）"],
"must_land_cost": "重写时必须落地的代价（1条最关键的）"
```

### `graphE.event.fix`

- 说明：无标记连续正文的锚点/场景级分级修复（L0/L1/L2）
- Prompt：`graphE.fix` v3.0
- 模板：`server/src/novelwb/prompts/graphE/fix/prompt.jinja2`
- 输入：`DiffReport`；变量：input_pack.event_id, input_pack.draft_text, input_pack.violations, input_pack.fix_level, input_pack.patch_instructions
- 输出：`EventDraft`；格式：`json`
- 提交：`none`；HardLint：`A, B, G`
- 模型：`deepseek-v4-pro`；temperature=0.7；max_tokens=16000；best_of_n=1

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是小说连续性修改编辑。根据修复级别修改完整事件正文，并始终返回一份无内部标记、可直接阅读的连续全文。

- L0：在明确文本锚点附近补写或替换200-800字的过渡、代价、证据或延期解释，不改变事件主体。
- L1：重写一个或两个有问题的场景/文本范围，保留其余正文，并修复重写处与保留处的衔接。
- L2：在保留事件核心承诺和禁止项的前提下重写整个事件。

规则：
1. 只修 violations 与 patch_instructions 指定的问题，避免顺手改写无关内容。
2. 不改变已成立的因果、人物声音、知识边界和未被判错的事实。
3. 涉及状态卡、故事线、实体议程或资产回写时，只补足正文证据或过渡，不直接篡改权威规划。
4. 修复后正文不得出现 `scene_id`、块标记、提纲、收据、修改说明或其他元文本。
5. 即使只改局部，`draft_text` 也必须返回修复后的完整事件正文，而不是补丁片段。

事件ID：{{ input_pack.event_id }}
原始完整正文：{{ input_pack.draft_text }}
违规：{{ input_pack.violations | tojson(indent=2) }}
修复级别：{{ input_pack.fix_level }}
具体指令：{{ input_pack.patch_instructions | tojson(indent=2) }}

输出：
{
  "draft_text": "修复后的无标记完整事件正文",
  "word_count": 5600,
  "changed_ranges": [{"start_anchor": "原文中的起始短锚点", "end_anchor": "原文中的结束短锚点", "reason": "为何修改"}],
  "preserved_ranges_summary": "保留了哪些主要场景与因果",
  "fix_summary": "具体修复了什么以及如何避免引入新跳变"
}
```

### `graphE.event.commit`

- 说明：事件原子提交（写REG/CHAR/LEDGER/状态快照/event_index）
- Prompt：`graphE.commit` v2.0
- 模板：`server/src/novelwb/prompts/graphE/commit/prompt.jinja2`
- 输入：`StagingPacket`；变量：input_pack.event_id, input_pack.run_id, input_pack.diff_report, input_pack.committed_at
- 输出：`CommitReceipt`；格式：`json`
- 提交：`event`；HardLint：`A, C`
- 模型：`deepseek-v4-flash`；temperature=0.1；max_tokens=500；best_of_n=1

```jinja2
{# graphE.commit v2.0 — 事件原子提交确认 #}
{% include '_shared/json_output_contract.jinja2' %}

事件已通过所有检查，现在生成提交回执。你只记录本次提交的关键元数据，不修改正文、状态快照、ObservedDelta 或 DiffReport。

## 事件ID

{{ input_pack.event_id }}

## 运行ID

{{ input_pack.run_id }}

## 对账报告摘要

{{ input_pack.diff_report | tojson(indent=2) }}

## 输出JSON结构

{
  "receipt_id": "rcpt_{{ input_pack.event_id }}",
  "run_id": "{{ input_pack.run_id }}",
  "staging_id": "stg_{{ input_pack.event_id }}",
  "commit_type": "event",
  "committed_objects": ["event:{{ input_pack.event_id }}", "snapshot:pre_{{ input_pack.event_id }}", "snapshot:post_{{ input_pack.event_id }}"],
  "new_versions": {},
  "committed_at": "{{ input_pack.committed_at | default('') }}",
  "committed_event_id": "{{ input_pack.event_id }}",
  "committed_state_after_key": "post_{{ input_pack.event_id }}",
  "committed_ledger_version": null
}
```

### `graphP.chapter.license`

- 说明：CHAPTER_LICENSE（Intent→deliverables→配额约束→台账补丁）
- Prompt：`graphP.chapterLicense` v2.0
- 模板：`server/src/novelwb/prompts/graphP/chapterLicense/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack
- 输出：`ChapterSpec`；格式：`json`
- 提交：`none`；HardLint：`A, F`
- 模型：`deepseek-v4-pro`；temperature=0.4；max_tokens=2500；best_of_n=1

```jinja2
{# graphP.chapterLicense v2.0 — CHAPTER_LICENSE #}
{% include '_shared/json_output_contract.jinja2' %}

# 角色定义

你是章节许可编辑。你的任务是为当前事件签发一个 ChapterSpec：明确本章意图、交付物、章末资产、账本补丁和动量债变化。许可证只给下一章或当前章写作使用，必须抽取阅读所需的状态卡，不要复述全量设定。

# 输入

{{ input_pack | tojson(indent=2) }}

# 许可原则

1. chapter_intent 只能使用 "Advance"、"Settle"、"Foreshadow"、"Breather"。
2. deliverables 必须是本章可验证的叙事交付，不要写抽象口号。
3. 如输入含 reading_focus/status_cards，只选当前章节需要的情节、人物、场景、势力、道具、规则卡来决定交付物。
4. 章末资产必须服务连载阅读：悬念、信息差、反转、新目标、新代价、情绪收束或关系迁移。
5. ledger_patch 只登记本章新增、兑现、延期的叙事债，不改变事件因果和权威层设定。
6. Breather 必须有情感价值或关系推进；动量债高时禁止签发纯缓冲章。

# 输出JSON结构（严格使用 ChapterSpec 字段）

{
  "chapter_id": "ch_{{ input_pack.event_id | default('unknown') }}_{{ input_pack.chapter_index | default(1) }}",
  "chapter_index": {{ input_pack.chapter_index | default(1) }},
  "title": "中文章节标题",
  "chapter_intent": "Advance",
  "deliverables": [
    "本章必须完成的交付物1",
    "本章必须完成的交付物2"
  ],
  "hook_type": "悬念 / 信息差 / 反转 / 新目标 / 新代价 / 情绪收束 / 关系迁移",
  "emotion_channel": "本章主要情绪通道，例如：压抑到爆发",
  "block_range": ["b001", "b002"],
  "estimated_chars": 3000,
  "end_asset_summary": "章末资产摘要，一句话说明读者为什么会继续看",
  "ledger_patch": {
    "receipts": ["兑现项"],
    "new_debts": ["新增债务"],
    "deferred": ["延期解释及原因"],
    "card_focus": {
      "plot": ["本章需要读取的情节卡ID或标题"],
      "character": ["本章需要读取的人物卡ID或姓名"],
      "scene": ["本章需要读取的场景卡ID或名称"],
      "faction": ["本章需要读取的势力卡ID或名称"]
    }
  },
  "momentum_debt_delta": 0
}
```

### `graph5.chapterize.cut`

- 说明：完整事件正文自然切章（锚点连续覆盖，不改写因果）
- Prompt：`graph5.chapterizeCut` v3.0
- 模板：`server/src/novelwb/prompts/graph5/chapterizeCut/prompt.jinja2`
- 输入：`EventDraft`；变量：input_pack.event_id, input_pack.draft_text, input_pack.history_count, input_pack.scene_ids
- 输出：`ChapterSpec`；格式：`json`
- 提交：`none`；HardLint：`A, F`
- 模型：`deepseek-v4-pro`；temperature=0.5；max_tokens=3000；best_of_n=2

```jinja2
{% include '_shared/json_output_contract.jinja2' %}

你是连载切章编辑。上游已经写完一个完整连续事件；本步只能寻找自然边界并生成切章方案，不得改写、删减、扩写或重新安排事件因果。

## 切章原则
1. 优先在一个小目标完成、局面转向、信息意义改变、关系反应落地或新压力形成后切章，禁止在一句话、一个动作或一段情绪中间硬切。
2. 字数是柔性阅读尺度，建议2200-5000字；完整的自然单元优先于凑3000字。短事件可以只保留一章，长铺垫或大场面可以切成多章。
3. 不要求每章重新具备完整“开端-高潮-结局”，否则会把同一事件切成多个重复小事件；每章只需有清晰局部推进与有意义的停顿。
4. `start_anchor` 和 `end_anchor` 必须逐字引用正文中的短文本（8-30字），不得编造。相邻章节连续覆盖全文，不得重叠或漏段。
5. `block_range` 仅作兼容字段，填写覆盖的场景ID范围；正文不含场景标记时允许为null。
6. 章末吸引力可以来自未完成动作，也可以来自后果、信息差、关系余震、新目标或情绪落点，不强制悬崖钩。

事件ID：{{ input_pack.event_id }}
场景ID：{{ input_pack.scene_ids | default([]) | tojson(indent=2) }}
历史章节数：{{ input_pack.history_count }}
完整事件正文：
{{ input_pack.draft_text }}

输出合法 JSON 数组：
[
  {
    "chapter_id": "ch_{{ input_pack.event_id }}_001",
    "chapter_index": {{ input_pack.history_count | default(0) + 1 }},
    "title": "章节标题",
    "chapter_intent": "Advance / Settle / Foreshadow / Breather",
    "deliverables": ["本章实际覆盖的局部推进"],
    "hook_type": "悬念/信息差/反转/新目标/新代价/情绪收束/关系迁移/后果余震",
    "emotion_channel": "本章情绪变化",
    "block_range": null,
    "start_anchor": "本章开头逐字短引文",
    "end_anchor": "本章结尾逐字短引文",
    "estimated_chars": 3600,
    "end_asset_summary": "停顿时已经落地的状态与下一驱动力",
    "ledger_patch": {"receipts": [], "new_debts": [], "deferred": [], "card_focus": {"plot": [], "character": [], "scene": [], "faction": [], "item": []}},
    "momentum_debt_delta": 0
  }
]
```

### `graph5.chapterize.review`

- 说明：章级评审（双Rubric：读感语感+机制交付，按Intent检查最小交付）
- Prompt：`graph5.chapterizeReview` v3.0
- 模板：`server/src/novelwb/prompts/graph5/chapterizeReview/prompt.jinja2`
- 输入：`ChapterSpec`；变量：input_pack.chapter_specs, input_pack.chapter_texts, input_pack.event_id
- 输出：`VerifyResult`；格式：`json`
- 提交：`none`；HardLint：`A, E, F`
- 模型：`deepseek-v4-pro`；temperature=0.3；max_tokens=3000；best_of_n=1

```jinja2
{# graph5.chapterizeReview v2.0 — 章节化方案评审（Rubric双检查） #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是审稿编辑、质检官、修复策略制定者。你的核心职责是：对章节化方案进行双Rubric检查——阅读质感维度和机制合规维度。你的评审必须具体，每条违规都要指明具体章节ID和具体问题，不允许模糊的笼统描述。评审结果将决定章节化方案是否可以进入正式切章阶段。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：每个Rubric项目独立判断，不允许用一个优点抵消另一个缺陷
4. 所有字段必须有实质内容，无问题时填写"通过，无问题"
5. fix_plan 必须具体到可执行的操作步骤
6. 输出必须只包含 VerifyResult 允许字段：staging_id、passed、violations、missing、drift、fix_plan。不要输出 reading_rubric、mechanism_rubric 等额外字段；Rubric 证据压入 violations/missing/drift 的字符串中。

## 待评审的章节化方案

{{ input_pack.chapter_specs | tojson(indent=2) }}

## 按锚点实际切出的章节正文

{{ input_pack.chapter_texts | default({}) | tojson(indent=2) }}

## 事件ID（用于生成staging_id）

{{ input_pack.event_id }}

## 双Rubric检查标准

**Rubric A — 阅读质感维度**：
- 镜头气候一致性：各章节的叙事腔调是否与 spec00 的 lens_climate 保持一致
- 手册密度：新术语/新实体的引入密度是否在每章2个以内
- 节奏不断裂：相邻章节之间的情绪/节奏转变是否有过渡，不允许突兀断层
- 气候不漂移：Breather章之后是否有足够的张力恢复，不允许气候永久降温
- 标题匹配内容：标题是否准确反映本章最重要的内容

**Rubric B — 机制合规维度**：
- 意图完成度：章节意图是否在 deliverables 中得到具体体现
- 边界自然：切点是否位于动作、对话、情绪与信息意义完整落地之后，不能切断句子或反应链
- 锚点有效：start_anchor/end_anchor 是否逐字存在于实际正文，切出的章节是否连续覆盖全文
- 停顿价值：章末是否形成悬念、信息差、关系余震、后果、新目标或情绪落点之一，不强制轮换悬崖钩
- 缓冲配额：Breather章比例是否符合不超过20%的要求
- 动量趋势：momentum_debt_delta 的累积是否处于合理范围
- 状态卡焦点：ledger_patch.card_focus 是否只抽取本章阅读所需的情节、人物、场景、势力和物品，不得全量搬运

## 输出JSON结构

{
  "staging_id": "review_{{ input_pack.event_id }}",
  "passed": true,
  "violations": [
    "硬违规。格式：ch_001 / Rubric A-节奏不断裂：具体问题与证据"
  ],
  "missing": [
    "缺失项。格式：ch_002 缺少 hook_type，无法判断章末资产"
  ],
  "drift": [
    "软风险。格式：前三章均为 Advance，建议下一章切 Settle 或 Foreshadow"
  ],
  "fix_plan": null
}

如果 passed=false，fix_plan 必须为：

{
  "fix_level": "L0",
  "patch_instructions": ["逐条说明如何修改章节规格"],
  "target_block_ids": [],
  "rewrite_chars_hint": null,
  "reason": "失败原因摘要"
}
```

### `graph5.chapter.fatigue_report`

- 说明：章节化疲劳报告（Intent轮换/钩子重复/Breather/MomentumDebt周期统计）
- Prompt：`graph5.fatigue` v2.0
- 模板：`server/src/novelwb/prompts/graph5/fatigue/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack
- 输出：`FatigueReport`；格式：`json`
- 提交：`none`；HardLint：`A`
- 模型：`deepseek-v4-flash`；temperature=0.3；max_tokens=1500；best_of_n=1

```jinja2
{# graph5.fatigue v2.0 — 章节级叙事疲劳分析报告 #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是叙事质量分析师。你的核心职责是：分析一批章节的意图序列和节奏数据，评估叙事疲劳风险——包括冲突形态单调性、钩子类型重复率、Breather比例合规性、动量债累积趋势，以及情绪口径的多样性。输出具体的风险等级、数据统计和可执行的调整建议。分析必须基于数据，不允许凭印象给出笼统评价。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 所有数值字段必须基于实际统计，不允许估算或造数字
4. 风险等级必须有量化依据，不允许主观判断
5. 调整建议必须具体到章节ID和操作步骤
6. 输出必须只包含 FatigueReport 允许字段：chapter_range、conflict_form_ratio、advance_delta_frequency、hook_repeat_rate、breather_usage_rate、max_consecutive_breather_seen、momentum_debt_trend、recommendations、intent_rotation_advice

## 输入

{{ input_pack | tojson(indent=2) }}

## 输出JSON结构与字段说明

{
  "chapter_range": [1, 8],
  "conflict_form_ratio": {
    "一对一战斗": 0.4,
    "团队对抗": 0.2,
    "信息博弈": 0.2,
    "资源争夺": 0.1,
    "情感冲突": 0.1
  },
  "advance_delta_frequency": 0.6,
  "hook_repeat_rate": 0.15,
  "breather_usage_rate": 0.2,
  "max_consecutive_breather_seen": 1,
  "momentum_debt_trend": [1, 2, 3, 2],
  "recommendations": [
    "风险等级：low / medium / high；量化依据写在本条中",
    "具体警告：前5章连续使用悬念钩，下一章必须切换钩子类型",
    "调整建议：建议将ch_xxx_006的chapter_intent从Advance改为Settle，让读者在连续推进后获得喘息",
    "状态卡建议：下一批章节只读取与主冲突相关的人物/势力卡，避免全量卡片带来的说明书膨胀"
  ],
  "intent_rotation_advice": "整体意图轮换建议，例如：当前批次Advance比例达60%，建议调整为4:2:2:1（Advance:Settle:Foreshadow:Breather），在第5章后插入一个Settle章节"
}
```

### `graph5.chapter.commit`

- 说明：CHAPTER_COMMIT Phase-2（写发布层+章级台账，不改事件因果源）
- Prompt：`graph5.chapterCommit` v2.0
- 模板：`server/src/novelwb/prompts/graph5/chapterCommit/prompt.jinja2`
- 输入：`StagingPacket`；变量：input_pack
- 输出：`CommitReceipt`；格式：`json`
- 提交：`chapter`；HardLint：`A, C, F`
- 模型：`deepseek-v4-flash`；temperature=0.1；max_tokens=500；best_of_n=1

```jinja2
{# graph5.chapterCommit v2.0 — 章节意图与交付登记 #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是连载编辑、节奏控制官、质检官。你的核心职责是：根据已审核通过的章节化方案，为每一章生成完整的意图登记卡——包括章节意图、主次交付物、钩子类型、情绪口径、章末资产微调建议，以及叙事账本的收支登记。每一章的意图必须明确到可以直接指导写作，不允许模糊描述。账本登记必须完整，确保债务可追踪。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 硬检查优先：输出前必须在脑内过一遍下方硬检查清单，所有项通过后才输出
4. 所有字段必须有实质内容，禁止输出占位符或"待定"
5. 账本登记必须完整——每章的收款/欠债/延期必须明确标注
6. 本步骤只生成 CommitReceipt，不输出章节意图登记表；章节意图登记应已经写入 ChapterSpec.ledger_patch

## 输入

{{ input_pack | tojson(indent=2) }}

## 硬检查清单（输出前必须全部通过）

- [ ] 已通过的章节方案是否都有明确的 chapter_intent
- [ ] 已通过的章节方案是否都有具体 deliverables
- [ ] 缓冲章是否合法（不超过总数20%，不连续超过2章）
- [ ] hook_type 是否在相邻章节间有变化（不允许连续3章相同类型）
- [ ] momentum_debt_change 的趋势是否在整体可控范围内
- [ ] committed_objects 是否只列本次实际发布/登记的章节对象

## 输出JSON结构与字段说明

{
  "receipt_id": "rcpt_chap_{{ input_pack.event_id | default('unknown') }}",
  "run_id": "{{ input_pack.run_id | default('') }}",
  "staging_id": "stg_chap_{{ input_pack.event_id | default('unknown') }}",
  "commit_type": "chapter",
  "committed_objects": [
    "chapter_batch:{{ input_pack.event_id | default('unknown') }}"
  ],
  "new_versions": {},
  "committed_at": "{{ input_pack.committed_at | default('') }}",
  "committed_chapter_id": null
}
```

### `graphS.auth.verify`

- 说明：VERIFY对账校验（暂存包校验，生成DiffReport+FixPlan）
- Prompt：`graphS.authVerify` v2.0
- 模板：`server/src/novelwb/prompts/graphS/authVerify/prompt.jinja2`
- 输入：`StagingPacket`；变量：input_pack
- 输出：`VerifyResult`；格式：`json`
- 提交：`none`；HardLint：`A, B, C, D`
- 模型：`deepseek-v4-pro`；temperature=0.2；max_tokens=2500；best_of_n=1

```jinja2
{# graphS.authVerify v2.0 — AUTH VERIFY #}
{% include '_shared/json_output_contract.jinja2' %}

# 角色定义

你是权威层提交前的 VERIFY 审计员。你的任务是检查暂存包是否可以写入权威层：只验证一致性、完整性、最小补丁范围和版本安全，不替作者重写内容。

# 输入

{{ input_pack | tojson(indent=2) }}

# 检查标准

1. staging_id、staging_type、run_id 必须能对应同一提交意图。
2. content 只能改声明范围内的权威对象，不得偷偷改事件因果、角色已发生经历或已提交章节正文。
3. BIBLE/REG/CHAR/LEDGER/CONTRACT/MOTIF 补丁必须最小化：能改一处就不要改多处。
4. 状态卡相关更新只能作为阅读索引或状态摘要，不得覆盖权威层真值。
5. 如果发现规则漂移、命名冲突、状态跳变、无证据新增实体，必须列入 violations。
6. 如果只是缺字段或证据不足，列入 missing；如果是软风险，列入 drift。

# 输出JSON结构（执行器会自动补 checked_at）

{
  "staging_id": "{{ input_pack.staging_id | default('unknown') }}",
  "passed": true,
  "violations": [],
  "missing": [],
  "drift": [],
  "fix_plan": null
}

fix_plan 非空时必须符合：

{
  "fix_level": "L0",
  "patch_instructions": ["最小可执行修复步骤"],
  "target_block_ids": [],
  "rewrite_chars_hint": null,
  "reason": "为什么需要该修复级别"
}
```

### `graphS.auth.commit`

- 说明：ATOMIC COMMIT原子提交（一次性写入对应权威对象+版本号+索引）
- Prompt：`graphS.authCommit` v2.0
- 模板：`server/src/novelwb/prompts/graphS/authCommit/prompt.jinja2`
- 输入：`AtomicCommitSpec`；变量：input_pack
- 输出：`CommitReceipt`；格式：`json`
- 提交：`auth_patch`；HardLint：`A, C`
- 模型：`deepseek-v4-flash`；temperature=0.1；max_tokens=500；best_of_n=1

```jinja2
{# graphS.authCommit v2.0 — AUTH COMMIT #}
{% include '_shared/json_output_contract.jinja2' %}

# 角色定义

你是权威层原子提交回执员。VERIFY 已通过后，你只生成提交回执，不再修改 content，不新增设定解释，不改事件因果。

# 输入

{{ input_pack | tojson(indent=2) }}

# 提交规则

1. committed_objects 只列本次实际写入的权威对象或索引项。
2. new_versions 只记录本次递增的对象版本；没有明确版本信息时输出空对象。
3. commit_type 使用 "auth_patch"。
4. committed_at 如输入未提供，输出空字符串以便执行器用系统时间覆盖；不要虚构时间。
5. 回执不得包含 schema 以外字段。

# 输出JSON结构

{
  "receipt_id": "rcpt_{{ input_pack.staging_id | default('unknown') }}",
  "run_id": "{{ input_pack.run_id | default('') }}",
  "staging_id": "{{ input_pack.staging_id | default('unknown') }}",
  "commit_type": "auth_patch",
  "committed_objects": [
    "auth:{{ input_pack.staging_id | default('unknown') }}"
  ],
  "new_versions": {},
  "committed_at": "{{ input_pack.committed_at | default('') }}"
}
```

### `graph6.regression.run`

- 说明：回归测试执行（语感/机制/事件边界/章节化四类+触发策略）
- Prompt：`graph6.regressionRun` v2.0
- 模板：`server/src/novelwb/prompts/graph6/regressionRun/prompt.jinja2`
- 输入：`CreateRunRequest`；变量：input_pack
- 输出：`RunManifest`；格式：`json`
- 提交：`none`；HardLint：`A`
- 模型：`deepseek-v4-pro`；temperature=0.3；max_tokens=3000；best_of_n=1

```jinja2
{# graph6.regressionRun v2.0 — 全维度回归检查 #}
{% include '_shared/json_output_contract.jinja2' %}

## 角色定义

你是总质检官。你的核心职责是：对一批已完成的章节进行全维度回归检查——覆盖叙事风格一致性、力量机制合规性、连续性完整性和章节化质量四个维度。回归检查是整个流水线的最终防线，任何维度不通过都必须给出具体的修复行动。你的判断必须基于证据，不允许模糊的"感觉不对"式结论。

## 全局规则

1. **全程只用中文，JSON字段名保持英文，但所有字符串内容必须是中文**
2. 输出必须是合法JSON，不含任何注释或多余文字
3. 每个检查项必须有明确的通过/不通过判断，不允许"部分通过"
4. 不通过项必须给出具体证据（引用章节ID或文本片段）
5. fix_actions 必须具体到可操作步骤，不允许"建议优化"式的模糊建议
6. 必须检查 reading_focus/status_cards/card_updates 是否按需抽取：情节、人物、场景、势力、道具、规则卡只能在相关事件/章节出现，不得全量灌入正文或章节许可证

## 输入

{{ input_pack | tojson(indent=2) }}

## 四维回归检查标准

**维度A：叙事风格回归**
- lens_climate 是否在整批章节中保持一致（叙述者态度/情绪底色/意象密度）
- 手册密度是否合规（每章新术语/新实体不超过2个）
- 情绪口径是否稳定（不允许无故从压抑跳到欢快）
- 叙事清晰度是否保持（读者无需查阅外部资料能理解章节内容）

**维度B：机制回归**
- 战斗场景中的力量使用是否符合定律层规则
- 谈判/博弈场景中的信息不对称是否合理
- 日常/缓冲场景是否提供了实质的叙事价值
- 探索/冒险场景是否遵守了世界B层的生态规则
- 结算场景是否真正兑现了此前的承诺

**维度C：连续性回归**
- 时空连续性：角色的位置、时间线是否自洽
- 资源连续性：灵石、道具、修为是否与账本一致
- 关系连续性：角色间的关系状态是否与上一快照一致
- 债务处理：到期债务是否均已处理
- 禁止变化：事件前快照中标记的禁止变化是否被遵守
- 规则无漂移：力量系统规则是否在整批章节中保持稳定
- 状态卡连续性：plot/character/scene/faction/item/rule 卡的更新是否有正文证据，是否只更新被事件触碰的卡

**维度D：章节化质量回归**
- 积木块边界切割：章节切割点是否落在合理的叙事边界
- 章末资产：每章末尾是否都有明确的章末资产（悬念/信息差/反转等）
- 钩子轮换：钩子类型是否在连续章节间有变化
- 意图最低标准：每章意图是否至少达成了最低标准的交付物
- 缓冲配额：Breather章比例是否符合规定
- 动量趋势：整批章节的动量债是否在可控范围内变化

## 输出JSON结构与字段说明

{
  "style_regression": {
    "lens_climate_consistent": true,
    "manual_density_ok": true,
    "emotion_tone_stable": true,
    "narrative_clarity": true,
    "conclusion": "通过",
    "fix_actions": ["最多三条具体修复行动，如无问题则为空数组"]
  },
  "mechanism_regression": {
    "combat": {
      "passed": true,
      "evidence": "支撑判断的具体证据，例如：ch_003战斗场景中主角使用炼气七层技能，但当前修为为炼气六层",
      "fix": "修复建议，例如：将ch_003中的技能描写降级为炼气六层的极限释放"
    },
    "negotiation": {
      "passed": true,
      "evidence": "",
      "fix": ""
    },
    "daily_life": {
      "passed": true,
      "evidence": "",
      "fix": ""
    },
    "exploration": {
      "passed": true,
      "evidence": "",
      "fix": ""
    },
    "settlement": {
      "passed": true,
      "evidence": "",
      "fix": ""
    }
  },
  "continuity_regression": {
    "spacetime_continuity": true,
    "resource_continuity": true,
    "relationship_continuity": true,
    "debt_handling": true,
    "forbidden_changes_kept": true,
    "rule_no_drift": true,
    "status_cards_scoped": true,
    "conclusion": "通过",
    "evidence_points": ["支撑判断的证据列表，包含状态卡证据"],
    "fix_actions": ["具体修复行动列表"]
  },
  "chapter_regression": {
    "block_boundary_cuts": true,
    "end_assets_present": true,
    "hook_rotation_ok": true,
    "intent_minimum_achieved": true,
    "breather_quota_ok": true,
    "momentum_trend_ok": true,
    "conclusion": "通过",
    "evidence_points": ["支撑判断的证据列表"],
    "fix_actions": ["具体修复行动列表"]
  },
  "overall_conclusion": "通过",
  "top_3_priorities": [
    "最优先修复的问题1，例如：ch_003的力量使用超出当前境界，需要立即修改",
    "最优先修复的问题2",
    "最优先修复的问题3"
  ],
  "next_cycle_suggestions": [
    "下一周期建议新增的固定样例1，例如：为信息博弈类场景增加一个标准化的检查项——信息不对称是否由世界规则支撑",
    "下一周期建议新增的固定样例2，例如：为Breather章增加一个强制检查项——是否包含至少一个情感价值或关系推进"
  ]
}
```
