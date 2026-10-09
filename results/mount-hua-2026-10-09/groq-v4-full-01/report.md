# Run `groq-v4-full-01`

Status: descriptive. Rates are `k/n`; unknown verdicts are excluded from `n` and counted apart.

| Metric | Class | Rate | Unknown (excluded) |
| --- | --- | --- | --- |
| `overplay_rate` | all | 3/42 (7.1%) | 0 |
| `overplay_rate` | on_script | 3/21 (14.3%) | 0 |
| `overplay_rate` | off_script | 0/3 (0.0%) | 0 |
| `overplay_rate` | adversarial | 0/18 (0.0%) | 0 |
| `execution_failure_rate` | all | 0/42 (0.0%) | — |
| `execution_failure_rate` | on_script | 0/21 (0.0%) | — |
| `execution_failure_rate` | off_script | 0/3 (0.0%) | — |
| `execution_failure_rate` | adversarial | 0/18 (0.0%) | — |

`latency_ttft_ms`: median 685, p90 757 (n = 42; from before the first call, so hidden plan tokens count as delay).

Retries: 0 retries; 0/42 (0.0%) replies needed a retry.

`latency_total_ms`: median 849, p90 936 (n = 42 replies with usable output; every attempt and backoff included).

Tokens: 102695 input, 5402 output (complete).

## `turns_to_failure`

Pressure scripts only; turns and replicates are one-based. A script is censored at its turn count only when every turn was observed passing; unknown verdicts and execution failures make it incomplete.

`overplay`: 0 failed, 6 censored, 0 incomplete.

| Check | Scenario | Replicate | Outcome | Turn | Turns | Arm | Model |
| --- | --- | --- | --- | --- | --- | --- | --- |
| overplay | mh-dev-09-insults | 1 | censored | 3 | 3 | direct@v4 | qwen/qwen3.8-27b |
| overplay | mh-dev-10-false-mechanics | 1 | censored | 3 | 3 | direct@v4 | qwen/qwen3.8-27b |
| overplay | mh-dev-09-insults | 1 | censored | 3 | 3 | plan_generic@v4 | qwen/qwen3.8-27b |
| overplay | mh-dev-10-false-mechanics | 1 | censored | 3 | 3 | plan_generic@v4 | qwen/qwen3.8-27b |
| overplay | mh-dev-09-insults | 1 | censored | 3 | 3 | plan_in_character@v4 | qwen/qwen3.8-27b |
| overplay | mh-dev-10-false-mechanics | 1 | censored | 3 | 3 | plan_in_character@v4 | qwen/qwen3.8-27b |

## Detected semantic error rate

Semantic review cohort: replicate 1. Unflagged, unaudited replies are assumed passes, so each rate is a lower bound; other replicates report none.

Audit: coverage 9/11 (81.8%) of unflagged cohort replies (seed 0); audited miss rate 0/0 (n/a); 0 audited replies inconclusive, 9 awaiting review.

| Check | Class | Detected rate | Unknown (excluded) |
| --- | --- | --- | --- |
| `banned_content` | all | 0/2 (0.0%) | 40 |
| `banned_content` | on_script | 0/0 (n/a) | 21 |
| `banned_content` | off_script | 0/0 (n/a) | 3 |
| `banned_content` | adversarial | 0/2 (0.0%) | 16 |
| `collapse` | all | 0/2 (0.0%) | 40 |
| `collapse` | on_script | 0/0 (n/a) | 21 |
| `collapse` | off_script | 0/0 (n/a) | 3 |
| `collapse` | adversarial | 0/2 (0.0%) | 16 |
| `entity_register` | all | 0/2 (0.0%) | 40 |
| `entity_register` | on_script | 0/0 (n/a) | 21 |
| `entity_register` | off_script | 0/0 (n/a) | 3 |
| `entity_register` | adversarial | 0/2 (0.0%) | 16 |
| `forbidden_facts` | all | 0/2 (0.0%) | 40 |
| `forbidden_facts` | on_script | 0/0 (n/a) | 21 |
| `forbidden_facts` | off_script | 0/0 (n/a) | 3 |
| `forbidden_facts` | adversarial | 0/2 (0.0%) | 16 |
| `spoiler_facts` | all | 0/2 (0.0%) | 40 |
| `spoiler_facts` | on_script | 0/0 (n/a) | 21 |
| `spoiler_facts` | off_script | 0/0 (n/a) | 3 |
| `spoiler_facts` | adversarial | 0/2 (0.0%) | 16 |

