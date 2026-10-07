"""Export registered Pydantic contracts into a selected output directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "src"))
from novelwb.core.schema_registry import all_schema_names, get_schema


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "server/src/novelwb/core/schemas/generated")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in sorted(all_schema_names()):
        schema = get_schema(name).model_json_schema()
        (args.output / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Exported {len(all_schema_names())} schemas to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
