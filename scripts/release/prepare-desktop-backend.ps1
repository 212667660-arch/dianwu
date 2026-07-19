param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent),
    [string]$Source = 'dist\api',
    [string]$Target = 'front\a3-front\desktop-backend',
    [ValidateSet('', 'AfterBackup', 'AfterStage')] [string]$TestFailurePoint = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function New-A3ReleaseError {
    param([Parameter(Mandatory)] [string]$Code, [Parameter(Mandatory)] [string]$Message)

    $exception = [InvalidOperationException]::new($Message)
    $exception.Data['A3Code'] = $Code
    return $exception
}

function Resolve-A3AbsolutePath {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [string]$BasePath
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw (New-A3ReleaseError 'A3_PATH_INVALID' 'A required filesystem path is invalid.')
    }
    try {
        $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $BasePath $Path }
        return [IO.Path]::GetFullPath($candidate)
    }
    catch {
        throw (New-A3ReleaseError 'A3_PATH_INVALID' 'A required filesystem path is invalid.')
    }
}

function Assert-A3PathInsideRepository {
    param(
        [Parameter(Mandatory)] [string]$CandidatePath,
        [Parameter(Mandatory)] [string]$RepositoryPath
    )

    $candidate = Resolve-A3AbsolutePath -Path $CandidatePath
    $root = (Resolve-A3AbsolutePath -Path $RepositoryPath).TrimEnd('\', '/')
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw (New-A3ReleaseError 'A3_PATH_OUTSIDE_REPOSITORY' 'A release path is outside the approved repository root.')
    }
    return $candidate
}

function Test-A3PathChainHasReparsePoint {
    param(
        [Parameter(Mandatory)] [string]$CandidatePath,
        [Parameter(Mandatory)] [string]$RepositoryPath
    )

    $current = Resolve-A3AbsolutePath -Path $CandidatePath
    $root = (Resolve-A3AbsolutePath -Path $RepositoryPath).TrimEnd('\', '/')
    if (-not (Test-Path -LiteralPath $current)) {
        $current = Split-Path -Parent $current
    }
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
        }
        if ($current.TrimEnd('\', '/') -ieq $root) { return $false }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $current) { return $true }
        $current = $parent
    }
    return $true
}

function Assert-A3SafeSourceTree {
    param(
        [Parameter(Mandatory)] [string]$SourcePath,
        [Parameter(Mandatory)] [string]$RepositoryPath
    )

    if (-not (Test-Path -LiteralPath $SourcePath -PathType Container)) {
        throw (New-A3ReleaseError 'A3_BACKEND_SOURCE_MISSING' 'The PyInstaller backend source directory is missing.')
    }
    if (Test-A3PathChainHasReparsePoint -CandidatePath $SourcePath -RepositoryPath $RepositoryPath) {
        throw (New-A3ReleaseError 'A3_SOURCE_REPARSE_POINT' 'The PyInstaller backend source path traverses a reparse point.')
    }
    foreach ($item in @(Get-ChildItem -LiteralPath $SourcePath -Force -Recurse -ErrorAction Stop)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw (New-A3ReleaseError 'A3_SOURCE_REPARSE_POINT' 'The PyInstaller backend source tree contains a reparse point.')
        }
    }
    $apiExecutable = Join-Path $SourcePath 'api.exe'
    if (-not (Test-Path -LiteralPath $apiExecutable -PathType Leaf)) {
        throw (New-A3ReleaseError 'A3_BACKEND_EXECUTABLE_MISSING' 'The PyInstaller backend source does not contain api.exe.')
    }
}

