# Unaudited, unflagged semantic results are assumed passes

Adjudication covers flagged replies and a seeded 10% audit of unflagged ones, so most
unflagged replies are never read by a human. We give those replies the verdict **pass**
with provenance **assumed**, kept distinct from a human-confirmed pass. A flagged result
awaiting review stays **unknown** with no provenance and review status **pending**; the
flag itself is kept. The resulting rate is named the **detected semantic
error rate**, a lower bound rather than the underlying error rate. Every such rate is
reported with its audit coverage, the error rate among audited unflagged replies, that
rate's interval and its sample size.

This applies only inside the predeclared **semantic review cohort**, the replies the run
declares for adjudication before it executes; in v0.1 that is replicate 1. Outside the
cohort (v0.1 replicates 2–3) every semantic verdict stays unknown and pending, and no
detected semantic error rate is reported, because assuming passes where no audit could have
found misses would make unreviewed replicates look cleaner than reviewed ones. Indicative
judge metrics are not bound by the cohort: they follow their own declared coverage and stay
labelled indicative.

## Interpretation

Provenance is part of every verdict, so a report can always separate assumed passes from
confirmed ones; renaming the rate to "error rate" without the qualifier would overstate it.
