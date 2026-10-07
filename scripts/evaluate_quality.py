"""Run the fixed offline quality corpus; return nonzero on a regression."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "src"))
from novelwb.engine.quality_benchmark import evaluate_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="离线正文与故事约束回归评测")
    parser.add_argument("--corpus", type=Path, default=ROOT / "server/tests/fixtures/quality/corpus.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_corpus(args.corpus)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in report["results"]:
        label = "PASS" if result["passed"] else "FAIL"
        print(f"[{label}] {result['id']}: score={result['quality']['score']}")
        for failure in result["failures"]:
            print(f"  {failure}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
