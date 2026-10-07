.PHONY: dev web-dev web-build web-test test lint fmt spec-sync smoke quality export demo release-check delivery-test help

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
	@echo "  make demo       启动无密钥离线审核演示"
	@echo "  make release-check 检查本地文件与 Git 历史"
	@echo "  make delivery-test 验证演示与发布检查脚本"

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

demo:
	python scripts/demo.py

release-check:
	python scripts/check_release.py --history

delivery-test:
	python -m pytest scripts/tests -q
