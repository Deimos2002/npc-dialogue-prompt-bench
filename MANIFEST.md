# Benchmark methodology

This document describes the implemented benchmark and how to interpret its results.
See [the glossary](GLOSSARY.md) for terminology and [the run interface](docs/code-structure.md)
for operation guarantees.

## Scenarios and comparison

Scenarios specify a character, story point, class, family and one or more player turns.
Families group related scenarios; they are the resampling unit for uncertainty estimates.
The runner counterbalances arm order across scenarios. Direct replies use one call;
generic and in-character planning use a private plan followed by a visible reply.
Both planning strategies share a 150-token planning cap. Native model reasoning settings
are recorded separately and must be disclosed when comparing models.

The included Mount Hua experiment has ten development scenarios in one family and one
replicate per model. It demonstrates the workflow and describes observed failures; it
cannot establish a general winning prompt strategy.

## Recorded calls and replay

Each attempt records the request, response, failure, timing, reported usage and available
model version. Transport failures and timeouts may retry once. Parse failures and
truncation are measured without resampling them. Reply latency includes both stages,
failed attempts and retry backoff; optional quota pacing is excluded.
The first-token measurement starts at the first visible non-whitespace output.
Unreported token usage stays unknown rather than becoming zero.

Run configuration records input hashes and a recordings hash. Replay verifies the inputs,
reconstructs checks and metrics from recordings, and compares them with the saved artifacts.
It does not call a provider. Creation rejects existing runs and publishes a staged directory.
Inputs must stay unchanged during generation. Interrupted live runs are not resumable.

## Checks and adjudication

Mechanical checks and semantic flags have different meanings. A semantic flag identifies
an item for review; an unflagged reply is not proof of correct behavior. The declared
semantic review cohort uses replicate index zero. Within that cohort, flagged replies and
a deterministic audit sample are eligible for adjudication. Unaudited, unflagged replies
can receive an assumed pass, distinct from a human-confirmed pass. Replies outside the
cohort remain unknown for semantic review.

Detected semantic error rates are lower bounds. Reports distinguish unresolved judgments,
assumed passes, human decisions and audit coverage. Human adjudication takes precedence
and is imported only after validating the whole CSV. Custom allocation/voice worksheets
are separate from the built-in adjudication format.

## Metrics and interpretation

Reports include per-arm rates, latency, token usage, paired differences and family-cluster
bootstrap intervals where supported. Failure counts need denominators. Comparisons from
one family or one replicate are descriptive; narrow intervals do not create independent
evidence. Quality findings from AI-assisted review are not independent human validation.
The recorded benchmark's review method and limitations are documented beside its results.

## Blind labelling

The local review interface exposes replies, conversation context, relevant character
information and trait questions. It hides strategy, model, latency and check results.
Calibration and validation samples use disjoint families. The server serializes duplicate
checks and label appends within one process; run a single server per labels file.
Labels capture judgments. Automated judge execution and agreement analysis are not implemented.

## Reproducibility and operational limits

Tests use fake providers or mock HTTP transports and disable external network access.
CI requires no model credentials. The browser demo uses authored dialogue and validates
point allocation locally; it is not a live model integration.
Adjudication files are replaced individually rather than in one multi-file transaction.
The saved evidence, input prompts and evaluation disclosures are retained unchanged.
