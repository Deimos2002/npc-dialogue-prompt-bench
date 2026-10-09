"""Ensure portfolio measurements include planning/retries rather than reply time alone."""

import importlib.util
from pathlib import Path


def test_summary_accounts_for_pipeline_cost_and_unusable_attempts():
    spec = importlib.util.spec_from_file_location(
        "pilot_summary", Path(__file__).parents[2] / "scripts/summarize-pilot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def call(kind, text, duration, *, failure=None, backoff=0, tokens=10):
        return {
            "arm_id": "plan_in_character@v4",
            "scenario_id": "s1",
            "turn_index": 0,
            "replicate": 0,
            "call_kind": kind,
            "response_text": text,
            "failure": failure,
            "backoff_ms": backoff,
            "timings": {"total_ms": duration},
            "usage": {"input_tokens": tokens, "output_tokens": tokens},
        }

    records = [
        call("plan", "Goal: I advise speed.\nPoints: 20\nCheck: none\nTradeoff: resilience", 100),
        call("reply", "", 50, failure="transport", tokens=None),
        call("reply", "word " * 81, 200, backoff=1000),
    ]
    result = module.summarize(records)["plan_in_character@v4"]
    assert result["median_reply_pipeline_ms"] == 1350
    assert result["input_tokens"] == 20
    assert result["calls_missing_usage"] == 1
    assert result["usable_replies"] == 1
    assert result["length_and_tic_pass"] == 0
    assert result["four_line_60_word_plan_pass"] == 1
    assert result["plans_with_first_person_I"] == 1
