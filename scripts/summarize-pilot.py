"""Create descriptive measurements and a shuffled review worksheet from recordings.

No provider calls and no semantic success inference. Run with --help for usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

from npcbench.checks.overplay import count_tics


def summarize(records: list[dict]) -> dict:
    groups = defaultdict(list)
    for record in records:
        groups[record["arm_id"]].append(record)
    result = {}
    for arm, calls in sorted(groups.items()):
        replies = [c for c in calls if c["call_kind"] == "reply"]
        usable = [c for c in replies if c["failure"] is None]
        plans = [c for c in calls if c["call_kind"] == "plan" and c["failure"] is None]
        budgets = sum(
            len(c["response_text"].split()) <= 80
            and count_tics(c["response_text"], ["young disciple", "this old man", "hear me well"])
            <= 1
            for c in usable
        )
        labels = ("Goal:", "Points:", "Check:", "Tradeoff:")
        strict = sum(
            len(lines := c["response_text"].strip().splitlines()) == 4
            and all(line.startswith(label) for line, label in zip(lines, labels, strict=True))
            and len(c["response_text"].split()) <= 60
            for c in plans
        )
        by_turn = defaultdict(list)
        for c in calls:
            by_turn[(c["scenario_id"], c["turn_index"], c["replicate"])].append(c)
        latency = [
            sum(c["timings"]["total_ms"] + c["backoff_ms"] for c in turn)
            for turn in by_turn.values()
            if any(c["call_kind"] == "reply" and c["failure"] is None for c in turn)
        ]
        result[arm] = {
            "attempts": len(calls),
            "reply_attempts": len(replies),
            "usable_replies": len(usable),
            "failed_attempts": sum(c["failure"] is not None for c in calls),
            "length_and_tic_pass": budgets,
            "replies_using_supplied_saying": sum(
                any(
                    saying in c["response_text"].lower()
                    for saying in (
                        "haste prevents you from reaching your goal",
                        "going too far is as bad as falling short",
                    )
                )
                for c in usable
            ),
            "replies_ending_question": sum(
                c["response_text"].rstrip().endswith("?") for c in usable
            ),
            "successful_plans": len(plans),
            "four_line_60_word_plan_pass": strict,
            "plans_with_first_person_I": sum(
                bool(re.search(r"\bI\b", c["response_text"])) for c in plans
            ),
            "median_reply_pipeline_ms": statistics.median(latency) if latency else None,
            "input_tokens": sum(c["usage"]["input_tokens"] or 0 for c in calls),
            "output_tokens": sum(c["usage"]["output_tokens"] or 0 for c in calls),
            "calls_missing_usage": sum(
                c["usage"]["input_tokens"] is None or c["usage"]["output_tokens"] is None
                for c in calls
            ),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    raw = args.recordings.read_bytes()
    records = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line]
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"recordings_sha256": hashlib.sha256(raw).hexdigest(), "arms": summarize(records)}
    (args.out / "measurements.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    replies = [c for c in records if c["call_kind"] == "reply" and c["failure"] is None]
    random.Random(20261009).shuffle(replies)
    worksheet, mapping = [], []
    for number, c in enumerate(replies, 1):
        label = f"R{number:02}"
        mapping.append({"label": label, "key": c["key"], "arm_id": c["arm_id"]})
        history = [m for m in c["request"]["messages"] if m["role"] != "system"]
        worksheet.append(
            {
                "label": label,
                "scenario_id": c["scenario_id"],
                "turn_index": c["turn_index"],
                "context": history,
                "reply": c["response_text"],
            }
        )
    for name, value in (("review-worksheet.json", worksheet), ("review-map.json", mapping)):
        (args.out / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
