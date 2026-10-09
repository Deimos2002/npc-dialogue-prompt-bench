# NPC Dialogue Prompt Bench

The language of a benchmark that compares prompt strategies for LLM-driven game characters
on original lore. `MANIFEST.md` is the contract; this file fixes the words it uses.

## Experiment

**Strategy**:
An approach to prompting the character: `direct`, `plan_generic` or `plan_in_character`.
_Avoid_: arm (when the version is not meant), method

**Arm**:
One strategy at one pinned prompt version; the unit compared within a run.
_Avoid_: strategy (when a version is meant), variant

**Run**:
One frozen configuration (scenario version, arms, models, judge, sampling parameters,
execution order) and every replicate executed under it. A finished run is never altered; a new
comparison is a new run.
_Avoid_: experiment, job

**Development run**:
A run on the dev split whose results may inform prompt edits; pilots are development runs.
_Avoid_: pilot (as a separate kind), trial

**Comparison run**:
A predeclared run of two or more frozen arms on the dev split, such as a prompt correction
before and after.
_Avoid_: A/B test, evaluation (on dev)

**Evaluation run**:
A predeclared run on the test split; the only kind whose results are headline evidence.
Any test-split comparison is one. An arm edited after its results were seen needs a fresh
held-out set for confirmatory evidence.
_Avoid_: test run, benchmark run

**Replicate**:
One complete sweep of every scenario under every arm and model within a run. Stored
indices start at 0; reports show replicates from 1.
_Avoid_: pass, run, repeat

**Turn**:
One player line and the reply opportunity it creates, counted even when execution fails to
produce a reply. Reports number turns from 1.
_Avoid_: message, exchange

**Call**:
One logical model request in producing a reply, identified by model, call kind (plan or
reply) and turn; made of one or more attempts.
_Avoid_: reply, generation

**Attempt**:
One physical try at a call; the thing that is recorded.
_Avoid_: call, request

**Retry**:
A second attempt at a call after a timeout or transport failure; at most one per call.
Parse failures and truncation are never retried.
_Avoid_: rerun, replicate

**Execution failure**:
A reply that has no usable output because either of its required calls failed on its final
attempt.
_Avoid_: error, crash

**Reply**:
The player-visible output of one turn, produced by one call (direct) or a plan call
followed by a reply call; the thing that checks and metrics count.
_Avoid_: response, call, output

**Plan**:
The hidden output of a plan call; recorded for audit, never shown to the player, never
carried into later turns.
_Avoid_: reasoning, thinking

## World and characters

**Slot**:
A position in the moral range the cast must cover: A (flawed but good), B (neutral,
knowledge-heavy), C (self-serving egoist).
_Avoid_: character (when the role is meant)

**Character**:
A concrete original NPC that fills a slot, with its own identity and sheet.
_Avoid_: slot, persona, NPC (when a specific sheet is meant)

**Not yet known**:
The status of a fact the character cannot know at the scenario's story point; a property of
a fact for one character at one story point, not of the fact itself.
_Avoid_: unknown

**Secret**:
The status of a fact the character knows at the story point but must not disclose unless
its reveal condition holds.
_Avoid_: hidden, unknown

## Scenarios

**Allowances**:
What one scenario explicitly lets the character do that would otherwise be an error, each
scoped to a specific proposition, entity or kind of invention. No allowance licenses
contradicting established facts or revealing a protected proposition; empty allowances
leave the character sheet and entity register in force.
_Avoid_: exceptions, permissions (unqualified)

**Family**:
A set of scenarios treated as one resampling unit because they share a target fact or are
substantive paraphrases or escalations of one another; may span classes, never characters.
Authorship does not establish independence, and separate families are not proven
independent.
_Avoid_: group, category, theme, independent sample

**Economic exploit**:
An adversarial attempt to make the character accept a trade it would never rationally
accept, such as legendary goods for a worthless item.
_Avoid_: scam, bad trade

**Family rationale**:
The reviewer's recorded reason a family groups its scenarios. A reason two closely related
families stay apart is recorded once and applies both ways.
_Avoid_: family note, description

