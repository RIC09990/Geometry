param([switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
# Compatibility for old shortcuts: use the same managed lifetime as the main CMD.
# Never launch a second detached preview that occupies the sharing ports.
$pythonBinary = Join-Path $projectRoot '.venv\Scripts\python.exe'
$localArguments = @('-u', (Join-Path $PSScriptRoot 'local.py'))
if (-not $OpenBrowser) { $localArguments += '--no-browser' }
& $pythonBinary @shareArguments
exit $LASTEXITCODE
