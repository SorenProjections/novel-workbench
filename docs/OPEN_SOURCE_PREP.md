# 本地开源交付验收记录

日期：2026-10-08（Asia/Shanghai）。基础提交：`a76c87f`。
本记录对应在该提交上准备的本地改动；尚未暂存、提交或公开发布。

## 已完成

- 采用 [MIT](../LICENSE)，版权署名为 `NewbieonfireSpongeforknowledge`，与首次提交作者一致。
  Python 包带有相同许可证、作者和项目简介；前端分发携带依赖许可声明。
- 整理 [README](../README.md)、[贡献指南](../CONTRIBUTING.md)、[安全说明](../SECURITY.md)、
  Issue/PR 模板、[发布检查流程](RELEASING.md)及 CI 检查。
- 增加[无密钥演示](DEMO.md)、真实浏览器截图、[工程设计阅读索引](ENGINEERING_NOTES.md)
  与[真实模型评测方案](EVALUATION.md)。文档明确个人维护节奏及当前能力边界。
- 增加交付扫描：检查工作文件或实际暂存内容、可达的本地历史、常见凭据、运行数据路径、
  大文件和必需文档；根目录与安装包的许可证必须一致。

## 本次验证

在 Windows 本地使用现有依赖执行，模型均为 mock；构建与测试产物位于被忽略的 `.checks/`。

| 检查 | 结果 |
|---|---|
| `python -m pytest server/tests -q` | 135 项通过 |
| `python -m pytest scripts/tests -q` | 14 项通过，覆盖暂存秘密、已删除的历史秘密、运行路径和演示隔离等边界 |
| `npm --prefix webui run check` / `test` / `build` | 类型检查、8 项测试和生产构建通过 |
| `python scripts/check_spec_sync.py` | 0 错误、0 警告 |
| `python scripts/evaluate_quality.py` | 11/11 固定用例通过，仅验证机械规则与故事约束 |
| `python scripts/smoke_run.py` | mock 后台任务、重复执行/批准及 SSE 回放通过 |
| Ruff 检查新增演示、扫描及其测试脚本 | 格式和静态检查通过 |
| 离线 wheel 构建及 `scripts/check_package.py` | 包内 MIT 元数据、许可证、第三方声明、静态页面、mock 生成、审核与回放通过 |
| `python scripts/check_release.py --history` | 工作文件及当前 1 个可达历史提交未发现规则命中 |
| `git diff --check` | 通过 |

浏览器实际操作了合成项目 `demo-ferry`：编辑作品规格 → 刷新恢复草稿 → 批准 → 查看正式资产 v1
→ 再次刷新确认内容持久化。截图见 [DEMO.md](DEMO.md#自动验证与记录)。验收服务已停止；
可用 `python scripts/demo.py` 启动新的隔离演示。

本次 wheel 为 `novelwb-1.0.0-py3-none-any.whl`，位于
`.checks/open-source-delivery-1791399972555/wheels/`。
SHA-256：`19d0c7dcd5b2c766f63a4c241e0a7ac24a704c621fa7067174d06ec7f3f6fb88`。
这是本地构建校验值；重新构建后需要重新记录。

## 验证范围与下一步

现有验证使用已安装的依赖，不等同于联网全新环境安装；GitHub Actions 尚未在远端运行。
离线演示只覆盖基座第一个文件 `spec00`，没有进行真实模型质量、长篇一致性、费用或用户效果实验。
扫描是基于规则的检查，不是全面安全审计或依赖授权审计，也不读取 Git 作者邮箱等提交元数据。

公开前按 [发布流程](RELEASING.md)审阅并暂存最终改动，再检查实际索引。
确认愿意公开的 Git 作者信息，填写真实仓库地址和安全问题接收渠道，最后执行远端 CI。
源代码归档需在最终本地提交后创建，避免遗漏目前尚未提交的交付文件。
