param([switch]$Lan)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPython = Join-Path $PSScriptRoot '../../work/venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $taskPython)) {
    $sysPy = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPy) { $taskPython = $sysPy.Source }
}
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create .venv or install Python 3.12+ and add to PATH; see README.md.'
}
& $taskPython -m backend.demo_setup
if ($LASTEXITCODE -ne 0) { throw 'Demo setup failed.' }
$taskBind = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
& $taskPython -m uvicorn backend.app:create_app --factory --host $taskBind --port 8000
