$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptPath = Join-Path $PSScriptRoot '..\prepare-desktop-backend.ps1'

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -cne $Expected) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-ThrowsCode {
    param([scriptblock]$Action, [string]$Code)
    try {
        & $Action
        throw "Expected $Code"
    }
    catch {
        if ($_.Exception.Data['A3Code'] -cne $Code) { throw }
        return $_.Exception
    }
}

function Write-DummyFile {
    param([string]$LiteralPath, [byte]$Seed)
    $parent = Split-Path -Parent $LiteralPath
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [IO.File]::WriteAllBytes($LiteralPath, [byte[]]@($Seed, ($Seed + 1), ($Seed + 2), 0, 255))
}

function Get-RelativeFileSnapshot {
    param([string]$RootPath)
    $root = ([IO.Path]::GetFullPath($RootPath)).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    return @(
        Get-ChildItem -LiteralPath $RootPath -File -Recurse -Force |
            Sort-Object -Property FullName |
            ForEach-Object {
                [pscustomobject][ordered]@{
                    RelativePath = $_.FullName.Substring($root.Length).Replace('\', '/')
                    Length = $_.Length
                    Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            }
    )
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("a3-prepare-backend-{0}" -f [guid]::NewGuid().ToString('N'))
$repositoryRoot = Join-Path $testRoot 'repository'
$sourceRoot = Join-Path $repositoryRoot 'dist\api'
$targetRoot = Join-Path $repositoryRoot 'front\a3-front\desktop-backend'
$outsideRoot = Join-Path $testRoot 'outside'

New-Item -ItemType Directory -Path $repositoryRoot -Force | Out-Null
New-Item -ItemType Directory -Path $outsideRoot -Force | Out-Null

try {
    Write-DummyFile -LiteralPath (Join-Path $sourceRoot 'api.exe') -Seed 11
    Write-DummyFile -LiteralPath (Join-Path $sourceRoot '_internal\marker.txt') -Seed 21
    Write-DummyFile -LiteralPath (Join-Path $sourceRoot '_internal\nested\settings.bin') -Seed 31
    Write-DummyFile -LiteralPath (Join-Path $targetRoot 'old-marker.txt') -Seed 41

    $outsideSource = Join-Path $outsideRoot 'api'
    Write-DummyFile -LiteralPath (Join-Path $outsideSource 'api.exe') -Seed 51
    Assert-ThrowsCode {
        & $scriptPath -RepositoryRoot $repositoryRoot -Source $outsideSource -Target 'front\a3-front\desktop-backend'
    } 'A3_PATH_OUTSIDE_REPOSITORY' | Out-Null
    Assert-ThrowsCode {
        & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\api' -Target $outsideRoot
    } 'A3_PATH_OUTSIDE_REPOSITORY' | Out-Null

    $missingSource = Join-Path $repositoryRoot 'dist\missing'
    New-Item -ItemType Directory -Path $missingSource -Force | Out-Null
    Assert-ThrowsCode {
        & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\missing' -Target 'front\a3-front\desktop-backend'
    } 'A3_BACKEND_EXECUTABLE_MISSING' | Out-Null

    $reparseSourceTarget = Join-Path $outsideRoot 'reparse-source-target'
    Write-DummyFile -LiteralPath (Join-Path $reparseSourceTarget 'api.exe') -Seed 56
    New-Item -ItemType Junction -Path (Join-Path $repositoryRoot 'dist\reparse-source') -Target $reparseSourceTarget | Out-Null
    Assert-ThrowsCode {
        & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\reparse-source' -Target 'front\a3-front\desktop-backend'
    } 'A3_SOURCE_REPARSE_POINT' | Out-Null

    Assert-ThrowsCode {
        & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\api' -Target 'front\a3-front\desktop-backend' -TestFailurePoint AfterBackup
    } 'A3_RELEASE_TEST_MODE_REQUIRED' | Out-Null

    & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\api' -Target 'front\a3-front\desktop-backend'
    $sourceSnapshot = Get-RelativeFileSnapshot -RootPath $sourceRoot
    $targetSnapshot = Get-RelativeFileSnapshot -RootPath $targetRoot
    Assert-Equal ($targetSnapshot | ConvertTo-Json -Compress) ($sourceSnapshot | ConvertTo-Json -Compress) 'The atomic replacement must preserve every backend file, length, and SHA-256 value.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'old-marker.txt') -PathType Leaf)) 'A successful replacement must remove files from the previous backend.'

    foreach ($failurePoint in @('AfterStage', 'AfterBackup')) {
        Remove-Item -LiteralPath $targetRoot -Recurse -Force
        Write-DummyFile -LiteralPath (Join-Path $targetRoot 'old-marker.txt') -Seed 61
        $previousTestMode = $env:A3_RELEASE_SCRIPT_TEST_MODE
        $env:A3_RELEASE_SCRIPT_TEST_MODE = '1'
        try {
            Assert-ThrowsCode {
                & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\api' -Target 'front\a3-front\desktop-backend' -TestFailurePoint $failurePoint
            } 'A3_RELEASE_TEST_FAILURE' | Out-Null
        }
        finally {
            if ($null -eq $previousTestMode) {
                Remove-Item Env:A3_RELEASE_SCRIPT_TEST_MODE -ErrorAction SilentlyContinue
            }
            else {
                $env:A3_RELEASE_SCRIPT_TEST_MODE = $previousTestMode
            }
        }
        Assert-True (Test-Path -LiteralPath (Join-Path $targetRoot 'old-marker.txt') -PathType Leaf) "A $failurePoint failure must restore the prior backend."
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'api.exe') -PathType Leaf)) "A $failurePoint failure must not publish the staged backend."
        $temporarySiblings = @(
            Get-ChildItem -LiteralPath (Split-Path -Parent $targetRoot) -Force |
                Where-Object { $_.Name -like '.desktop-backend.staging-*' -or $_.Name -like '.desktop-backend.backup-*' }
        )
        Assert-Equal $temporarySiblings.Count 0 "A $failurePoint failure must clean staging and backup directories."
    }

    $reparseTarget = Join-Path $testRoot 'reparse-target'
    Write-DummyFile -LiteralPath (Join-Path $reparseTarget 'sentinel.txt') -Seed 71
    New-Item -ItemType Junction -Path (Join-Path $targetRoot 'unsafe-link') -Target $reparseTarget | Out-Null
    $previousTestMode = $env:A3_RELEASE_SCRIPT_TEST_MODE
    $env:A3_RELEASE_SCRIPT_TEST_MODE = '1'
    try {
        Assert-ThrowsCode {
            & $scriptPath -RepositoryRoot $repositoryRoot -Source 'dist\api' -Target 'front\a3-front\desktop-backend' -TestFailurePoint AfterBackup
        } 'A3_BACKEND_TARGET_INVALID' | Out-Null
    }
    finally {
        if ($null -eq $previousTestMode) {
            Remove-Item Env:A3_RELEASE_SCRIPT_TEST_MODE -ErrorAction SilentlyContinue
        }
        else {
            $env:A3_RELEASE_SCRIPT_TEST_MODE = $previousTestMode
        }
    }
    Assert-True (Test-Path -LiteralPath (Join-Path $reparseTarget 'sentinel.txt') -PathType Leaf) 'An unsafe existing target must be rejected before any cleanup can traverse its junction.'
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output 'prepare-desktop-backend.test.ps1 passed'
