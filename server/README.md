# Novel Workbench backend

面向长篇小说的 FastAPI 创作工作台后端，包含逐文件人工审核、分层故事资产、上下文编译、
后台任务回放及提交恢复。配套前端使用 React / TypeScript。

从项目源码构建时，应先在仓库根目录执行 `npm --prefix webui run build`，再生成 wheel，
以便携带网页与静态资源。源码仓库的 README、SPEC_v1.md、CONTRIBUTING.md 和
docs/RELEASING.md 分别提供启动、行为契约、贡献与验收说明。

安装后可以通过 `python -m uvicorn novelwb.server_main:app --host 127.0.0.1 --port 8000`
启动本机服务。真实模型调用需单独配置服务方凭据；当前 API 尚未提供多用户认证，
不应将本机演示视为完成加固的公网服务。

无密钥演示使用源码仓库中的 `scripts/demo.py` 和合成 fixture，安装包自身不包含
完整小说的离线生成模型。

项目采用 MIT License，完整许可随安装包的 LICENSE 分发。
网页第三方依赖的许可位于 `novelwb/web/THIRD_PARTY_NOTICES.txt`。
