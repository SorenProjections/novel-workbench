"""FastAPI 应用入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from novelwb.api.routers import chapters, pipeline, projects
from novelwb.engine.task_service import TaskService

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


@app.exception_handler(FileNotFoundError)
async def missing_artifact(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})
