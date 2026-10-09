# OpenAI, Groq, and Gemini pilot setup

Provider details below were checked on 2026-10-09. Verify model access and quota
in the relevant provider dashboard before starting a live run.

| Provider | Suggested first model | Environment variable | Native thinking |
| --- | --- | --- | --- |
| OpenAI | `gpt-4.1-mini-2025-04-14` | `OPENAI_API_KEY` | Non-reasoning model |
| Groq | `qwen/qwen3.8-27b`, if available on the account's free plan | `GROQ_API_KEY` | Explicit `reasoning_effort: none`, hidden reasoning format |
| Gemini | `gemini-3.5-flash-lite`, if available on the project's free tier | `GEMINI_API_KEY` | `--reasoning lowest` sends `reasoning_effort: minimal`; thinking remains enabled |

OpenAI and Groq support the thinking-off comparison. Gemini 3.5 runs with its lowest
documented native reasoning level, so comparisons must disclose this difference.
They are starting
models, not measured winners or claims about the latest or strongest model. The OpenAI
snapshot is fixed. Groq/Gemini names may identify provider-managed versions; recordings
save the model string returned by each call, not a guaranteed immutable weight digest.
The adapter also supports OpenAI GPT-4.1/GPT-4o families, Groq's
`llama-3.3-70b-versatile` and `llama-3.1-8b-instant` when the account can access them,
and Gemini `gemini-2.5-flash`. Other models fail before a call until their parameters
and thinking behaviour are deliberately supported.

Listing a model through `/models` does not establish that generation is available
to the account. The older 2.5 settings remain supported for eligible existing users.
The replacement has a published free tier and supports minimal native thinking.
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini thinking levels](https://ai.google.dev/gemini-api/docs/thinking).

Sources: [OpenAI model snapshot and prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[Groq model-specific reasoning](https://console.groq.com/docs/reasoning),
[Gemini thinking compatibility](https://ai.google.dev/gemini-api/docs/openai).

## Credit and quota planning

OpenAI's published GPT-4.1 mini standard rates are $0.40 per million input tokens
and $1.60 per million output tokens. A full successful pilot makes 70 calls: 42 reply
calls capped at 512 tokens and 28 planning calls capped at 150 tokens.
As an **illustration**, assuming an average 3,000 input tokens on each call and every
output reaching its cap gives:

```text
Input:  70 × 3,000 × $0.40 / 1,000,000              = $0.084
Output: (42 × 512 + 28 × 150) × $1.60 / 1,000,000   = $0.041
Total under these assumptions                     ≈ $0.13
```

This is not a tokenizer-based estimate or a hard spending limit. Actual prompt/history
lengths, retries and usage determine charges. Failed attempts can also incur usage.
The adapter's token cap limits output, not input cost or total account spending. API credit is distinct from a ChatGPT subscription. [Official OpenAI prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

Groq limits can constrain requests and tokens per minute/day; the exact account limits
are in its dashboard. Gemini lists Flash-Lite input/output as free on the Free Tier,
but project tier and model-specific quotas determine eligibility. Using a paid Gemini
project is not a guarantee of free inference. Check that at least 70 daily requests
remain before a full run; if not, use a deliberately smaller scenario file or defer it.
Waiting between calls cannot solve a daily quota shortage.
[Groq limits](https://console.groq.com/docs/rate-limits),
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini active quotas](https://ai.google.dev/gemini-api/docs/rate-limits).

Gemini's pricing page lists use of free-tier data to improve products; consult the
linked terms for regional details. This pilot uses fictional dialogue. Its free tier
is not a reason to send private real-player conversations.

## Set a key and run from PowerShell

You can fill in the root `.env` file instead of using masked prompts:

```dotenv
OPENAI_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
```

The pilot launcher automatically loads supported API keys from this file. It never
executes its contents; existing process environment values take precedence. Bare
values or matching single/double quotes are supported. Put comments on their own
lines; shell expansion and multiline values are not supported. `.env` and its local
variants are ignored by Git; `.env.example` contains empty, shareable assignments.
Direct `bench` CLI calls still read process environment variables, not `.env`.

The template and loader also recognise `MISTRAL_API_KEY`, `LANGFUSE_SECRET_KEY`,
`LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_BASE_URL`. Mistral generation and Langfuse tracing
are not integrated yet; adding these settings alone does not send requests or traces.
Langfuse uses a project public/secret key pair and an instance base URL.
[Langfuse configuration](https://langfuse.com/docs/observability/sdk/troubleshooting-and-faq),
[Mistral key setup](https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request).

Create API keys through the provider's own console. Run these commands in your
PowerShell terminal; `-PromptForKey` asks for masked entry if the environment variable
is missing. It holds the key in that PowerShell process and its child processes,
without writing a credential file or placing the literal key in command history.
The launcher starts generation immediately after validation; configure the chosen
account's free tier/credit first. Each command starts a separate comparison run.

```powershell
# Paid API credit: one OpenAI pilot.
& ./scripts/run-mount-hua-pilot.ps1 -Provider openai -Model gpt-4.1-mini-2025-04-14 -PromptForKey -ResultsDir results

# Run only if this model is enabled in your Groq account and free quota remains.
& ./scripts/run-mount-hua-pilot.ps1 -Provider groq -Model qwen/qwen3.8-27b -PromptForKey -RequestInterval 30 -ResultsDir results

# Run only with an eligible Gemini free-tier project and enough daily quota.
& ./scripts/run-mount-hua-pilot.ps1 -Provider gemini -Model gemini-3.5-flash-lite -Reasoning lowest -PromptForKey -RequestInterval 20 -ResultsDir results
```

Intervals are adjustable starting points, not a guarantee of fitting account limits.
Quota pacing happens between attempts, outside measured provider call latency; it adds
wall-clock run time. The interval is recorded in `run_config.json`. Both plan strategies
still have two timed provider calls per reply, with normal retry backoff included in
recorded latency. A 429 is recorded as a transport failure and retried once by the runner;
there is no adaptive `Retry-After` scheduler or daily quota resume feature yet.

Review each run separately first. The current reports compare prompt arms within a run;
they do not automatically create a combined ranking across these three providers.
Human review of build suitability and voice remains necessary.
