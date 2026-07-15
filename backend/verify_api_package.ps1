param(
    [string]$Executable = "..\dist\api\api.exe",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$backendDir = Split-Path -Parent $PSCommandPath
$projectRoot = Split-Path -Parent $backendDir
$executablePath = Join-Path $backendDir $Executable
if (-not (Test-Path $executablePath)) { throw "Executable not found: $executablePath" }
$executablePath = (Resolve-Path -LiteralPath $executablePath).Path

$env:A3_PACKAGED_API_EXE = $executablePath
try {
    Push-Location $projectRoot
    try {
        & $Python -m pytest -q backend\tests\knowledge\test_packaged_worker.py -k "packaged_worker_parses_each_supported_format"
        if ($LASTEXITCODE -ne 0) { throw "Packaged knowledge worker verification failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }

    $port = Get-Random -Minimum 18000 -Maximum 28000
    $env:A3_PORT = "$port"
    $process = Start-Process -FilePath $executablePath -PassThru -WindowStyle Hidden
    $passed = $false
    try {
        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 300
            try {
                $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health/live" -TimeoutSec 2
                if ($response.status -eq "live") {
                    $ui = Invoke-WebRequest -Uri "http://127.0.0.1:$port/test" -TimeoutSec 2 -UseBasicParsing
                    if ($ui.StatusCode -ne 200 -or $ui.Content -notmatch "A3 backend test console") {
                        throw "The packaged test console did not load."
                    }
                    $passed = $true
                    break
                }
            } catch {
            }
        } while ((Get-Date) -lt $deadline -and -not $process.HasExited)
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        Remove-Item Env:A3_PORT -ErrorAction SilentlyContinue
    }
    if (-not $passed) { throw "api.exe did not pass the health check within 20 seconds." }
    Write-Host "Package launch check passed: $executablePath"
} finally {
    Remove-Item Env:A3_PACKAGED_API_EXE -ErrorAction SilentlyContinue
}
