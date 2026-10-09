# Calls are made of attempts; reply latency is end to end

A reply needs one call (direct) or two (plan, then reply). Each call is a logical request
made of one or more recorded **attempts**: at most one retry, and only after a timeout or
transport failure; parse failures and truncation are never retried. Reply latency counts
everything the player waited through: every attempt of both stages, including failed ones,
and any backoff. Known token usage and cost are recorded per attempt; usage a timed-out
attempt never reported is **unknown**, not zero. A reply whose retry recovered is not an
execution failure; a reply is one if either required call fails on its final attempt.
Reports state retry counts and the share of replies that needed a retry.

## Interpretation

Latency figures look worse than a provider's own per-request numbers; that gap is
intended. Missing usage keeps cost totals partial rather than silently low.
