# 工程设计阅读索引

这份文档帮助读者从具体问题进入代码，也可用作项目介绍提纲。它不是另一份行为规范；
架构和契约仍以 [SPEC_v1.md](../SPEC_v1.md) 为准。

## 1. 多文件写入失败后如何保持一致

权威文件、索引和历史记录可能在一次提交中同时变化。实现采用项目级锁与持久化撤销日志，
写入前保存恢复信息，提交失败时回滚，后续受控读取恢复未完成事务。

- 实现：[transactions.py](../server/src/novelwb/utils/transactions.py)、
  [auth_store.py](../server/src/novelwb/storage/auth_store.py)。
- 证据：[test_reliability.py](../server/tests/test_reliability.py) 中的失败注入与进程强制退出测试。
- 取舍：面向本地文件工作区，项目内操作需要锁协调；它不等于分布式数据库事务，也没有经过断电和硬件故障验证。

## 2. 重复批准与过期编辑如何处理

审批先检查暂存包状态，已批准的请求返回保存的结果。写回正式资产时检查基准版本，
防止旧审核稿覆盖更新后的内容。事件、章节和权威资产各有明确的提交路径。

- 实现：[review_service.py](../server/src/novelwb/engine/review_service.py)、
  [asset_catalog.py](../server/src/novelwb/engine/asset_catalog.py)。
- 证据：[可靠性测试](../server/tests/test_reliability.py) 和
  [流水线测试](../server/tests/test_pipeline.py) 的并发批准、回滚与过期版本用例。
- 取舍：更多显式审核步骤提高了可控性，也增加操作量；是否适合具体作者需要真实使用反馈。

## 3. 为什么模型输入需要可追踪

事件从正式资产与状态投影中选择工作集，记录来源版本、选中和省略的原因，以及上下文指纹。
这样才能解释某次模型调用依据了哪一版设定，并在后续状态抽取中保持可追踪关系。

- 实现：[context_compiler.py](../server/src/novelwb/engine/context_compiler.py)、
  [step_runner.py](../server/src/novelwb/engine/step_runner.py)。
- 证据：[test_context_compiler.py](../server/tests/test_context_compiler.py)。
- 取舍：确定性选择便于调试，但选择策略和预算是否改善真实生成效果，需要按
  [评测方案](EVALUATION.md) 实验；不能从实现存在直接推出质量收益。

## 4. 浏览器断线与后台任务如何衔接

后台服务保存运行参数、状态和事件序列。SSE 支持从游标回放，前端过滤已接收的序列，
草稿按项目和逻辑文件保存在浏览器。进程重启后遗留任务标记中断，已批准文件继续保留。

- 实现：[task_service.py](../server/src/novelwb/engine/task_service.py)、
  [runStream.ts](../webui/src/runStream.ts)、[draftStorage.ts](../webui/src/draftStorage.ts)。
- 证据：[test_tasks_api.py](../server/tests/test_tasks_api.py) 与前端 `webui/tests/`。
- 取舍：有界线程池适合当前本机工作台；取消在步骤边界生效，不能保证立即中止已发出的外部模型请求。

## 介绍项目时可以使用的事实

> 面向长篇小说创作的 LLM 工作台，基于 FastAPI 和 React 实现逐文件人工审核、
> 版本化故事资产、后台任务回放，以及失败回滚和进程中断恢复；通过模拟模型与故障注入验证关键边界。

再补充自己实际负责和理解的部分，以及一次能够讲清楚的故障、设计选择和验证过程。
测试数量应引用当前执行结果；不要把 mock 检查写成真实用户指标，或将应用编排表述为模型训练成果。

现有维护重点包括大型编排模块的职责划分、审核服务与编排器的耦合、真实模型效果评测，
以及首次使用体验。它们适合做后续范围明确的贡献，不需要为此承诺固定的长期更新计划。
