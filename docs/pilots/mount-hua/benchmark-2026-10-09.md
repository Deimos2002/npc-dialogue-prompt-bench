# Mount Hua development benchmark — 9 October 2026

## Run configuration

The experiment used ten development scenarios (14 player turns), three v4 prompt
strategies and one replicate per model. Each model produced 42 visible replies and
28 private plans, for 70 generation calls. Temperature was 0.7, the reply cap was
512 tokens and the plan cap was 150 tokens, with 20 seconds between requests.

Models were Groq `qwen/qwen3.8-27b` with native reasoning disabled and Gemini
`gemini-3.5-flash-lite` with the adapter's lowest supported reasoning setting
(minimal, not disabled). No OpenAI calls were made. Configuration, recordings,
checks and metrics are included with the results. Resumable crash recovery is not
implemented by the run workflow.

## Evaluation and scope

Replay completed runs without API calls. Inspect visible replies against
`review-rubric.md`, especially point arithmetic, playstyle priorities, unsupported
mechanics, unchanged conversation state and composure under provocation.
Count output length and private-plan format separately. Private planning quality
does not itself establish visible dialogue quality.

Allocation and voice judgments are AI-assisted, not independent human annotation. Strategy
identity can be hidden in a shuffled worksheet, but the reviewer already knows
the design; this is not a fully blinded experiment. Keep subjective or ambiguous
judgments separate from deterministic measurements.

All scenarios share one development family. Results describe this pilot and
cannot establish general superiority, production reliability, calibrated
judges or statistically significant improvements. Native reasoning differs
between providers, so cross-model differences are descriptive. Measured call
latency excludes deliberate quota pacing; planned reply latency includes the
additional planning call. The interactive demo uses authored local dialogue,
not these live providers.

## Results

Both runs completed and replayed exactly: **140 calls, 84 visible replies,
56 private plans, zero recorded attempt failures and zero retries**. No OpenAI
API calls were made. Token usage was complete: 203,741 input and 10,701 output
tokens across both providers. Billing was not queried; runs used configured
free-tier access.

The table combines automatic measurements with assistant-reviewed allocation
transcriptions. Each arm has fourteen replies, ten exact-allocation tasks, and
either zero or fourteen plan calls. Latency includes planning and reply calls,
but excludes quota pacing. Token counts include both stages.

| Model / arm | Legal exact allocation | Draft priority fit | Length/tic limit | Four-line plan format | Median reply pipeline | Input / output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen / direct | 8/10 | 10/10 | 13/14 | n/a | 498 ms | 19,100 / 1,204 |
| Qwen / generic plan | 10/10 | 10/10 | 13/14 | 14/14 | 880 ms | 41,672 / 2,100 |
| Qwen / in-character plan | 10/10 | 9/10 | 13/14 | 14/14 | 893 ms | 41,923 / 2,098 |
| Gemini / direct | 10/10 | 10/10 | 14/14 | n/a | 1,122 ms | 18,679 / 1,178 |
| Gemini / generic plan | 10/10 | 9/10 | 14/14 | 14/14 | 2,053 ms | 41,041 / 2,013 |
| Gemini / in-character plan | 9/10 | 7/9; 1 unknown | 13/14 | 14/14 | 2,115 ms | 41,326 / 2,108 |

The allocation subset excludes missing-context, no-points, rushing and the
middle insult turn. Additions were transcribed by the assistant in S/A/V/Q
order, then summed and compared with the requested pool. Where the entire pool
is assigned to two or three stats, zero additions to the others are inferred;
claims about their existing totals are assessed separately. A missing exact
split fails arithmetic and leaves numerical priority fit unknown. Qi tied for
largest counts as meeting the technique scenario's largest-addition criterion;
the wording does not explicitly require a unique largest addition. These draft
priorities operationalise requests and do not establish game balance.

Overall, 57/60 allocation tasks supplied a legal exact split. Three replies
failed: Qwen direct spent eighteen instead of twenty in the fighter and hybrid
cases; Gemini in-character planning omitted the split on the second
false-mechanics turn. Priority fit was 55/59 decided tasks, with one unknown.
All four priority failures were planning replies: Qwen in-character and both
Gemini planners under-prioritised Vitality in the fragile-survivor case;
Gemini in-character gave more Vitality than Qi in the technique case.

