# 项目优化与验证记录

完成日期：2026-10-03。范围：novel-workbench 后端、前端、可执行契约与工程检查。

## 已完成的改动

| 方向 | 改动与结果 | 主要位置 |
|---|---|---|
| 提交一致性 | 多文件写入采用持久化撤销日志；写入失败回滚，进程退出后的受控读取恢复未完成事务。事件、权威和章节仍走各自提交路径。 | `server/src/novelwb/utils/transactions.py`、`storage/`、`engine/graphs/` |
| 并发与重复审批 | 操作系统锁在进程结束后自动释放；权威版本在锁内分配，支持预期版本校验；重复批准返回保存结果，避免重复扣账和发布。权威提交回执返回实际版本。 | `utils/file_locks.py`、`storage/auth_store.py`、`engine/review_service.py` |
| 路径与查询边界 | 校验项目及文件 ID、Windows 保留名称和解析后的路径；查询未知项目/运行返回错误而不建目录；CLI 与 API 共用工作区配置。 | `storage/workspace_layout.py`、`api/deps.py`、`cli/main.py` |
| 运行恢复 | 后台任务采用有界线程池与队列，保存参数、状态、取消标记、结果和用量；相同运行 ID 幂等执行；SSE 按游标回放并增量读取，刷新和断线能恢复订阅。服务关闭取消排队任务，遗留任务标记中断。 | `engine/task_service.py`、`api/routers/pipeline.py`、`webui/src/runStream.ts` |
| 编辑体验 | 审核正文、修订意见、资产按项目与文件保存本地草稿；显示保存状态、来源冲突和修改前后文本；存储失败提供保留提醒。切换资产时清空旧详情，并忽略过期的目录响应。 | `webui/src/draftStorage.ts`、`useDraft.ts`、`components/DraftStatus.tsx` |
| 质量与回归 | 修正空正文、连续重复、禁忌、零配额等检查；兼容当前和旧版 spec00；API 与 CLI 的项目回归检查已有事件，返回实际检查数量；加入 11 个固定原创评测样例。 | `engine/prose_quality.py`、`engine/regression.py`、`core/validators/hard_lint.py`、`tests/fixtures/quality/` |
| 结构与读取性能 | 从编排器拆出审核和任务服务；进度回调按执行上下文隔离；权威集合与长线骨架优先读最新工件，旧工作区只进行一次历史迁移。 | `engine/orchestrator.py`、`engine/review_service.py`、`engine/step_runner.py`、`storage/auth_store.py` |
| 工程保障 | 修复静态检查和类型问题，补齐资源打包、依赖约束、Schema 导出、隔离 Smoke 和包验证；CI 配置 Windows/Linux 后端、前端与安装包检查；SPEC 更新至 r18。 | `server/pyproject.toml`、`requirements-dev.lock`、`.github/workflows/ci.yml`、`scripts/`、`SPEC_v1.md` |

## 本地验证结果

| 检查 | 结果 |
|---|---|
| 后端全量 pytest | **135 passed**；初始基线为 90 项 |
| 可靠性与任务专项 | 并发版本、重复批准、发布失败回滚、强制退出恢复、嵌套锁、取消、队列关闭、生命周期恢复均通过 |
| API/CLI 回归入口 | 4 项通过，确认已有事件与章节被实际计入，命令行查询不会创建未知项目 |
| Ruff 检查与格式 | 通过；88 个源文件格式检查通过 |
| 严格 mypy | **Success: no issues found in 88 source files** |
| 前端回归 | **8 passed**，覆盖草稿存储、项目隔离、存储异常和 SSE 事件处理 |
| TypeScript 与生产构建 | 通过；产物已更新到后端 `novelwb/web/` |
| 规范同步 | **0 错误，0 警告** |
| 离线质量样例 | **11/11 通过** |
| JSON Schema 导出 | **60 个**导出成功 |
| 模拟端到端 Smoke | 持久化运行 → 回放 → 审核 → 重复批准，通过 |
| Wheel 打包与独立包目录运行 | 通过；脱离源码目录加载契约/模板，读取页面与 JS/CSS，完成模拟生成、批准和回放 |
| 依赖约束与脚本 | 38 项依赖的已安装元数据约束相容；Python 脚本与 CI YAML 解析通过 |

本地使用 Windows 和 `F:\anaconda\python.exe`；运行验证时指定 mock 适配器。测试、报告、模拟任务和包解压均放在 `E:\ClaudeTest\.optimization-checks\`；创作数据 `server/workspace/` 未被本次验证读写。

最终安装包：`E:\ClaudeTest\.optimization-checks\delivery-wheels\novelwb-1.0.0-py3-none-any.whl`。

SHA-256：`459efe90932fa7f9274e2f534163d2c8c700adc2e450a60d374d438507f83611`。

## 验证边界

- 没有调用真实 LLM 或搜索服务；模型输出的文学质量与真实请求耗时未验证。
- 浏览器工具初始化失败（无法写入 kernel assets，系统找不到指定路径），因此未完成浏览器点击与视觉检查；前端已完成自动测试、类型检查、构建及静态资源 HTTP 检查。
- Windows 本地检查已执行；远程 CI、Linux 执行和联网全新环境安装仍待 CI 验证。包检查使用现有本地依赖，验证包自身不依赖源码目录。
- 崩溃恢复覆盖进程强制退出；没有模拟断电或磁盘硬件故障。

日常检查命令与使用说明见项目 `README.md`；架构和行为以 `SPEC_v1.md` 为准。
