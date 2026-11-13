# Build plugin TKGPM cho AutoCAD 2020 -> 2026.
# Chạy:  powershell -ExecutionPolicy Bypass -File build.ps1
# Hoặc chỉ một năm: powershell -ExecutionPolicy Bypass -File build.ps1 -Years 2026

param(
    [int[]]$Years = @(2020, 2021, 2022, 2023, 2024, 2025, 2026)
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$proj = Join-Path $root 'CadTkgpm.csproj'
$date = Get-Date -Format 'yyyyMMdd'
$results = @()

foreach ($y in $Years) {
    $acadRoot = Join-Path $env:ProgramFiles "Autodesk\AutoCAD $y"
    if (-not (Test-Path (Join-Path $acadRoot 'acdbmgd.dll'))) {
        Write-Warning "Bỏ qua AutoCAD $y: không tìm thấy $acadRoot"
        $results += [pscustomobject]@{ Year = $y; Status = 'SKIP (chưa cài AutoCAD)'; Output = '' }
        continue
    }

    Write-Host "=== Build AutoCAD $y ===" -ForegroundColor Cyan
    dotnet build $proj -c Release "-p:AcadYear=$y" "-p:BuildDate=$date" --nologo
    if ($LASTEXITCODE -ne 0) {
        $results += [pscustomobject]@{ Year = $y; Status = 'FAILED'; Output = '' }
        continue
    }

    $dll = Get-ChildItem (Join-Path $root "dist\AutoCAD$y") -Filter "CadTkgpm_AC${y}_$date.dll" | Select-Object -First 1
    $results += [pscustomobject]@{ Year = $y; Status = 'OK'; Output = $dll.FullName }
}

Write-Host ""
Write-Host "Kết quả build:" -ForegroundColor Green
$results | Format-Table -AutoSize
