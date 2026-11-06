# Build a single-file HotspotLite.exe (no console window).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pip pyinstaller | Out-Null
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name HotspotLite `
  hotspot_lite.py

Write-Host ""
Write-Host "Done: $PSScriptRoot\dist\HotspotLite.exe"
