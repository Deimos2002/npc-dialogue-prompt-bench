# Load only known provider/observability settings; never execute .env contents.
function Import-PilotEnv {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $lineNumber = 0
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $lineNumber++
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            throw "Invalid .env assignment at line $lineNumber. Use KEY=value."
        }
        $variableName = $Matches[1]
        $variableValue = $Matches[2].Trim()
        if ($variableName -notin @(
            'OPENAI_API_KEY', 'GROQ_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY',
            'MISTRAL_API_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_BASE_URL'
        )) {
            continue
        }
        if ($variableValue.StartsWith('"') -or $variableValue.StartsWith("'")) {
            $quote = $variableValue.Substring(0, 1)
            if ($variableValue.Length -lt 2 -or -not $variableValue.EndsWith($quote)) {
                throw "Unclosed .env quote at line $lineNumber."
            }
            $variableValue = $variableValue.Substring(1, $variableValue.Length - 2)
        }
        if ($variableValue -and -not [Environment]::GetEnvironmentVariable($variableName, 'Process')) {
            [Environment]::SetEnvironmentVariable($variableName, $variableValue, 'Process')
        }
    }
}