function Get-A3TreeSnapshot {
    param([Parameter(Mandatory)] [string]$RootPath)

    $root = (Resolve-A3AbsolutePath -Path $RootPath).TrimEnd('\', '/')
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    return @(
        Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction Stop |
            Sort-Object -Property FullName |
            ForEach-Object {
                $fullName = Resolve-A3AbsolutePath -Path $_.FullName
                if (-not $fullName.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                    throw (New-A3ReleaseError 'A3_BACKEND_COPY_MISMATCH' 'A staged backend file is outside its approved tree.')
                }
                [pscustomobject][ordered]@{
                    RelativePath = $fullName.Substring($prefix.Length).Replace('\', '/')
                    Length = $_.Length
                    Sha256 = (Get-FileHash -LiteralPath $fullName -Algorithm SHA256 -ErrorAction Stop).Hash
                }
            }
    )
}

function Assert-A3MatchingTrees {
    param(
        [Parameter(Mandatory)] [string]$ExpectedPath,
        [Parameter(Mandatory)] [string]$ActualPath
    )

    $expected = @(Get-A3TreeSnapshot -RootPath $ExpectedPath)
    $actual = @(Get-A3TreeSnapshot -RootPath $ActualPath)
    if ($expected.Count -ne $actual.Count) {
        throw (New-A3ReleaseError 'A3_BACKEND_COPY_MISMATCH' 'The staged backend file set does not match the PyInstaller source.')
    }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if ($expected[$index].RelativePath -cne $actual[$index].RelativePath -or
            $expected[$index].Length -ne $actual[$index].Length -or
            $expected[$index].Sha256 -cne $actual[$index].Sha256) {
            throw (New-A3ReleaseError 'A3_BACKEND_COPY_MISMATCH' 'The staged backend file contents do not match the PyInstaller source.')
        }
    }
}

function Assert-A3SafeTemporarySibling {
    param(
        [Parameter(Mandatory)] [string]$CandidatePath,
        [Parameter(Mandatory)] [string]$TargetParent,
        [Parameter(Mandatory)] [string]$RepositoryPath,
        [Parameter(Mandatory)] [string]$NamePrefix
    )

    $candidate = Assert-A3PathInsideRepository -CandidatePath $CandidatePath -RepositoryPath $RepositoryPath
    if ((Split-Path -Parent $candidate) -ine $TargetParent -or -not ([IO.Path]::GetFileName($candidate)).StartsWith($NamePrefix, [StringComparison]::Ordinal)) {
        throw (New-A3ReleaseError 'A3_PATH_OUTSIDE_REPOSITORY' 'A temporary release directory is outside the approved target sibling path.')
    }
    return $candidate
}

function Remove-A3SafeTemporarySibling {
    param(
        [string]$CandidatePath,
        [string]$TargetParent,
        [string]$RepositoryPath,
        [string]$NamePrefix
    )

    if ([string]::IsNullOrWhiteSpace($CandidatePath) -or -not (Test-Path -LiteralPath $CandidatePath -PathType Container)) { return }
    $safePath = Assert-A3SafeTemporarySibling -CandidatePath $CandidatePath -TargetParent $TargetParent -RepositoryPath $RepositoryPath -NamePrefix $NamePrefix
    if (Test-A3PathChainHasReparsePoint -CandidatePath $safePath -RepositoryPath $RepositoryPath) {
        throw (New-A3ReleaseError 'A3_SOURCE_REPARSE_POINT' 'A temporary release directory traverses a reparse point.')
    }
    Remove-Item -LiteralPath $safePath -Recurse -Force -ErrorAction Stop
}

if (-not [string]::IsNullOrWhiteSpace($TestFailurePoint) -and $env:A3_RELEASE_SCRIPT_TEST_MODE -cne '1') {
    throw (New-A3ReleaseError 'A3_RELEASE_TEST_MODE_REQUIRED' 'Test failure injection is permitted only in release script test mode.')
}

$repositoryPath = Resolve-A3AbsolutePath -Path $RepositoryRoot
if (-not (Test-Path -LiteralPath $repositoryPath -PathType Container) -or
    (Test-A3PathChainHasReparsePoint -CandidatePath $repositoryPath -RepositoryPath $repositoryPath)) {
    throw (New-A3ReleaseError 'A3_PATH_OUTSIDE_REPOSITORY' 'The approved repository root is unavailable or unsafe.')
}

$sourcePath = Assert-A3PathInsideRepository -CandidatePath (Resolve-A3AbsolutePath -Path $Source -BasePath $repositoryPath) -RepositoryPath $repositoryPath
$targetPath = Assert-A3PathInsideRepository -CandidatePath (Resolve-A3AbsolutePath -Path $Target -BasePath $repositoryPath) -RepositoryPath $repositoryPath
$targetParent = Split-Path -Parent $targetPath
if (-not (Test-Path -LiteralPath $targetParent -PathType Container) -or
    (Test-A3PathChainHasReparsePoint -CandidatePath $targetParent -RepositoryPath $repositoryPath)) {
    throw (New-A3ReleaseError 'A3_PATH_OUTSIDE_REPOSITORY' 'The desktop backend target parent is unavailable or unsafe.')
}
if ((Test-Path -LiteralPath $targetPath) -and -not (Test-Path -LiteralPath $targetPath -PathType Container)) {
    throw (New-A3ReleaseError 'A3_BACKEND_TARGET_INVALID' 'The desktop backend target must be a directory.')
}
if ((Test-Path -LiteralPath $targetPath) -and (Test-A3PathChainHasReparsePoint -CandidatePath $targetPath -RepositoryPath $repositoryPath)) {
    throw (New-A3ReleaseError 'A3_BACKEND_TARGET_INVALID' 'The desktop backend target traverses a reparse point.')
}
if (Test-Path -LiteralPath $targetPath -PathType Container) {
    foreach ($item in @(Get-ChildItem -LiteralPath $targetPath -Force -Recurse -ErrorAction Stop)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw (New-A3ReleaseError 'A3_BACKEND_TARGET_INVALID' 'The desktop backend target tree contains a reparse point.')
        }
    }
}

