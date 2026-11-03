param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path -LiteralPath $iscc -PathType Leaf)) {
    throw 'Install Inno Setup 6 (6.3 or later) before building the installer.'
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'dist\carkit.exe') -PathType Leaf)) {
    throw 'Run build_windows.ps1 to build dist\carkit.exe first.'
}

& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot 'carkit.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$setup = Join-Path $root "dist\carkit-$Version-setup.exe"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "Inno Setup did not produce $setup."
}
Write-Host "Installer ready: $setup"
