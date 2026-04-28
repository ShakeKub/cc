param(
    [string]$Python = "python",
    [string]$Name = "ByteSweep"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

& $Python -m pip install -r requirements.txt
& $Python -m pip install -r requirements-dev.txt

$addData = @(
    "config.json;.",
    "locales;locales",
    "themes;themes",
    "profiles;profiles",
    "plugins;plugins",
    "core/wordlist.txt;core"
)

$addDataArgs = $addData | ForEach-Object { "--add-data", $_ }

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $Name `
    $addDataArgs `
    "main.py"

Write-Host "Build complete: dist\\$Name.exe"
