$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$opamRoot = Join-Path $projectRoot '.local/opam'
$opamBin = Join-Path $projectRoot '.tools/opam/opam.exe'
if (-not (Test-Path -LiteralPath $opamBin)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $opamBin) | Out-Null
    $release = Invoke-RestMethod 'https://api.github.com/repos/ocaml/opam/releases/tags/2.6.1'
    $asset = $release.assets | Where-Object name -eq 'opam-2.6.1-x86_64-windows.exe'
    Invoke-WebRequest -Uri $asset.url -Headers @{Accept='application/octet-stream'} -OutFile $opamBin
    $hash = (Get-FileHash -LiteralPath $opamBin -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne '2548f0592abfa728432c85ef6d08bf97c295c1859ddca61876e33884336c130c') { throw 'opam checksum mismatch' }
}
if (-not (Test-Path -LiteralPath (Join-Path $opamRoot 'config'))) {
    & $opamBin init --root $opamRoot --bare --no-setup --cygwin-internal-install --yes
    if ($LASTEXITCODE) { throw 'opam initialization failed' }
}
if (-not (Test-Path -LiteralPath (Join-Path $opamRoot 'geometry/bin/ocamlc.exe'))) {
    & $opamBin switch create geometry 5.4.1 --root $opamRoot --yes --jobs=1
    if ($LASTEXITCODE) { throw 'OCaml installation failed' }
}
& $opamBin install --root $opamRoot --switch geometry --yes --jobs=1 dune.3.24.2 sedlex.3.7 yojson.3.0.0 menhir.20260209
if ($LASTEXITCODE) { throw 'NiceGeo dependency installation failed' }
$env:PATH = (Join-Path $opamRoot '.cygwin/root/bin') + ';' + $env:PATH
Push-Location (Join-Path $projectRoot 'vendor/nicegeo')
try {
    & $opamBin exec --root $opamRoot --switch geometry -- dune build --profile release -j 2 bin/main.exe bin/proofstate.exe
    if ($LASTEXITCODE) { throw 'NiceGeo build failed' }
    & $opamBin exec --root $opamRoot --switch geometry -- ./_build/default/bin/main.exe euclib/euclib.ncg
    if ($LASTEXITCODE) { throw 'NiceGeo upstream proof check failed' }
} finally { Pop-Location }
Write-Output 'NiceGeo is built and the upstream proof library was checked.'
