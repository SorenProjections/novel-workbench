# 本地发布准备与验收

本文件描述将本地源码整理成可交付版本的流程。下面的检查和打包命令不创建远端仓库，
不推送、不打标签，也不发布 Release 或安装包。

## 1. 审阅源码范围

在仓库根目录运行：

```powershell
git status --short
git diff --check
git diff --stat
python scripts/check_release.py --history --output .checks/release-hygiene.json
```

默认检查已跟踪文件的工作区版本，以及未被忽略的新文件。`--history` 另外检查所有本地可达引用
和 HEAD 的历史文件，包括当前已删除的内容；不检查 reflog、不可达对象或远端尚未获取的历史。
脚本不联网，也不会修改索引、工作文件或提交历史。

它检查交付文档是否齐全、禁止提交的运行路径、常见凭据格式和超过 5 MiB 的文件。
它不识别所有密钥格式，不验证第三方授权，也不能证明不存在敏感信息。发现问题后先在本地查看
具体文件；不要把可能包含密钥的原文粘贴进公开问题。

完成自己的暂存操作后，再检查实际暂存区：

```powershell
git diff --cached --stat
git diff --cached --check
python scripts/check_release.py --index --history
```

新增交付文件尚未暂存时，`--index` 报告缺失文件是预期行为；不要因此跳过最终的索引检查。

## 2. 验证

依赖安装见 [贡献指南](../CONTRIBUTING.md)。以下检查不调用真实模型：

```powershell
python -m pytest server/tests -q
python -m pytest scripts/tests -q
python scripts/check_spec_sync.py
python scripts/evaluate_quality.py --output .checks/quality.json
python scripts/smoke_run.py
python -m ruff check server/src
python -m ruff format --check server/src
python -m mypy server/src --config-file server/pyproject.toml
npm --prefix webui run check
npm --prefix webui test
npm --prefix webui run build
```

然后按 [DEMO.md](DEMO.md) 检查浏览器内的编辑、批准、刷新和资产查看。
远端 CI 中已配置 Windows/Linux 后端检查，但远端没有实际运行前，不填写通过徽章或宣称跨平台验收完成。

公开前还应查询锁定依赖的已知漏洞。以下操作需要网络；在独立虚拟环境安装 `pip-audit`，
避免审计工具改变应用的依赖环境。npm 镜像可能不提供审计接口，审计命令显式使用官方 registry：

```powershell
python -m pip install pip-audit
python -m pip_audit --disable-pip --no-deps -r server/requirements-dev.lock
npm --prefix webui audit --registry=https://registry.npmjs.org
```

更新依赖后重新运行回归与打包检查，并等待对应最终提交的 CI 通过。审计结果只代表查询时
数据库已收录的问题，不等同于完整安全审计。

## 3. 生成和检查本地安装包

前端必须先构建；打包依赖需要已安装。使用已安装的构建依赖可避免构建隔离阶段联网：

本项目使用兼容当前依赖约束的许可证文件元数据。如果构建环境缺少 `setuptools>=68` 或 `wheel`，
先在允许联网的环境运行 `python -m pip install "setuptools>=68" wheel`。
`LICENSE` 是许可真值，`server/LICENSE` 为安装包副本；发布检查会核对两者一致。

```powershell
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir .checks/wheels ./server
python scripts/check_package.py
```

`.checks/wheels` 应只包含本次要验证的一个 `novelwb` wheel。如果已有其他版本，改用新的
`--wheel-dir` 并向 `check_package.py` 传入同一路径，不要覆盖或删除用户数据。
包验证检查资源、页面静态文件以及 mock 生成、审核和回放；使用现有本地依赖，不等同于
联网全新环境安装验收。

源码归档应在最终提交并完成索引检查之后创建：

```powershell
git archive --format=zip --output=.checks/novel-workbench-source.zip HEAD
```

该归档只包含 HEAD 已提交文件，不包含尚未提交的新文档，也不包含 Git 历史和被忽略的数据。
不要直接压缩整个工作目录作为源码包。

## 4. 公开前由维护者完成

- 确认许可证、版权署名及第三方素材范围；项目许可证不替代依赖和模型服务的各自条款。
- 核对提交作者邮箱等 Git 元数据，选择自己愿意公开的信息；文件扫描不包含这项检查。
- 填写真实仓库地址、安全问题接收渠道，实际运行远端 CI 后再添加状态徽章。
- 用演示合成项目制作截图或录像；真实模型案例需记录模型、提示词版本、成本、耗时与人工修改。
- 发布记录明确区分本地验证、远端 CI、浏览器验收与真实模型质量实验。

## 已知范围

当前程序以本机单用户工作台为目标，尚未具备公网多用户部署需要的完整认证和权限控制。
离线演示只提供 `spec00`，质量样例验证的是机械规则和故事约束；真实文学质量、长篇一致性、
服务费用及性能需单独评测。算法研究能力不能由这些工程检查替代证明。
