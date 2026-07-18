param(
    [switch]$Package,
    [switch]$Pause,
    [switch]$PrintPython
)

$ErrorActionPreference = "Stop"
$backendDir = Split-Path -Parent $PSCommandPath
$projectRoot = Split-Path -Parent $backendDir

function Find-Python {
    $candidates = @(
        (Join-Path $projectRoot ".venv\Scripts\python.exe"),
        (Join-Path $backendDir "competition\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }
    throw "Python not found. Prepare backend\competition or the project .venv environment first."
}

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    Write-Host "`n[$Label]" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$python = $null
$locationChanged = $false
try {
    $python = Find-Python
    if ($PrintPython) {
        Write-Output $python
        exit 0
    }
    Write-Host "A3 backend quick test" -ForegroundColor Green
    Write-Host "Python: $python"
    Push-Location $projectRoot
    $locationChanged = $true

    Invoke-CheckedCommand "Python compile check" { & $python -m compileall -q backend }
    Invoke-CheckedCommand "Backend automated tests" { & $python -m pytest -q backend }

    if ($Package) {
        $buildScript = Join-Path $backendDir "build_api.ps1"
        $verifyScript = Join-Path $backendDir "verify_api_package.ps1"
        Invoke-CheckedCommand "PyInstaller package build" {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript -Python $python
        }
        Invoke-CheckedCommand "api.exe launch check" {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript
        }
    }

    Write-Host "`nAll quick tests passed." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nQuick test failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($locationChanged) {
        Pop-Location
    }
    if ($Pause) {
        Read-Host "Press Enter to close"
    }
}
