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
    & $Python -m PyInstaller --noconfirm --clean --onedir --name api --distpath $outputPath --workpath (Join-Path $projectRoot "build\api") --specpath (Join-Path $projectRoot "build") --add-data "$backendDir\.env.example;backend" --add-data "$backendDir\test_console.html;backend" --collect-all fastapi --collect-all pydantic --collect-all pydantic_settings --collect-all sqlalchemy --collect-all uvicorn --collect-all backend.knowledge --collect-all fitz --collect-all docx --collect-all pptx --collect-all openpyxl --collect-all defusedxml --collect-all charset_normalizer --collect-all numpy --collect-all rapidocr_onnxruntime --collect-all onnxruntime --collect-all cv2 --paths $projectRoot backend\run.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码：$LASTEXITCODE" }
} finally {
    Pop-Location
}

$runtimeTarget = Join-Path $outputPath "api\_internal"
$system32 = Join-Path $env:SystemRoot "System32"
$runtimeDlls = @(
    "concrt140.dll",
    "msvcp140.dll",
    "MSVCP140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "vcruntime140_threads.dll"
)
foreach ($runtimeDll in $runtimeDlls) {
    $sourceDll = Join-Path $system32 $runtimeDll
    if (Test-Path -LiteralPath $sourceDll) {
        Copy-Item -Force -LiteralPath $sourceDll -Destination (Join-Path $runtimeTarget $runtimeDll)
    }
}

$executable = Join-Path $outputPath "api\api.exe"
if (-not (Test-Path $executable)) { throw "未找到打包产物：$executable" }
Write-Host "打包完成：$executable"
