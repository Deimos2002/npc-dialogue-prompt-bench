# Run the Mount Hua development pilot

The ten scenarios in `data/pilots/mount-hua/scenarios/dev.yaml` cover build advice,
missing context and adversarial dialogue. Use [the rubric](review-rubric.md) to assess
the replies. The three strategies share system text and differ in their planning
instruction. Game rules are explicitly in that shared text: `--world` supplies scoring data and
does not automatically inject world facts into model context.

The Windows launcher validates the inputs, compares all three strategies, and
verifies replay. It generates a fresh run ID by default and uses fake responses
unless a live provider is explicitly selected:

```powershell
& ./scripts/run-mount-hua-pilot.ps1
# Once a local model is available, replace MODEL_ID:
& ./scripts/run-mount-hua-pilot.ps1 -Provider ollama -Model MODEL_ID -ResultsDir results
# Alternative: requires ANTHROPIC_API_KEY in the environment and incurs API usage:
& ./scripts/run-mount-hua-pilot.ps1 -Provider anthropic -Model MODEL_ID -ResultsDir results
```

Use `-RunId`, `-Temperature`, `-OllamaUrl`, or `-Reasoning` to override the
corresponding settings. The script stops on a failed command. Commands below
show the same workflow step by step.

For OpenAI, Groq and Gemini configuration, see
[model choices, credit estimates and masked key setup](providers.md). The launcher
also accepts `-RequestInterval` for quota pacing and `-PromptForKey` for API-key entry.

From the repository root in PowerShell, validate the pilot:

```powershell
.\.venv\Scripts\bench.exe validate --world data/pilots/mount-hua/world --characters data/pilots/mount-hua/characters --scenarios data/pilots/mount-hua/scenarios --profile none
```

Run the offline workflow smoke check with all three strategies:

```powershell
$pilotArgs = @(
  '--scenarios', 'data/pilots/mount-hua/scenarios/dev.yaml',
  '--character', 'data/pilots/mount-hua/characters/elder.yaml',
  '--world', 'data/pilots/mount-hua/world',
  '--arm', 'direct=data/pilots/mount-hua/prompts/direct/v2.md',
  '--arm', 'plan_generic=data/pilots/mount-hua/prompts/plan_generic/v2.md',
  '--arm', 'plan_in_character=data/pilots/mount-hua/prompts/plan_in_character/v2.md',
  '--temperature', '0.7'
)
.\.venv\Scripts\bench.exe run @pilotArgs --provider fake --model fake-1 --run-id mount-hua-smoke --results-dir .scratch/mount-hua
.\.venv\Scripts\bench.exe replay --run-id mount-hua-smoke --results-dir .scratch/mount-hua
```

Expect 42 visible replies and 70 calls before retries: fourteen turns, three reply
strategies, and one extra planning call for each of the two planning strategies.
The fake provider echoes text; its scores say nothing about model quality.
Use a new run ID if the existing run directory is present.

For a live run, reuse `$pilotArgs` and select a pinned model:

```powershell
# Replace MODEL_ID before running. Ollama must be running with this model available.
.\.venv\Scripts\bench.exe run @pilotArgs --provider ollama --model MODEL_ID --run-id mount-hua-local-dev-01 --results-dir results

# Alternative: set ANTHROPIC_API_KEY in the environment before calling Anthropic.
# Replace MODEL_ID with a supported pinned model; this run incurs API usage.
.\.venv\Scripts\bench.exe run @pilotArgs --provider anthropic --model MODEL_ID --run-id mount-hua-api-dev-01 --results-dir results
```

Select a provider and model for each run. Model, temperature, arm order, input hashes,
recordings and usage are saved in the run artifacts. The 0.7 temperature is a starting
pilot setting, not a tuned or validated choice. Token costs are not estimated here.
Review the content and choose the model/budget before making paid calls.

After a live run, inspect `results/<run-id>/report.md` and `recordings.jsonl`, replay it,
and export the supported checks for human adjudication:

```powershell
.\.venv\Scripts\bench.exe replay --run-id mount-hua-local-dev-01 --results-dir results
.\.venv\Scripts\bench.exe adjudicate export --run-id mount-hua-local-dev-01 --results-dir results --out .scratch/mount-hua-pending.csv
# Fill exported verdicts with pass, fail, or unknown, then import that same CSV:
.\.venv\Scripts\bench.exe adjudicate import --run-id mount-hua-local-dev-01 --results-dir results --file .scratch/mount-hua-pending.csv
```

Use a separate worksheet for the custom build/voice rubric. This pilot has one family,
so it cannot supply disjoint calibration and validation sets for `bench label sample`.
Author additional independent development families before judge validation.

Optional traditional sayings allowed by the prompts (translations may vary slightly):

- 過猶不及: “Going too far is as bad as falling short.” Source and Analects attribution:
  [Taiwan Ministry of Education idiom dictionary](https://dict.idioms.moe.edu.tw/idiomView.jsp?ID=-1439).
- 欲速則不達: “Haste prevents you from reaching your goal.” Source and Analects attribution:
  [Taiwan Ministry of Education revised dictionary](https://dict.revised.moe.edu.tw/dictView.jsp?ID=164149&la=1&powerMode=0).

Historical citations are reviewer background, not required dialogue content.

The recorded benchmark uses v4 prompts. Pass `-PromptVersion v4` to the
launcher to select them. Older prompt versions remain available for reproducibility.
