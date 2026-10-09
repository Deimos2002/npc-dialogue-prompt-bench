<#
.SYNOPSIS
Validate, run, and replay the Mount Hua development pilot.
.EXAMPLE
& ./scripts/run-mount-hua-pilot.ps1
.EXAMPLE
& ./scripts/run-mount-hua-pilot.ps1 -Provider ollama -Model 'YOUR_MODEL_ID' -ResultsDir results
#>
[CmdletBinding()]
param(
    [ValidateSet('fake', 'ollama', 'anthropic', 'openai', 'groq', 'gemini')]
    [string]$Provider = 'fake',
    [string]$Model,
    [string]$RunId = ('mount-hua-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')),
    [string]$ResultsDir = '.scratch/mount-hua',
    [ValidateSet('v1', 'v2', 'v3', 'v4')]
    [string]$PromptVersion = 'v2',
    [ValidateRange(0.0, 1.0)]
    [double]$Temperature = 0.7,
    [ValidateRange(0.0, 3600.0)]
    [double]$RequestInterval = 0,
    [switch]$PromptForKey,
    [string]$OllamaUrl = 'http://127.0.0.1:11434',
    [ValidateSet('disabled', 'lowest')]
    [string]$Reasoning = 'disabled'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'load-pilot-env.ps1')
Import-PilotEnv -Path (Join-Path $projectRoot '.env')
$benchPath = Join-Path $projectRoot '.venv/Scripts/bench.exe'
if (-not (Test-Path -LiteralPath $benchPath -PathType Leaf)) {
    throw 'Install the project in .venv first; see the README setup instructions.'
}
if ([string]::IsNullOrWhiteSpace($Model)) {
    if ($Provider -eq 'fake') {
        $Model = 'fake-1'
    } else {
        throw 'A live provider requires -Model with the chosen model ID.'
    }
}
$keyVariable = @{
    anthropic = 'ANTHROPIC_API_KEY'
    openai = 'OPENAI_API_KEY'
    groq = 'GROQ_API_KEY'
    gemini = 'GEMINI_API_KEY'
}[$Provider]
if ($keyVariable -and -not [Environment]::GetEnvironmentVariable($keyVariable, 'Process')) {
    if (-not $PromptForKey) {
        throw "Set $keyVariable in your environment, or use -PromptForKey for masked entry."
    }
    $secureKey = Read-Host "Enter $keyVariable (hidden; held in this PowerShell session only)" -AsSecureString
    $keyBuffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        [Environment]::SetEnvironmentVariable(
            $keyVariable,
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyBuffer),
            'Process'
        )
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyBuffer)
        $secureKey.Dispose()
    }
}

function Invoke-PilotBench {
    param([string[]]$BenchArguments)
    & $benchPath @BenchArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark command failed with exit code $LASTEXITCODE."
    }
}

Push-Location -LiteralPath $projectRoot
try {
    $pilotRoot = 'data/pilots/mount-hua'
    Invoke-PilotBench -BenchArguments @(
        'validate', '--world', "$pilotRoot/world",
        '--characters', "$pilotRoot/characters",
        '--scenarios', "$pilotRoot/scenarios", '--profile', 'none'
    )
    if ($Provider -eq 'fake') {
        Write-Host 'Offline smoke check: fake echoes do not measure dialogue quality.'
    } else {
        Write-Host "Live pilot: $Provider / $Model; 42 replies and 70 calls before retries."
    }
    Invoke-PilotBench -BenchArguments @(
        'run', '--scenarios', "$pilotRoot/scenarios/dev.yaml",
        '--character', "$pilotRoot/characters/elder.yaml",
        '--world', "$pilotRoot/world",
        '--arm', "direct=$pilotRoot/prompts/direct/$PromptVersion.md",
        '--arm', "plan_generic=$pilotRoot/prompts/plan_generic/$PromptVersion.md",
        '--arm', "plan_in_character=$pilotRoot/prompts/plan_in_character/$PromptVersion.md",
        '--provider', $Provider, '--model', $Model, '--run-id', $RunId,
        '--results-dir', $ResultsDir,
        '--temperature', $Temperature.ToString([Globalization.CultureInfo]::InvariantCulture),
        '--request-interval', $RequestInterval.ToString([Globalization.CultureInfo]::InvariantCulture),
        '--ollama-url', $OllamaUrl, '--reasoning', $Reasoning
    )
    Invoke-PilotBench -BenchArguments @(
        'replay', '--run-id', $RunId, '--results-dir', $ResultsDir
    )
    $reportPath = Join-Path (Join-Path $ResultsDir $RunId) 'report.md'
    Write-Host "Report: $([IO.Path]::GetFullPath($reportPath))"
} finally {
    Pop-Location
}
