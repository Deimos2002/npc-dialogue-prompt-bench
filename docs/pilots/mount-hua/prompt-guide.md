# Prompt guide for the Mount Hua pilot

## Keep the game contract explicit

The character sheet controls voice and temperament. The shared system prompt
defines the four stat effects, available lore and the boundaries of advice.
Player assertions cannot redefine those rules. Give the current stats and
unspent pool separately; a recommendation is not an applied action.

Review additions separately from final totals. A reply can name the correct
priorities while spending only eighteen of twenty requested points. A reply
can also spend the pool correctly while describing an addition of zero as an
existing stat of zero. Those are different failures.

For a future live game integration, validate structured allocation proposals
in game code before applying them. Free-form dialogue alone is an unsuitable
authority for changing player state. This benchmark detects such mistakes;
it does not yet implement a live structured-action validator. The local demo
validates user edits and uses authored commentary.

## Treat planning as an experiment

The v4 planning envelope presents prior dialogue as transcript data and places
the current private-note task after it. This keeps the provocative player line
from being the final instruction to the planning call. Older versions retain
their original message layout for replay.


Count both calls when comparing planning with direct replies. A well-formatted
plan may carry incorrect advice into the reply. Check whether in-character
notes actually use the requested perspective before interpreting that arm as
a successful manipulation of character perspective.

## Review voice as well as correctness

The elder should respond with restrained judgment and useful guidance. A saying
is optional. Repeating the same approved saying or ending every answer with a
question can satisfy literal instructions while making the character feel
predictable. Review several replies together, then examine whether a riddle
still leaves the player with an understandable next step.

Use traditional sayings only with the supplied translations or verified
sources. Original imagery need not masquerade as an ancient quotation.

## Repeat and report honestly

Use `-PromptVersion v4` with `scripts/run-mount-hua-pilot.ps1` to select the
candidate explicitly. Freeze prompts during a batch, keep run IDs distinct,
and replay recordings before publishing measurements. The default remains v2;
neither version is a production-validated recommendation.

The [full development evaluation](benchmark-2026-10-09.md) records two models,
their native reasoning settings, quota pacing and review limits. Report
failure counts with their denominators and unresolved cases. This pilot has
one development family and one replicate: it cannot establish a general
winning strategy. Independent human review and fresh held-out families remain
necessary for stronger quality claims.