**Protected proposition**:
The specific claim a spoiler probe forbids the character to disclose.
_Avoid_: secret (when the claim rather than the fact status is meant), target

**Permitted acknowledgement**:
What a probe explicitly lets the character admit without disclosing its protected
proposition, such as that a route exists.
_Avoid_: hint, partial answer

**Withholding**:
A reply that neither discloses the protected proposition nor falsely denies what the
character knows, and admits no more than the permitted acknowledgements.
_Avoid_: refusal, evasion (as a synonym)

**Evasion**:
A withholding reply that does not engage with the question at all.
_Avoid_: deflection, non-answer

**False denial**:
A reply denying knowledge or truth that the character holds; a lore error unless the
scenario explicitly permits that deception.
_Avoid_: lie (unqualified), withholding

## Scoring

**Mechanical check**:
A deterministic check whose frozen counting or matching rule fully decides the outcome, so
its flag is its verdict.
_Avoid_: rule check, automatic check

**Semantic check**:
A check whose flags need context to resolve, so a flag alone never decides the verdict.
_Avoid_: soft check, judge check

**Flag**:
A deterministic check's raw hit on a reply, before any human resolution.
_Avoid_: error, verdict, violation

**Adjudication**:
A human's resolution of a flag or an audited reply as error, not error or unknown.
_Avoid_: label, review

**Label**:
A blind per-trait yes/no answer from labelling mode, used only to validate the judge.
_Avoid_: rating, adjudication

**Verdict**:
The final per-reply, per-check outcome that metrics consume: pass, fail or unknown, with
its provenance and review status.
_Avoid_: flag, result, score

**Pass**:
A verdict value: the reply meets the check.
_Avoid_: replicate, sweep

**Provenance**:
How a completed verdict was reached: mechanical, adjudicated, assumed or judge; absent
while review is pending. Human adjudication overrides any other provenance; the overridden
judge output is kept for audit.
_Avoid_: source, origin

**Review status**:
Whether a verdict's review is pending or complete; a pending verdict is always unknown and
has no provenance.
_Avoid_: provenance, state

**Judge validation status**:
Whether the pinned judge configuration is validated or indicative for one specific check or
trait; any metric using an indicative judge verdict is indicative.
_Avoid_: judge quality, trusted judge

**Unknown**:
A verdict that decides neither pass nor fail: a flag awaiting review, a review that ended
inconclusive, or a mechanical check that could not be evaluated; never counted as a pass.
_Avoid_: not yet known, pending

**Assumed pass**:
The verdict of a semantic check on a reply that was neither flagged nor audited; kept
distinct from a pass a human confirmed.
_Avoid_: pass (unqualified), clean

**Semantic review cohort**:
The replies a run declares for adjudication and audit before it executes; assumed passes
exist only inside it. In v0.1 it is replicate 1.
_Avoid_: audited set, sample

**Detected semantic error rate**:
The share of replies with a failed semantic verdict, counting assumed passes as passes;
a lower bound read alongside the audit's miss rate, not the underlying error rate.
_Avoid_: error rate (unqualified)

**Lore error**:
A reply asserting something false against world truth or character belief, or naming an
entity outside the register; a false denial of a secret is one. A lie the scenario
explicitly permits is not.
_Avoid_: hallucination, spoiler

**Turns to failure**:
The first turn whose reply fails a given check in a pressure script. A script is
right-censored at its turn count only when every turn was observed without failure; unknown
verdicts or an early execution failure make the observation incomplete, not held.
_Avoid_: survival length

**Collapse**:
A reply in which the character's own voice clearly abandons the role at least once, such
as an appended AI disclaimer; quoted or discussed text does not count.
_Avoid_: break, refusal

**In-character refusal**:
A refusal spoken entirely in the character's voice; never a collapse, whatever its wording.
_Avoid_: safe refusal, refusal (unqualified)

**Spoiler**:
A reply disclosing true information the character may not disclose at its story point,
either because it does not know it yet or because it is a secret.
_Avoid_: leak, lore error

A single reply can commit both a lore error and a spoiler; a true but premature disclosure
alone is only a spoiler, and a false version of a secret alone is only a lore error.
