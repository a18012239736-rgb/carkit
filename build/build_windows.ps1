# Build the carkit Windows application.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$root = (Get-Location).Path
$venv = Join-Path $root ".venv"
$offlineVenv = Join-Path $PSScriptRoot "..\..\work\carkit-venv"
$python = $null
$pip = $null

function Test-BuildPython([string]$candidate) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $false }
    $envRoot = Split-Path (Split-Path $candidate -Parent) -Parent
    $site = Join-Path $envRoot "Lib\site-packages"
    foreach ($module in @("PyInstaller", "webview", "playwright", "openpyxl", "lxml", "pytest")) {
        if (-not (Test-Path -LiteralPath (Join-Path $site $module))) { return $false }
    }
    return $true
}

foreach ($candidateVenv in @($venv, $offlineVenv)) {
    $candidatePython = Join-Path $candidateVenv "Scripts\python.exe"
    if (Test-BuildPython $candidatePython) {
        $python = $candidatePython
        $pip = Join-Path $candidateVenv "Scripts\pip.exe"
        break
    }
}

Write-Host "[1/4] Create virtual environment" -ForegroundColor Cyan
if (-not $python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $venv
    } else {
        & python -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the virtual environment." }
    $python = Join-Path $venv "Scripts\python.exe"
    $pip = Join-Path $venv "Scripts\pip.exe"
}

Write-Host "[2/4] Install build dependencies" -ForegroundColor Cyan
$packages = @("pywebview", "playwright", "openpyxl", "lxml", "beautifulsoup4", "pyinstaller", "pytest")
if (-not (Test-BuildPython $python)) {
    & $python -m pip install --upgrade pip -q
    & $pip install @packages -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Default package index failed; retrying with the Tsinghua mirror." -ForegroundColor Yellow
        & $pip install @packages -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to install Python build dependencies." }
}

Write-Host "[3/4] Run offline regression tests" -ForegroundColor Cyan
& $python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { throw "Regression tests failed; packaging was stopped." }

Write-Host "[4/4] Build single-file executable with PyInstaller" -ForegroundColor Cyan
& $python -m PyInstaller build/carkit.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$exe = Join-Path (Get-Location) "dist\carkit.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Build finished but carkit.exe was not found: $exe"
}

$releaseDir = Join-Path $root "release"
$releaseExe = Join-Path $releaseDir "carkit.exe"
$sizeMb = [Math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
if ($sizeMb -lt 20) {
    throw "The packaged exe is only $sizeMb MB. Python or Playwright may not have been embedded; release copy is unsafe to publish."
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
Copy-Item -LiteralPath $exe -Destination $releaseExe -Force

Write-Host "Build complete: $exe" -ForegroundColor Green
Write-Host "Release copy updated: $releaseExe ($sizeMb MB)" -ForegroundColor Green
