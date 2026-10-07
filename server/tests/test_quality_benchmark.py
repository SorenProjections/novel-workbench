"""Golden prose and story-constraint examples, without model credentials."""
import json
from pathlib import Path

import pytest

from novelwb.engine.quality_benchmark import evaluate_case

CORPUS = Path(__file__).parent / "fixtures/quality/corpus.json"
CASES = json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_fixed_quality_corpus(case):
    result = evaluate_case(case)
    assert result["passed"], result["failures"]
