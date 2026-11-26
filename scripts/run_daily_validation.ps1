# Daily validation entry point (SPEC-016). Register it only if you want automatic accumulation:
#
#   $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
#       -Argument '-NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_daily_validation.ps1"' `
#       -WorkingDirectory '<repo>'
#   $trigger = New-ScheduledTaskTrigger -Daily -At 04:00
#   Register-ScheduledTask -TaskName 'GTAF daily validation' -Action $action -Trigger $trigger
#
# Why a separate small task: the Gemini free tier allows roughly eleven calls a day, so a 50-item check is
# assembled over several days. Each run adds at most --limit new items and skips what is already validated.
#
# Exit codes: 0 on success, 0 on quota (a blocked day is not a failure — it simply adds nothing), 0 when the
# database is locked by the 02:30 collection run (D-014), and the vendor's code otherwise.

param(
    [string]$Database = 'data/gtaf.duckdb',
    [string]$Target = 'saakashvili',
    [int]$Limit = 10,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error "Python environment not found at $python"
    exit 1
}

$env:PYTHONPATH = Join-Path $repo 'src'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $repo

$arguments = @('-m', 'gtaf', 'validate', '--db', $Database, '--target', $Target, '--limit', "$Limit")
Write-Host "would run: $python $($arguments -join ' ')"
if ($DryRun) {
    Write-Host 'dry run; not validating'
    exit 0
}

& $python @arguments
switch ($LASTEXITCODE) {
    0 { Write-Host 'validation batch finished' ; exit 0 }
    5 { Write-Host 'validator vendor quota exhausted; nothing added today (D-026)' ; exit 0 }
    4 { Write-Host 'database locked by the collection run; skipping today (D-014)' ; exit 0 }
    default { Write-Host "validation failed with exit $LASTEXITCODE" ; exit $LASTEXITCODE }
}
