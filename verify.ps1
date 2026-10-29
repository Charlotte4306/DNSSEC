param([switch]$Faults)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create .venv and install dashboard/requirements.txt first.'
}
$taskArguments = @()
if ($Faults) { $taskArguments += '--faults' }
& $taskPython (Join-Path $PSScriptRoot 'tools/acceptance.py') @taskArguments
if ($LASTEXITCODE -eq 2) { Write-Host 'Partial report: use -Faults to include live fault cases.' }
elseif ($LASTEXITCODE -ne 0) { throw 'Acceptance failed; inspect the generated report.' }