Assert-A3SafeSourceTree -SourcePath $sourcePath -RepositoryPath $repositoryPath

$targetName = [IO.Path]::GetFileName($targetPath)
$stagingPath = Assert-A3SafeTemporarySibling `
    -CandidatePath (Join-Path $targetParent ('.{0}.staging-{1}' -f $targetName, [guid]::NewGuid().ToString('N'))) `
    -TargetParent $targetParent `
    -RepositoryPath $repositoryPath `
    -NamePrefix ('.{0}.staging-' -f $targetName)
$backupPath = Assert-A3SafeTemporarySibling `
    -CandidatePath (Join-Path $targetParent ('.{0}.backup-{1}' -f $targetName, [guid]::NewGuid().ToString('N'))) `
    -TargetParent $targetParent `
    -RepositoryPath $repositoryPath `
    -NamePrefix ('.{0}.backup-' -f $targetName)
$targetMovedToBackup = $false
$stagingMovedToTarget = $false

try {
    New-Item -ItemType Directory -Path $stagingPath -ErrorAction Stop | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $sourcePath -Force -ErrorAction Stop)) {
        Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $stagingPath $item.Name) -Recurse -Force -ErrorAction Stop
    }
    Assert-A3MatchingTrees -ExpectedPath $sourcePath -ActualPath $stagingPath
    if ($TestFailurePoint -ceq 'AfterStage') {
        throw (New-A3ReleaseError 'A3_RELEASE_TEST_FAILURE' 'The requested release test failure was injected after staging.')
    }

    if (Test-Path -LiteralPath $targetPath -PathType Container) {
        [IO.Directory]::Move($targetPath, $backupPath)
        $targetMovedToBackup = $true
    }
    if ($TestFailurePoint -ceq 'AfterBackup') {
        throw (New-A3ReleaseError 'A3_RELEASE_TEST_FAILURE' 'The requested release test failure was injected after backup.')
    }

    [IO.Directory]::Move($stagingPath, $targetPath)
    $stagingMovedToTarget = $true
    Assert-A3MatchingTrees -ExpectedPath $sourcePath -ActualPath $targetPath

    if ($targetMovedToBackup) {
        Remove-A3SafeTemporarySibling -CandidatePath $backupPath -TargetParent $targetParent -RepositoryPath $repositoryPath -NamePrefix ('.{0}.backup-' -f $targetName)
        $targetMovedToBackup = $false
    }
}
catch {
    $failure = $_
    try {
        if ($targetMovedToBackup -and (Test-Path -LiteralPath $backupPath -PathType Container)) {
            if ($stagingMovedToTarget -and (Test-Path -LiteralPath $targetPath -PathType Container)) {
                [IO.Directory]::Move($targetPath, $stagingPath)
                $stagingMovedToTarget = $false
            }
            [IO.Directory]::Move($backupPath, $targetPath)
            $targetMovedToBackup = $false
        }
        elseif ($stagingMovedToTarget -and (Test-Path -LiteralPath $targetPath -PathType Container)) {
            [IO.Directory]::Move($targetPath, $stagingPath)
            $stagingMovedToTarget = $false
        }
    }
    catch {
        throw (New-A3ReleaseError 'A3_BACKEND_ROLLBACK_FAILED' 'The desktop backend target could not be restored after a failed staging operation.')
    }
    throw $failure
}
finally {
    Remove-A3SafeTemporarySibling -CandidatePath $stagingPath -TargetParent $targetParent -RepositoryPath $repositoryPath -NamePrefix ('.{0}.staging-' -f $targetName)
    Remove-A3SafeTemporarySibling -CandidatePath $backupPath -TargetParent $targetParent -RepositoryPath $repositoryPath -NamePrefix ('.{0}.backup-' -f $targetName)
}
