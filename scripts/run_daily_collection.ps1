# Daily collection entry point for Windows Task Scheduler (SPEC-010 §3).
#
# The machine's execution policy rejects unsigned scripts, so the task must pass -ExecutionPolicy
# Bypass explicitly — measured on 2026-11-13, where a plain `& script.ps1` failed with
# "not digitally signed".
#
# Register once, from an elevated PowerShell prompt:
#   $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
#       -Argument '-NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_daily_collection.ps1"' `
#       -WorkingDirectory '<repo>'
#   $trigger = New-ScheduledTaskTrigger -Daily -At 02:30
#   Register-ScheduledTask -TaskName 'GTAF daily collection' -Action $action -Trigger $trigger `
#       -Description 'Collect the next paced batch of Georgian TV captions'
#
# Why exit 0 on 5 and 4: a run blocked by YouTube's rate limit, or by a reader holding the database, is
# an expected outcome of the pacing policy (D-018, D-014). Returning non-zero would make the scheduler
# treat it as failure and retry into the same limit.

param(
    [string]$Database = 'data/gtaf.duckdb',
    [string]$LogDir = 'logs',
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

Write-Host "[$(Get-Date -Format 's')] asking gtaf what to collect next"
$decisionJson = & $python -m gtaf next --db $Database --json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "gtaf next failed (exit $LASTEXITCODE): $decisionJson"
    exit $LASTEXITCODE
}

$decision = $decisionJson | ConvertFrom-Json
Write-Host "decision: $($decision.reason)"

if (-not $decision.collect) {
    Write-Host 'nothing to do; exiting cleanly'
    exit 0
}

$arguments = @(
    '-m', 'gtaf', 'collect',
    '--channel', $decision.channel_id,
    '--limit', "$($decision.limit)",
    '--skip-existing',
    '--log-dir', $LogDir
)
Write-Host "would run: $python $($arguments -join ' ')"
if ($DryRun) {
    Write-Host 'dry run; not collecting'
    exit 0
}

& $python @arguments
$code = $LASTEXITCODE
switch ($code) {
    0 { Write-Host 'collection completed' ; exit 0 }
    5 { Write-Host 'rate limited by YouTube; ending this run without retrying (D-018)' ; exit 0 }
    4 { Write-Host 'database locked by another process; ending this run (D-014)' ; exit 0 }
    default { Write-Host "collection failed with exit $code" ; exit $code }
}
