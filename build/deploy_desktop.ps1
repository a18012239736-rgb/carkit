# Deploy the packaged carkit program to the current user's Desktop\Codex.
# Run from the repository root or from this script's directory:
#   powershell -ExecutionPolicy Bypass -File .\carkit\build\deploy_desktop.ps1
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$source = Join-Path $repo "dist\carkit"
$target = Join-Path ([Environment]::GetFolderPath("Desktop")) "Codex"

if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Packaged directory not found: $source. Build carkit first."
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
# Only overwrite program files; do not delete existing user data or results.
# Use -Path here because the source contains a wildcard; -LiteralPath would
# treat the asterisk literally and silently skip the executable.
Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
$folders = @(
    "raw",
    [string]::Concat([char]0x9636, [char]0x68AF),
    [string]::Concat([char]0x5FEB, [char]0x7167),
    [string]::Concat([char]0x8D4B, [char]0x503C),
    [string]::Concat([char]0x7ED3, [char]0x679C)
)
$folders | ForEach-Object {
    New-Item -ItemType Directory -Path (Join-Path $target $_) -Force | Out-Null
}

$exe = Join-Path $target "carkit.exe"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Deployment finished but carkit.exe was not found: $exe"
}
Write-Host "Deployment complete: $exe" -ForegroundColor Green
Write-Host "Work directory: $target" -ForegroundColor Cyan
