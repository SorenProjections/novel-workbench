#!/usr/bin/env bash
set -euo pipefail
export NOVELWB_LLM_ADAPTER=mock
python "$(dirname "$0")/smoke_run.py" "$@"
