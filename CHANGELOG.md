# CHANGELOG

只记录 v1.x 功能变更和 rX 规范修订。计划外改动请开 v2 + migration。

## [Unreleased] — 本地开源交付准备

- 采用 MIT License，补齐版权署名、安装包许可元数据及前端第三方许可文本
- 增加隔离工作区的无密钥审核演示、演示路线和真实模型评测记录方案
- 增加贡献指南、安全边界、问题模板、PR 模板和本地发布验收流程
- 增加工作文件、暂存区及 Git 可达历史检查；报告不输出疑似凭据内容
- 增加交付脚本回归检查，并纳入 Windows/Linux 后端 CI；未执行远端发布

## [v1.0+r7] - 2026-07-16

### 作品基座逐文件审核
- 将作品基座拆为 `spec00 / world_a / world_b / pow_l / pow_s / pow_e / opp_eco / cast` 八个连续文件级步骤
- 每次只生成一个文件；当前文件批准或驳回前禁止生成后续文件，八个文件全部批准前锁定全书总纲
- 后续文件只读取前序人工修改并批准后的权威版本，恢复人工审核的实际控制意义
- 前端增加 1/8～8/8 步骤链、当前文件提示和文件级批准文案；生成改为 SSE 流式进度并接入真实取消运行
- 禁止作品基座八文件整包微调；完成后的设定修改统一走分层资产面板的单文件审核

## [v1.0+r6] - 2026-07-16

### DeepSeek 连接策略
- DeepSeek 的 `httpx.Client` 固定使用 `trust_env=False`，忽略 `HTTP_PROXY`、`HTTPS_PROXY` 与 `ALL_PROXY`
- 清除请求被系统代理导向本机代理端口后长时间等待的问题，并增加连接策略回归测试

## [v1.0+r5] - 2026-07-16

### 分层资产工作台
- 新增由注册表动态生成的“分层资产”面板，细化到作品基座、全书 StoryRoom、卷 StoryRoom、地图/场景、事件槽位和逐事件设计的独立逻辑页面
- 新增逻辑资产目录、详情和暂存审核 API；单页修改通过 `asset_edit` 审核写回所属 AUTH 文件
- 局部合并保留兄弟字段，使用权威基准版本防止并发覆盖，并保护事件身份字段与字段所有权
- 将 `reading_assets`、状态卡索引、最新快照和上下文包作为只读投影展示，禁止绕开来源资产反向修改
- 前端使用通用 JSON 编辑器和动态目录，不随卷数、事件数线性增加手写页面组件

## [v1.0+r4] - 2026-07-16

### 规范与结构图同步
- 将 StoryRoom 故事丰富度分层提升为主架构，明确“丰富度”与“复杂度”是两个独立轴
- 补齐全书 StoryRoom、全书地图、卷 StoryRoom、卷地图/场景、逐事件设计、`reading_assets`、动态事件丰富和事实回写的纵向链路
- 固化 `plot/character/relationship/faction/item/ecology/mystery/set_piece/aftermath/ensemble` 横向扩展路线
- 补入 `foundation → master_plan → volume_plan → event_plan → prose → state_delta → chapter_plan` 人工审核工作流
- 重画 `../结构.md`，同步 README、Prompt Review 版本与 Word 文件流图；旧 Word 提示词包标记为历史资料

## [v1.0.0] - 2026-03-20

### 初始化
- 项目骨架，目录结构，SPEC v1.0+r0
- 技术选型：DeepSeek LLM，跳过RAG，CLI优先

### 阶段8-13完成（2026-03-20）
- Stage 8: Workspace IO层（FileLock / RunsStore / EventsStore / StagingStore / AuthStore / SnapshotsStore / MaterialsStore / PublishStore / SqliteIndex）
- Stage 9: LLM缓存层（LlmCacheStore / SearchCacheStore）
- Stage 10: 适配器层（LLMAdapter / MockReplayAdapter / DeepSeekAdapter / NoopSearchAdapter）
- Stage 11: 核心引擎（HardLintEngine规则A-G / Judge / RegressionRunner）
- Stage 12: 图执行+调度器（StepRunner / GraphE / GraphS / Graph5 / GraphP / RepairPolicy / Orchestrator）
- Stage 13: FastAPI API（/projects / /pipeline / /chapters） + Typer CLI（novelwb命令） + 单元测试（13 passed） + scripts/run_pipeline.py