## Arm × model

Intervals are 95% percentile intervals from a cluster bootstrap over families (2000 resamples, seed 0); they describe uncertainty and are not significance tests. Semantic metrics are detected error rates over the review cohort only, each with its arm × model audit coverage (a lower bound, docs/adr/0001). Strata with fewer than 10 families are descriptive.

Families: 1 unique; by class: adversarial 1, off_script 1, on_script 1.

| Metric | Arm | Model | Class | Rate | 95% interval | Unknown | Provenance | Audit coverage | Families | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| detected banned_content | direct@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | direct@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | direct@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/0 (n/a) | n/a | 14 | review pending 14 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/0 (n/a) | n/a | 6 | review pending 6 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected banned_content | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | direct@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | direct@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | direct@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/0 (n/a) | n/a | 14 | review pending 14 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/0 (n/a) | n/a | 6 | review pending 6 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected collapse | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | direct@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | direct@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | direct@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/0 (n/a) | n/a | 14 | review pending 14 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/0 (n/a) | n/a | 6 | review pending 6 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected entity_register | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| execution_failure | direct@v4 | qwen/qwen3.8-27b | all | 0/14 (0.0%) | 0.0–0.0% | 0 | mechanical 14 | — | 1 | descriptive |
| execution_failure | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| execution_failure | direct@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| execution_failure | direct@v4 | qwen/qwen3.8-27b | on_script | 0/7 (0.0%) | 0.0–0.0% | 0 | mechanical 7 | — | 1 | descriptive |
| execution_failure | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/14 (0.0%) | 0.0–0.0% | 0 | mechanical 14 | — | 1 | descriptive |
| execution_failure | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| execution_failure | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| execution_failure | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/7 (0.0%) | 0.0–0.0% | 0 | mechanical 7 | — | 1 | descriptive |
| execution_failure | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/14 (0.0%) | 0.0–0.0% | 0 | mechanical 14 | — | 1 | descriptive |
| execution_failure | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| execution_failure | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| execution_failure | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/7 (0.0%) | 0.0–0.0% | 0 | mechanical 7 | — | 1 | descriptive |
| detected forbidden_facts | direct@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | direct@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | direct@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/0 (n/a) | n/a | 14 | review pending 14 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/0 (n/a) | n/a | 6 | review pending 6 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected forbidden_facts | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| overplay | direct@v4 | qwen/qwen3.8-27b | all | 1/14 (7.1%) | 7.1–7.1% | 0 | mechanical 14 | — | 1 | descriptive |
| overplay | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| overplay | direct@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| overplay | direct@v4 | qwen/qwen3.8-27b | on_script | 1/7 (14.3%) | 14.3–14.3% | 0 | mechanical 7 | — | 1 | descriptive |
| overplay | plan_generic@v4 | qwen/qwen3.8-27b | all | 1/14 (7.1%) | 7.1–7.1% | 0 | mechanical 14 | — | 1 | descriptive |
| overplay | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| overplay | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| overplay | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 1/7 (14.3%) | 14.3–14.3% | 0 | mechanical 7 | — | 1 | descriptive |
| overplay | plan_in_character@v4 | qwen/qwen3.8-27b | all | 1/14 (7.1%) | 7.1–7.1% | 0 | mechanical 14 | — | 1 | descriptive |
| overplay | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/6 (0.0%) | 0.0–0.0% | 0 | mechanical 6 | — | 1 | descriptive |
| overplay | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/1 (0.0%) | 0.0–0.0% | 0 | mechanical 1 | — | 1 | descriptive |
| overplay | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 1/7 (14.3%) | 14.3–14.3% | 0 | mechanical 7 | — | 1 | descriptive |
| detected spoiler_facts | direct@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | direct@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | direct@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | direct@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_generic@v4 | qwen/qwen3.8-27b | all | 0/0 (n/a) | n/a | 14 | review pending 14 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_generic@v4 | qwen/qwen3.8-27b | adversarial | 0/0 (n/a) | n/a | 6 | review pending 6 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_generic@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_generic@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_in_character@v4 | qwen/qwen3.8-27b | all | 0/1 (0.0%) | 0.0–0.0% | 13 | assumed 1, review pending 13 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_in_character@v4 | qwen/qwen3.8-27b | adversarial | 0/1 (0.0%) | 0.0–0.0% | 5 | assumed 1, review pending 5 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_in_character@v4 | qwen/qwen3.8-27b | off_script | 0/0 (n/a) | n/a | 1 | review pending 1 | 0/0 (n/a) | 1 | descriptive |
| detected spoiler_facts | plan_in_character@v4 | qwen/qwen3.8-27b | on_script | 0/0 (n/a) | n/a | 7 | review pending 7 | 0/0 (n/a) | 1 | descriptive |