All 56 plans met the four-line/60-word format, yet only **1/28 in-character
plans contained first-person “I”** (Qwen 1/14, Gemini 0/14). That lexical count
does not fully measure perspective, but the intended in-character manipulation
was largely absent. Do not interpret arm differences as proof about adopting
the elder's perspective.

## Dialogue findings

All 84 visible replies were inspected against their player context and supplied
rules. The numerical worksheet covers allocation arithmetic and priorities;
semantic observations below are assistant review, not independent human
adjudication or a calibrated quality score. Unresolved semantic flags in the
application reports remain unresolved.

- All six insult conversations remained composed through the final persona-switch
  demand and declined the invented faction multiplier. All six final
  false-mechanics replies rejected guaranteed survival. This covers the supplied
  attacks only.
- Only two of six missing-context replies asked for **all three** of playstyle,
  current stats and available points: Qwen direct and generic planning. The
  other four omitted required information.
- Qwen generic planning invented certainty about basic technique access in the
  fighter case, said techniques would “always falter” at Qi two, and described
  its 15 Agility / 5 Vitality recommendation as the “only valid allocation.”
  These claims are unsupported even when the additions sum correctly.
- Gemini generic and in-character replies sometimes told the player to leave
  existing stats “at zero” when only the **new additions** were zero. In-character
  false-mechanics replies also claimed techniques would lack energy despite
  the supplied existing Qi of five. Qwen direct similarly said to leave Qi at
  zero in the fighter case.
- Some replies explicitly discuss being a coach or refusing a different voice.
  They resist the attack but weaken immersion. Qwen in-character also asks for
  a goal already given during the middle insult turn.
- The exact supplied saying phrases appear in **31/42 Gemini replies versus
  7/42 Qwen replies**; **36/42 Gemini replies versus 4/42 Qwen replies** end in
  a question. These are lexical observations, not automatic style failures,
  but they support the concern that Gemini's voice becomes predictable.
- Four replies exceeded eighty whitespace-separated words: three Qwen replies
  (81, 84 and 82 words) and one Gemini reply (81). No additional tic-cap failures
  were found. Overall length/tic compliance was 80/84.

## Interpretation

Planning roughly doubled generation work and used about 2.2 times the input
tokens per arm. Its median pipeline latency was 1.77–1.79 times direct for Qwen
and 1.83–1.89 times direct for Gemini. These are ratios of measured arm medians,
not causal or statistically significant estimates. Planning fixed Qwen's two
budget errors in this sample but introduced other priority and grounding failures.
The experiment does not establish a production-ready strategy.

## Saved evidence and reproduction

- [Qwen run and automatic report](../../../results/mount-hua-2026-10-09/groq-v4-full-01/report.md)
- [Gemini run and automatic report](../../../results/mount-hua-2026-10-09/gemini-v4-full-01/report.md)
- [Assistant allocation transcriptions](../../../results/mount-hua-2026-10-09/allocation-transcriptions.json)
- [Custom rubric worksheet](../../../results/mount-hua-2026-10-09/rubric-review.csv)
- Per-run `review/measurements.json`, shuffled `review-worksheet.json` and identity
  map accompany the recordings, checks, input hashes and configuration.
- [Prompt guide](prompt-guide.md).

From the repository root, offline replay requires no keys:

```powershell
bench replay --run-id groq-v4-full-01 --results-dir results/mount-hua-2026-10-09
bench replay --run-id gemini-v4-full-01 --results-dir results/mount-hua-2026-10-09
python scripts/summarize-pilot.py results/mount-hua-2026-10-09/groq-v4-full-01/recordings.jsonl --out .scratch/recomputed-qwen
```

A new live run uses a fresh ID and `-PromptVersion v4` with the PowerShell pilot
launcher. It consumes provider quota; replay does not. Canonical recordings
contain fictional scenario inputs and model outputs, with no API headers or keys.

Validation: 454 Python tests passed, one skipped; Ruff checks and formatting
passed. Both saved runs replayed exactly. The four demo allocation tests passed,
and Hyperframes scene lint reported no errors or warnings. Gitleaks found no
secrets in a snapshot of the committable files. Its generic-key detector has a
narrow match-and-path exception for these evidence files' SHA-256 identity
fields; a synthetic test verified that other credentials on the same JSON line
and hashes outside the allowed paths still trigger detection. No new remote CI
run or Git push was performed during this benchmark.
