"""FastAPI 应用入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from novelwb.api.routers import chapters, model_settings, pipeline, projects
from novelwb.engine.task_service import TaskService
from novelwb.storage.model_settings_store import SettingsConflict

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if pipeline.tasks.closed:
        pipeline.tasks = TaskService()
    service = pipeline.tasks
    try:
        yield
    finally:
        service.close()


app = FastAPI(
    title="Novel Workbench API",
    version="0.1.0",
    description="小说工业化流水线 REST API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(chapters.router)
app.include_router(model_settings.router)

if _WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_WEB_DIR), html=True), name="ui")


@app.get("/", response_model=None)
def index() -> FileResponse | dict[str, str]:
    if _WEB_DIR.exists():
        return FileResponse(_WEB_DIR / "index.html")
    return {"status": "ok"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.exception_handler(ValueError)
async def invalid_identifier(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SettingsConflict)
async def settings_conflict(request: Request, exc: SettingsConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/settings/models"):
        # FastAPI's default includes the submitted input, which may contain an API key.
        labels = {
            "name": "配置名称",
            "protocol": "API 协议",
            "base_url": "API 基础地址",
            "model": "模型 ID",
            "api_key": "API Key",
            "revision": "配置版本（请刷新）",
            "max_output_tokens": "最大输出 tokens",
            "timeout_seconds": "超时秒数",
            "max_retries": "重试次数",
        }
        fields = "、".join(
            dict.fromkeys(labels.get(str(error["loc"][-1]), "请求内容") for error in exc.errors())
        )
        return JSONResponse(
            status_code=422, content={"detail": f"配置字段不合法，请检查：{fields}"}
        )
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(FileNotFoundError)
async def missing_artifact(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})