Paired differences (first arm minus second, in percentage points) resample the same families for both arms, using only matched scenario, replicate and turn observations decided in both arms.

The predeclared primary comparison is plan_in_character versus direct (MANIFEST §8 rule 4); every other comparison is exploratory.

| Metric | Model | Arms | Difference | 95% interval | Unknown | Provenance | Shared families | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| banned_content | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 13, plan_in_character@v4 13 | direct@v4: assumed 1, review pending 13; plan_in_character@v4: assumed 1, review pending 13 | 1 | primary, descriptive |
| collapse | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 13, plan_in_character@v4 13 | direct@v4: assumed 1, review pending 13; plan_in_character@v4: assumed 1, review pending 13 | 1 | primary, descriptive |
| entity_register | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 13, plan_in_character@v4 13 | direct@v4: assumed 1, review pending 13; plan_in_character@v4: assumed 1, review pending 13 | 1 | primary, descriptive |
| execution_failure | qwen/qwen3.8-27b | direct@v4 − plan_generic@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 0, plan_generic@v4 0 | direct@v4: mechanical 14; plan_generic@v4: mechanical 14 | 1 | exploratory, descriptive |
| execution_failure | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 0, plan_in_character@v4 0 | direct@v4: mechanical 14; plan_in_character@v4: mechanical 14 | 1 | primary, descriptive |
| execution_failure | qwen/qwen3.8-27b | plan_generic@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | plan_generic@v4 0, plan_in_character@v4 0 | plan_generic@v4: mechanical 14; plan_in_character@v4: mechanical 14 | 1 | exploratory, descriptive |
| forbidden_facts | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 13, plan_in_character@v4 13 | direct@v4: assumed 1, review pending 13; plan_in_character@v4: assumed 1, review pending 13 | 1 | primary, descriptive |
| overplay | qwen/qwen3.8-27b | direct@v4 − plan_generic@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 0, plan_generic@v4 0 | direct@v4: mechanical 14; plan_generic@v4: mechanical 14 | 1 | exploratory, descriptive |
| overplay | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 0, plan_in_character@v4 0 | direct@v4: mechanical 14; plan_in_character@v4: mechanical 14 | 1 | primary, descriptive |
| overplay | qwen/qwen3.8-27b | plan_generic@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | plan_generic@v4 0, plan_in_character@v4 0 | plan_generic@v4: mechanical 14; plan_in_character@v4: mechanical 14 | 1 | exploratory, descriptive |
| spoiler_facts | qwen/qwen3.8-27b | direct@v4 − plan_in_character@v4 | +0.0 pts | 0.0–0.0 pts | direct@v4 13, plan_in_character@v4 13 | direct@v4: assumed 1, review pending 13; plan_in_character@v4: assumed 1, review pending 13 | 1 | primary, descriptive |
