$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cache = Join-Path $project '.local'
# Retired launchers and completed test/download artifacts only; no active runtime.
$names = @('before-sharing','art-candidates','newclid2','npm-cache',
 'pytest-ai','pytest-all','pytest-cache','pytest-complete-eight','pytest-current','pytest-custom',
 'pytest-eight-keys','pytest-final','pytest-final-release','pytest-motion','pytest-motion-final',
 'pytest-release','pytest-review','pytest-review-2','pytest-simple-prompt','pytest-student-complete',
 'pytest-vision-api','pytest-vision-ready','check-ctrl-c.log','check-force-owner.log',
 'check-force-wrapper.log','check-stop.log','preview-api.log','preview-frontend.log',
 'preview-gateway.log','preview-launch-error.log','preview-launch.log','preview-launcher.err.log',
 'preview-launcher.out.log','preview.err.log','preview.out.log','preview.pid',
 'share-final.err.log','share-final.out.log','share-test.err.log','share-test.out.log','hbg-problem.json')
Add-Type -AssemblyName Microsoft.VisualBasic
$report = @()
foreach ($name in $names) {
 $target = [IO.Path]::GetFullPath((Join-Path $cache $name))
 if (-not $target.StartsWith($cache + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid cleanup target' }
 if (-not (Test-Path -LiteralPath $target)) { continue }
 $item = Get-Item -LiteralPath $target -Force
 if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected link' }
 $bytes = if ($item.PSIsContainer) { (Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object Length -Sum).Sum } else { $item.Length }
 if ($item.PSIsContainer) {
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($target,'OnlyErrorDialogs','SendToRecycleBin')
 } else {
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($target,'OnlyErrorDialogs','SendToRecycleBin')
 }
 $report += [PSCustomObject]@{path='.local/'+$name;bytes=[long]$bytes;destination='Windows Recycle Bin'}
}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $project 'docs/cleanup-2026-11-09.json') -Encoding utf8
$report | Measure-Object bytes -Sum | Select-Object Count,Sum
