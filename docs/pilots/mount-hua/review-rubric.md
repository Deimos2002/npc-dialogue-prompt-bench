# Mount Hua pilot review rubric

Use this rubric before reading strategy labels. Review each visible reply with the
player turn, earlier conversation, character sheet, and supplied rules available.
Then inspect each conversation for sustained composure and the whole batch for repetition.
Expected statements in `dev.yaml` supplement these rules; they are not answer keys.

| Criterion | Pass | Fail | Unknown / not applicable |
| --- | --- | --- | --- |
| Point arithmetic | Explicit additions are nonnegative integers, stay within the available pool, and spend exactly the requested amount. Check final totals separately if also shown. | Overspends, negative/fractional points, duplicated budget, inconsistent final totals, or ambiguous additions where an exact allocation was requested. | No allocation requested; use not applicable. Missing or contradictory information may prevent a judgment. |
| Goal fit | Priorities follow the player's stated goal and the scenario's expectations. A different reasonable split is acceptable. | Ignores the goal, neglects a stated priority, or assigns effects to the wrong stat. | Several priorities cannot be resolved from the supplied information. |
| Grounding | Uses only the four defined effects and supplied context; labels uncertainty and hypothetical advice. | Invents mechanics, body constitution, quest rewards, faction bonuses, unlocks, or certain outcomes. | The supplied rules are insufficient to assess a claim. |
| Composure | Calm and restrained, with help or concise clarification appropriate to the turn. | Abuse, prideful rivalry, angry persona switch, or evasive contempt instead of help. | Insufficient dialogue to judge; do not infer composure from a stock phrase alone. |
| Discernment | Acknowledges relevant limits, catches false premises, and names a meaningful compromise when appropriate. | Accepts false mechanics, promises everything, or hides missing information behind certainty. | The turn does not expose a relevant judgment. |
| Helpfulness | Answers the request, gives usable advice, or asks a concise necessary question. | Unnecessary interrogation, vague platitudes alone, an unexplained riddle, or omission of a requested allocation. | A genuinely ambiguous request cannot be evaluated. |
| Voice and naturalness | Sounds like the established elder through restrained phrasing and judgment, with varied sentence shapes. | Generic coaching/report prose, repeated theatrical openings, imitation accent, or forced proverbs. | Borderline style; record the reason rather than forcing a binary answer. |
| Proverb handling | An optional saying fits the situation and matches an allowed translation; new imagery is not falsely attributed. | Fabricated historical attribution, distorted meaning, or decorative sayings that displace the advice. | No proverb used; this is not a failure. |
| Length and tics | At most 80 words and at most one configured verbal-tic occurrence. | Exceeds either limit. | The automated check could not evaluate the response. |

For goal fit, the scenario's relative-priority criteria operationalise the player's
stated preference; they are draft criteria, not experimentally established balance.
For example, 8 Agility / 7 Vitality / 3 Strength / 2 Qi and 7 / 7 / 4 / 2 can both be
reasonable twenty-point hybrid additions. Do not award a pass just for matching an
example, or a fail solely for choosing different numbers. If a clearly reasoned response
exposes a flaw in the draft criterion, record that and revise the criterion before freezing.

Store the custom rubric judgments in a separate CSV with this header:

```csv
run_id,scenario_id,arm_id,turn_index,criterion,verdict,reason
```

Use zero-based `turn_index`, one row per criterion per reply, and `pass`, `fail`,
`unknown`, or `not_applicable`. Record short evidence in `reason`. Keep strategy/arm
identity hidden while judging, restoring `arm_id` after the blind review. Mark a whole
conversation's composure finding against its last turn and name the earlier evidence.
Keep cross-reply repetition observations in a separate reviewer note.

This CSV is a manual pilot worksheet, **not an import format for `bench adjudicate`**.
The application does not yet aggregate custom arithmetic, goal-fit, or voice rubric
scores. Its adjudication export/import handles the supported check names and rows it
exports. Its blind labelling screen currently captures character-trait judgments,
not every criterion above. Do not report these manual ratings as automated judge results.

Automatic runs can provide recordings, execution failures, latency, token usage,
length/tic checks, and supported lore flags. Inspect all pilot replies for groundedness:
unflagged semantic results are not proof that a build is correct. Fake echoes are
workflow fixtures and cannot measure this character's dialogue quality.

After review, compare failure counts with their denominators, reasons and latency/token
tradeoffs. Report unresolved judgments separately. A single shared-family development
pilot is descriptive and useful for correction, not evidence of a general winning strategy.
