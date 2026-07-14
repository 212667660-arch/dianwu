param(
    [string]$Executable = "..\dist\api\api.exe"
)

$ErrorActionPreference = "Stop"
$backendDir = Split-Path -Parent $PSCommandPath
$executablePath = Join-Path $backendDir $Executable
if (-not (Test-Path $executablePath)) { throw "Executable not found: $executablePath" }

$port = Get-Random -Minimum 18000 -Maximum 28000
$env:A3_PORT = "$port"
$process = Start-Process -FilePath $executablePath -PassThru -WindowStyle Hidden
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
                Write-Host "Package launch check passed: $executablePath"
                exit 0
            }
        } catch {
        }
    } while ((Get-Date) -lt $deadline -and -not $process.HasExited)
    throw "api.exe did not pass the health check within 20 seconds."
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    Remove-Item Env:A3_PORT -ErrorAction SilentlyContinue
}
