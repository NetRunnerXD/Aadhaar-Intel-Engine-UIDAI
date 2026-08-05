# Refresh processed parquet marts (schedule via Task Scheduler for research ETL).
# Example daily 02:00:
#   schtasks /Create /SC DAILY /ST 02:00 /TN "AadhaarMarts" /TR "powershell -File D:\path\scripts\refresh_marts.ps1"

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Building marts in $Root ..."
python -m src.etl.build_cache --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Manifest: data\processed\manifest.json"
