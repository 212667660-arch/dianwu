param(
    [string]$Python = "python",
    [string]$OutputDir = "..\dist"
)

$ErrorActionPreference = "Stop"
$backendDir = Split-Path -Parent $PSCommandPath
$projectRoot = Split-Path -Parent $backendDir
$outputPath = Join-Path $backendDir $OutputDir

Push-Location $projectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --onedir --name api --distpath $outputPath --workpath (Join-Path $projectRoot "build\api") --specpath (Join-Path $projectRoot "build") --add-data "$backendDir\.env.example;backend" --add-data "$backendDir\test_console.html;backend" --collect-all fastapi --collect-all pydantic --collect-all pydantic_settings --collect-all sqlalchemy --collect-all uvicorn --paths $projectRoot backend\run.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码：$LASTEXITCODE" }
} finally {
    Pop-Location
}

$executable = Join-Path $outputPath "api\api.exe"
if (-not (Test-Path $executable)) { throw "未找到打包产物：$executable" }
Write-Host "打包完成：$executable"
