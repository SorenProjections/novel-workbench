# 参与贡献

欢迎提交可复现的问题、文档改进、回归测试和范围明确的修复。架构与行为以
[`SPEC_v1.md`](SPEC_v1.md) 为准；首次阅读可从 [README](README.md) 和
[离线演示](docs/DEMO.md) 开始。

## 开发环境

Python 3.11+；Node.js 22 与 npm；Git。以下命令在仓库根目录运行，安装依赖需要网络：

```powershell
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Linux/macOS 使用：source .venv/bin/activate
python -m pip install -c server/requirements-dev.lock -e "./server[dev]"
npm --prefix webui ci
npm --prefix webui run build
```

后端开发：`python -m uvicorn novelwb.server_main:app --reload --host 127.0.0.1 --port 8000`。
前端开发：`npm --prefix webui run dev`，Vite 将 API 请求代理到 8000 端口。
没有模型密钥时用 `python scripts/demo.py` 体验审核流程。

## 修改与验证

- 先读相关实现和测试，保持改动集中。运行目录、缓存和个人创作内容不要加入提交。
- Prompt、StepSpec、Schema 或枚举变更须同步规范并运行 `python scripts/check_spec_sync.py`。
- 保持“暂存 → 校验 → 原子提交或回滚”，以及 AUTH、EVENT、CHAPTER 的提交边界。
- 外部模型和搜索调用放在适配器层；回归测试使用 mock，不能要求贡献者的真实密钥。
- 有行为变化时补充针对失败边界的测试。文案和低影响样式调整通常不需要新测试。

优先执行对应的窄测试。涉及共享逻辑时，再执行相关全量检查：

```powershell
python -m pytest server/tests -q
python -m pytest scripts/tests -q
python scripts/check_spec_sync.py
python scripts/evaluate_quality.py
python scripts/smoke_run.py
python -m ruff check server/src
python -m ruff format --check server/src
python -m mypy server/src --config-file server/pyproject.toml
npm --prefix webui run check
npm --prefix webui test
npm --prefix webui run build
python scripts/check_release.py --history
```

提交前审阅 `git diff` 和 `git diff --cached`；加入暂存区后，可用
`python scripts/check_release.py --index --history` 检查实际将提交的内容。
本地检查不执行推送、发布或修改 Git 历史。

## 问题和拉取请求

问题报告请包含操作系统、Python/Node 版本、提交版本、最小复现步骤、预期与实际结果。
使用合成文本重现；不要上传 `.env`、真实密钥、完整运行日志或未授权的小说内容。
安全问题的处理方式见 [SECURITY.md](SECURITY.md)。

PR 说明应描述具体问题、最终行为和实际执行的验证；没有执行的验证需明确写出。
不要把 mock 样例的通过率称为真实模型质量。使用 AI 辅助贡献时，提交者仍应理解改动，
核查来源，并能够解释实现与验证结果。

贡献内容遵循仓库根目录的 [MIT 许可证](LICENSE)；第三方代码、图片、字体与数据需保留其原始许可和来源。
前端分发文本位于 `webui/public/THIRD_PARTY_NOTICES.txt`，构建后位于
`/ui/THIRD_PARTY_NOTICES.txt`，并随 wheel 携带。更新前端依赖时，核对其实际依赖树与许可文本，
同步这份声明；开发工具依赖不因列在锁文件中就自动属于浏览器运行包。
