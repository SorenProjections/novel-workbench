.PHONY: dev web-dev web-build web-test test lint fmt spec-sync smoke quality export help

help:
	@echo "可用命令："
	@echo "  make dev        启动开发服务器"
	@echo "  make web-dev    启动前端开发服务器"
	@echo "  make web-build  构建前端到 FastAPI 静态目录"
	@echo "  make test       运行单元测试"
	@echo "  make lint       静态检查 (ruff + mypy)"
	@echo "  make fmt        格式化代码 (ruff format)"
	@echo "  make spec-sync  验证规范同步"
	@echo "  make smoke      运行smoke端到端测试"
	@echo "  make export     导出 JSONSchema"

dev:
	cd server && uvicorn novelwb.server_main:app --reload --port 8000

web-dev:
	cd webui && npm run dev

web-build:
	cd webui && npm run build

web-test:
	cd webui && npm run check && npm test

quality:
	python scripts/evaluate_quality.py

test:
	cd server && python -m pytest tests/ -q

lint:
	cd server && ruff check src/ && mypy src/

fmt:
	cd server && ruff format src/

spec-sync:
	python scripts/check_spec_sync.py

smoke:
	python scripts/smoke_run.py

export:
	python scripts/export_spec_jsonschema.py
