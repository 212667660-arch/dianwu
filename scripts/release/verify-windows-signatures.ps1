param(
    [Parameter(Mandatory)] [string]$ReleaseDir,
    [Parameter(Mandatory)] [string]$Version,
    [Parameter(Mandatory)] [string]$ExpectedPublisher,
    [Parameter(Mandatory)] [string]$SourceCommit,
    [string]$ManifestPath,
    [switch]$InstallAndVerify
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'A3.SignatureVerification.psm1') -Force

function Resolve-A3WrapperPath {
    param([Parameter(Mandatory)] [string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw (New-A3SignatureError 'A3_PATH_INVALID' 'A required filesystem path is invalid.')
    }
    try {
        $resolved = @(Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue)
        if ($resolved.Count -gt 1) { throw [InvalidOperationException]::new('Ambiguous path.') }
        if ($resolved.Count -eq 1) {
            if ($resolved[0].Provider.Name -cne 'FileSystem') { throw [InvalidOperationException]::new('Non-filesystem path.') }
            $providerPath = [string]$resolved[0].ProviderPath
        }
        else {
            $provider = $null
            $drive = $null
            $providerPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
                $Path,
                [ref]$provider,
                [ref]$drive
            )
            if ($null -eq $provider -or $provider.Name -cne 'FileSystem') { throw [InvalidOperationException]::new('Non-filesystem path.') }
        }
        if ($providerPath.StartsWith('\\.\', [StringComparison]::OrdinalIgnoreCase) -or
            $providerPath.StartsWith('\\?\GLOBALROOT\', [StringComparison]::OrdinalIgnoreCase)) {
            throw [InvalidOperationException]::new('Device path.')
        }
        if ($providerPath.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
            $providerPath = '\\' + $providerPath.Substring(8)
        }
        elseif ($providerPath.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
            $providerPath = $providerPath.Substring(4)
        }
        return [IO.Path]::GetFullPath($providerPath)
    }
    catch {
        throw (New-A3SignatureError 'A3_PATH_INVALID' 'A required filesystem path is invalid.')
    }
}

function Test-A3PathChainHasReparsePoint {
    param(
        [Parameter(Mandatory)] [string]$CandidatePath,
        [Parameter(Mandatory)] [string]$RootPath
    )

    $candidate = Resolve-A3WrapperPath -Path $CandidatePath
    $root = (Resolve-A3WrapperPath -Path $RootPath).TrimEnd('\', '/')
    $current = $candidate
    if (-not (Test-Path -LiteralPath $current)) {
        $current = Split-Path -Parent $current
    }
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
        }
        if ($current.TrimEnd('\', '/') -ieq $root) { break }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $current) { break }
        $current = $parent
    }
    return $false
}

function Assert-A3PathContained {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$CandidatePath,
        [Parameter(Mandatory)] [string]$RootPath,
        [Parameter(Mandatory)] [string]$FailureCode,
        [switch]$RejectReparsePoint,
        [switch]$AllowRoot
    )

    $candidate = Resolve-A3WrapperPath -Path $CandidatePath
    $root = (Resolve-A3WrapperPath -Path $RootPath).TrimEnd('\', '/')
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    $inside = $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    if ($AllowRoot -and $candidate.TrimEnd('\', '/') -ieq $root) { $inside = $true }
    if (-not $inside) {
        throw (New-A3SignatureError $FailureCode 'A required path is outside its approved root.')
    }
    if ($RejectReparsePoint -and (Test-A3PathChainHasReparsePoint -CandidatePath $candidate -RootPath $root)) {
        throw (New-A3SignatureError $FailureCode 'A required path traverses a reparse point.')
    }
    return $candidate
}

function Find-A3ExactChildArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$DirectoryPath,
        [Parameter(Mandatory)] [string]$FileName,
        [scriptblock]$ChildProvider
    )

    $directory = Resolve-A3WrapperPath -Path $DirectoryPath
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' 'A required artifact directory is missing.')
    }
    if ($null -eq $ChildProvider) {
        $ChildProvider = {
            param([string]$LiteralPath)
            return @(Get-ChildItem -LiteralPath $LiteralPath -File -Force -ErrorAction Stop)
        }
    }
    $matches = @(& $ChildProvider $directory | Where-Object {
        $null -ne $_ -and $null -ne $_.PSObject.Properties['Name'] -and
        $_.Name -is [string] -and $_.Name -ceq $FileName
    })
    if ($matches.Count -eq 0) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' 'A required signed artifact is missing.')
    }
    if ($matches.Count -gt 1) {
        throw (New-A3SignatureError 'A3_ARTIFACT_AMBIGUOUS' 'More than one required artifact matched the exact expected name.')
    }
    $fullNameProperty = $matches[0].PSObject.Properties['FullName']
    if ($null -eq $fullNameProperty -or $fullNameProperty.Value -isnot [string]) {
        throw (New-A3SignatureError 'A3_PATH_INVALID' 'A required artifact path is invalid.')
    }
    $path = Assert-A3PathContained -CandidatePath ([string]$fullNameProperty.Value) -RootPath $directory -FailureCode 'A3_PATH_INVALID' -RejectReparsePoint
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' 'A required signed artifact is missing.')
    }
    return $path
}

function Assert-A3ArtifactPathsSafe {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [object[]]$Artifacts,
        [Parameter(Mandatory)] [string]$ReleaseDir,
        [string]$InstallDir
    )

    foreach ($artifact in $Artifacts) {
        if ($artifact -isnot [pscustomobject] -or
            $null -eq $artifact.PSObject.Properties['Scope'] -or $artifact.Scope -isnot [string] -or
            $null -eq $artifact.PSObject.Properties['RelativePath'] -or $artifact.RelativePath -isnot [string] -or
            $null -eq $artifact.PSObject.Properties['Path'] -or $artifact.Path -isnot [string]) {
            throw (New-A3SignatureError 'A3_ARTIFACT_PATH_UNSAFE' 'A required artifact descriptor is invalid.')
        }
        $relativePath = [string]$artifact.RelativePath
        if ([string]::IsNullOrWhiteSpace($relativePath) -or [IO.Path]::IsPathRooted($relativePath) -or
            @($relativePath -split '[\/]' | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
            throw (New-A3SignatureError 'A3_ARTIFACT_PATH_UNSAFE' 'A required artifact relative path is invalid.')
        }

        if ($artifact.Scope -in @('package', 'release')) {
            $approvedRoot = $ReleaseDir
        }
        elseif ($artifact.Scope -ceq 'installed' -and -not [string]::IsNullOrWhiteSpace($InstallDir)) {
            $approvedRoot = $InstallDir
        }
        else {
            throw (New-A3SignatureError 'A3_ARTIFACT_PATH_UNSAFE' 'A required artifact scope is invalid.')
        }

        $expectedPath = Resolve-A3WrapperPath -Path (Join-Path $approvedRoot $relativePath.Replace('/', '\'))
        $actualPath = Assert-A3PathContained -CandidatePath $artifact.Path -RootPath $approvedRoot -FailureCode 'A3_ARTIFACT_PATH_UNSAFE' -RejectReparsePoint
        if ($actualPath -ine $expectedPath -or -not (Test-Path -LiteralPath $actualPath -PathType Leaf)) {
            throw (New-A3SignatureError 'A3_ARTIFACT_PATH_UNSAFE' 'A required artifact path does not match its approved relative path.')
        }
    }
}

function Get-A3LockedExecutableSnapshot {
    param(
        [Parameter(Mandatory)] [IO.FileStream]$ArtifactStream,
        [Parameter(Mandatory)] [string]$SafePath
    )

    $information = New-Object A3.ByHandleFileInformation
    if (-not [A3.SignatureNativeMethods]::GetFileInformationByHandle(
        $ArtifactStream.SafeFileHandle.DangerousGetHandle(),
        [ref]$information
    )) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' 'The executable identity could not be established.')
    }

    $capacity = 32768
    $builder = [Text.StringBuilder]::new($capacity)
    $length = [A3.SignatureNativeMethods]::GetFinalPathNameByHandle(
        $ArtifactStream.SafeFileHandle.DangerousGetHandle(),
        $builder,
        [uint32]$capacity,
        [uint32]0
    )
    if ($length -eq 0 -or $length -ge $capacity) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' 'The executable final path could not be established.')
    }

    return [pscustomobject][ordered]@{
        FinalPath = Resolve-A3WrapperPath -Path $builder.ToString()
        VolumeSerialNumber = $information.VolumeSerialNumber
        FileIndexHigh = $information.FileIndexHigh
        FileIndexLow = $information.FileIndexLow
        NumberOfLinks = $information.NumberOfLinks
    }
}

function Assert-A3LockedExecutableSnapshot {
    param(
        [Parameter(Mandatory)] [pscustomobject]$Expected,
        [Parameter(Mandatory)] [pscustomobject]$Actual
    )

    if ($Expected.FinalPath -ine $Actual.FinalPath -or
        $Expected.VolumeSerialNumber -ne $Actual.VolumeSerialNumber -or
        $Expected.FileIndexHigh -ne $Actual.FileIndexHigh -or
        $Expected.FileIndexLow -ne $Actual.FileIndexLow -or
        $Expected.NumberOfLinks -ne 1 -or $Actual.NumberOfLinks -ne 1) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' 'The executable identity changed during locked verification and execution.')
    }
}

function Invoke-A3LockedVerifiedExecutable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [Parameter(Mandatory)] [string]$ApprovedRoot,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [Parameter(Mandatory)] [string]$ExpectedSha256,
        [scriptblock]$RecordProvider,
        [scriptblock]$NativeProcessProvider
    )

    $logicalPath = Assert-A3PathContained -CandidatePath $LiteralPath -RootPath $ApprovedRoot -FailureCode 'A3_ARTIFACT_IDENTITY_CHANGED'
    $artifactStream = $null
    try {
        $artifactStream = [IO.File]::Open(
            $logicalPath,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
    }
    catch {
        throw (New-A3SignatureError 'A3_ARTIFACT_LOCK_FAILED' 'The executable could not be locked for verified execution.')
    }

    try {
        $lockedSnapshot = Get-A3LockedExecutableSnapshot -ArtifactStream $artifactStream -SafePath $logicalPath
        if ($lockedSnapshot.NumberOfLinks -ne 1) {
            throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' 'Multiply linked executables are not permitted.')
        }
        $finalPath = Assert-A3PathContained -CandidatePath $lockedSnapshot.FinalPath -RootPath $ApprovedRoot -FailureCode 'A3_ARTIFACT_IDENTITY_CHANGED' -RejectReparsePoint

        if ($null -eq $RecordProvider) {
            $record = Get-A3SignatureRecord -LiteralPath $finalPath
        }
        else {
            $record = & $RecordProvider $finalPath
        }
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher $ExpectedPublisher -ExpectedSha256 $ExpectedSha256

        $beforeLaunch = Get-A3LockedExecutableSnapshot -ArtifactStream $artifactStream -SafePath $logicalPath
        Assert-A3LockedExecutableSnapshot -Expected $lockedSnapshot -Actual $beforeLaunch
        $exitCode = Invoke-A3NativeExecutable -FilePath $finalPath -Arguments ([string[]]$Arguments) -NativeProcessProvider $NativeProcessProvider
        $afterLaunch = Get-A3LockedExecutableSnapshot -ArtifactStream $artifactStream -SafePath $logicalPath
        Assert-A3LockedExecutableSnapshot -Expected $lockedSnapshot -Actual $afterLaunch
        return $exitCode
    }
    finally {
        $artifactStream.Dispose()
    }
}

function Invoke-A3NativeExecutable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [scriptblock]$NativeProcessProvider
    )

    if ($null -eq $NativeProcessProvider) {
        $NativeProcessProvider = {
            param([string]$LiteralPath, [string[]]$ArgumentList, [bool]$Hidden)
            $parameters = @{
                FilePath = $LiteralPath
                ArgumentList = $ArgumentList
                PassThru = $true
                Wait = $true
                ErrorAction = 'Stop'
            }
            if ($Hidden) { $parameters.WindowStyle = 'Hidden' }
            return Start-Process @parameters
        }
    }
    $result = & $NativeProcessProvider $FilePath ([string[]]$Arguments) $true
    if ($null -eq $result -or $null -eq $result.PSObject.Properties['ExitCode']) {
        throw (New-A3SignatureError 'A3_PROCESS_FAILED' 'A release verification process returned an invalid result.')
    }
    return [int]$result.ExitCode
}

function Initialize-A3ReleaseProcessNativeMethods {
    if ($null -ne ('A3.ReleaseProcessNativeMethods' -as [type])) { return }

    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace A3 {
    public static class ReleaseProcessNativeMethods {
        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr OpenProcess(uint desiredAccess, bool inheritHandle, uint processId);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool QueryFullProcessImageName(
            IntPtr processHandle,
            uint flags,
            StringBuilder executablePath,
            ref uint size
        );

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool TerminateProcess(IntPtr processHandle, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool CloseHandle(IntPtr handle);
    }
}
'@
}

function Stop-A3ResidualProcesses {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$InstallDir,
        [scriptblock]$ProcessListProvider,
        [scriptblock]$ProcessHandleProvider,
        [scriptblock]$ProcessImagePathProvider,
        [scriptblock]$StopProcessProvider,
        [scriptblock]$CloseProcessHandleProvider
    )

    $safeInstallDir = Assert-A3PathContained -CandidatePath $InstallDir -RootPath (Split-Path -Parent $InstallDir) -FailureCode 'A3_INSTALL_PATH_UNSAFE' -RejectReparsePoint
    if ($null -eq $ProcessListProvider) {
        $ProcessListProvider = { return @(Get-Process -ErrorAction SilentlyContinue) }
    }
    if ($null -eq $ProcessHandleProvider) {
        $ProcessHandleProvider = {
            param($Process)
            Initialize-A3ReleaseProcessNativeMethods
            $handle = [A3.ReleaseProcessNativeMethods]::OpenProcess(
                [uint32]0x00101001,
                $false,
                [uint32]$Process.Id
            )
            if ($handle -eq [IntPtr]::Zero) { return $null }
            return [pscustomobject]@{ Handle = $handle; ProcessId = [int]$Process.Id }
        }
    }
    if ($null -eq $ProcessImagePathProvider) {
        $ProcessImagePathProvider = {
            param($HandleContext)
            Initialize-A3ReleaseProcessNativeMethods
            $capacity = 32768
            $builder = [Text.StringBuilder]::new($capacity)
            [uint32]$size = $capacity
            if (-not [A3.ReleaseProcessNativeMethods]::QueryFullProcessImageName(
                $HandleContext.Handle,
                [uint32]0,
                $builder,
                [ref]$size
            )) { return $null }
            return $builder.ToString()
        }
    }
    if ($null -eq $StopProcessProvider) {
        $StopProcessProvider = {
            param($HandleContext)
            Initialize-A3ReleaseProcessNativeMethods
            if (-not [A3.ReleaseProcessNativeMethods]::TerminateProcess($HandleContext.Handle, [uint32]1)) {
                throw (New-A3SignatureError 'A3_PROCESS_FAILED' 'A residual process could not be terminated through its stable handle.')
            }
            $waitResult = [A3.ReleaseProcessNativeMethods]::WaitForSingleObject($HandleContext.Handle, [uint32]10000)
            if ($waitResult -ne 0) {
                throw (New-A3SignatureError 'A3_PROCESS_FAILED' 'A residual process did not exit after stable-handle termination.')
            }
        }
    }
    if ($null -eq $CloseProcessHandleProvider) {
        $CloseProcessHandleProvider = {
            param($HandleContext)
            Initialize-A3ReleaseProcessNativeMethods
            $null = [A3.ReleaseProcessNativeMethods]::CloseHandle($HandleContext.Handle)
        }
    }
    foreach ($process in @(& $ProcessListProvider)) {
        $handleContext = $null
        try {
            $handleContext = & $ProcessHandleProvider $process
            if ($null -eq $handleContext) { continue }
            $processPath = & $ProcessImagePathProvider $handleContext
            if ($processPath -isnot [string] -or [string]::IsNullOrWhiteSpace($processPath)) { continue }
            try {
                $null = Assert-A3PathContained -CandidatePath $processPath -RootPath $safeInstallDir -FailureCode 'A3_PROCESS_PATH_UNSAFE' -RejectReparsePoint
            }
            catch {
                continue
            }
            & $StopProcessProvider $handleContext
        }
        finally {
            if ($null -ne $handleContext) {
                & $CloseProcessHandleProvider $handleContext
            }
        }
    }
}

function Remove-A3IsolatedInstallDirectory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$InstallDir,
        [Parameter(Mandatory)] [string]$RunnerTemp,
        [scriptblock]$RemoveDirectoryProvider
    )

    $safeInstallDir = Assert-A3PathContained -CandidatePath $InstallDir -RootPath $RunnerTemp -FailureCode 'A3_INSTALL_PATH_UNSAFE' -RejectReparsePoint
    if (-not ([IO.Path]::GetFileName($safeInstallDir)).StartsWith('a3-signed-install-', [StringComparison]::Ordinal)) {
        throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'The isolated install directory name is invalid.')
    }
    if (-not (Test-Path -LiteralPath $safeInstallDir -PathType Container)) { return }
    if ($null -eq $RemoveDirectoryProvider) {
        $RemoveDirectoryProvider = {
            param([string]$LiteralPath)
            Remove-Item -LiteralPath $LiteralPath -Recurse -Force -ErrorAction Stop
        }
    }
    & $RemoveDirectoryProvider $safeInstallDir
}

function Invoke-A3WindowsSignatureVerification {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$ReleaseDir,
        [Parameter(Mandatory)] [string]$Version,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [Parameter(Mandatory)] [string]$SourceCommit,
        [string]$ManifestPath,
        [switch]$InstallAndVerify,
        [string]$RepositoryRoot = (Resolve-A3WrapperPath -Path (Join-Path $PSScriptRoot '..\..')),
        [string]$RunnerTemp = $env:RUNNER_TEMP,
        [scriptblock]$RecordProvider,
        [scriptblock]$NativeProcessProvider,
        [scriptblock]$ProcessListProvider,
        [scriptblock]$ProcessHandleProvider,
        [scriptblock]$ProcessImagePathProvider,
        [scriptblock]$StopProcessProvider,
        [scriptblock]$CloseProcessHandleProvider,
        [scriptblock]$RemoveDirectoryProvider,
        [scriptblock]$ArtifactChildProvider,
        [string]$VerifiedAtUtc
    )

    $resolvedRepositoryRoot = Resolve-A3WrapperPath -Path $RepositoryRoot
    if (-not (Test-Path -LiteralPath $resolvedRepositoryRoot -PathType Container)) {
        throw (New-A3SignatureError 'A3_RELEASE_OUTSIDE_REPOSITORY' 'The repository root is unavailable.')
    }
    $resolvedReleaseDir = Assert-A3PathContained -CandidatePath $ReleaseDir -RootPath $resolvedRepositoryRoot -FailureCode 'A3_RELEASE_OUTSIDE_REPOSITORY' -RejectReparsePoint
    if (-not (Test-Path -LiteralPath $resolvedReleaseDir -PathType Container)) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' 'The release directory is missing.')
    }

    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        $ManifestPath = Join-Path $resolvedReleaseDir 'a3-windows-release-manifest.json'
    }
    $resolvedManifestPath = Assert-A3PathContained -CandidatePath $ManifestPath -RootPath $resolvedReleaseDir -FailureCode 'A3_MANIFEST_PATH_UNSAFE' -RejectReparsePoint

    $expectedInstallerName = "智学协作台 Setup $Version.exe"
    $installerPath = Find-A3ExactChildArtifact -DirectoryPath $resolvedReleaseDir -FileName $expectedInstallerName -ChildProvider $ArtifactChildProvider
    $preInstallArtifacts = @(Get-A3RequiredArtifacts -ReleaseDir $resolvedReleaseDir -Version $Version)
    Assert-A3ArtifactPathsSafe -Artifacts $preInstallArtifacts -ReleaseDir $resolvedReleaseDir
    if ((Resolve-A3WrapperPath -Path $preInstallArtifacts[3].Path) -ine $installerPath) {
        throw (New-A3SignatureError 'A3_ARTIFACT_AMBIGUOUS' 'The installer identity did not match the exact required artifact.')
    }
    $preInstallRecords = @(Assert-A3ArtifactSet -Artifacts $preInstallArtifacts -ExpectedPublisher $ExpectedPublisher -RecordProvider $RecordProvider)

    if (-not $InstallAndVerify) {
        $manifestParameters = @{
            ManifestPath = $resolvedManifestPath
            SourceCommit = $SourceCommit
            AppVersion = $Version
            Artifacts = $preInstallArtifacts
            Records = $preInstallRecords
        }
        if (-not [string]::IsNullOrWhiteSpace($VerifiedAtUtc)) { $manifestParameters.VerifiedAtUtc = $VerifiedAtUtc }
        New-A3ReleaseManifest @manifestParameters
        return
    }

    if ([string]::IsNullOrWhiteSpace($RunnerTemp)) {
        throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'RUNNER_TEMP is required for isolated install verification.')
    }
    $resolvedRunnerTemp = Resolve-A3WrapperPath -Path $RunnerTemp
    if (-not (Test-Path -LiteralPath $resolvedRunnerTemp -PathType Container)) {
        throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'RUNNER_TEMP is unavailable.')
    }
    if (Test-A3PathChainHasReparsePoint -CandidatePath $resolvedRunnerTemp -RootPath $resolvedRunnerTemp) {
        throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'RUNNER_TEMP traverses a reparse point.')
    }

    $installDir = Join-Path $resolvedRunnerTemp ("a3-signed-install-{0}" -f [guid]::NewGuid().ToString('N'))
    $uninstallerPath = $null
    $verifiedUninstallerSha256 = $null
    $installedArtifactsVerified = $false
    New-Item -ItemType Directory -Path $installDir -ErrorAction Stop | Out-Null
    $installDir = Assert-A3PathContained -CandidatePath $installDir -RootPath $resolvedRunnerTemp -FailureCode 'A3_INSTALL_PATH_UNSAFE' -RejectReparsePoint
    if (@(Get-ChildItem -LiteralPath $installDir -Force -ErrorAction Stop).Count -ne 0) {
        throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'The isolated install directory was not empty.')
    }

    try {
        $installerArguments = [string[]]@('/S', "/D=$installDir")
        $installerExitCode = Invoke-A3LockedVerifiedExecutable -LiteralPath $installerPath -ApprovedRoot $resolvedReleaseDir -Arguments $installerArguments -ExpectedPublisher $ExpectedPublisher -ExpectedSha256 $preInstallRecords[3].Sha256 -RecordProvider $RecordProvider -NativeProcessProvider $NativeProcessProvider
        if ($installerExitCode -ne 0) {
            throw (New-A3SignatureError 'A3_INSTALLER_FAILED' 'The signed installer returned a nonzero exit code.')
        }

        $uninstallerPath = Find-A3ExactChildArtifact -DirectoryPath $installDir -FileName 'Uninstall 智学协作台.exe' -ChildProvider $ArtifactChildProvider
        $allArtifacts = @(Get-A3RequiredArtifacts -ReleaseDir $resolvedReleaseDir -InstallDir $installDir -Version $Version)
        Assert-A3ArtifactPathsSafe -Artifacts $allArtifacts -ReleaseDir $resolvedReleaseDir -InstallDir $installDir
        $records = @(Assert-A3ArtifactSet -Artifacts $allArtifacts -ExpectedPublisher $ExpectedPublisher -RecordProvider $RecordProvider)
        $verifiedUninstallerSha256 = $records[7].Sha256
        $installedArtifactsVerified = $true
        $manifestParameters = @{
            ManifestPath = $resolvedManifestPath
            SourceCommit = $SourceCommit
            AppVersion = $Version
            Artifacts = $allArtifacts
            Records = $records
        }
        if (-not [string]::IsNullOrWhiteSpace($VerifiedAtUtc)) { $manifestParameters.VerifiedAtUtc = $VerifiedAtUtc }
        New-A3ReleaseManifest @manifestParameters
    }
    finally {
        $safeInstallDir = Assert-A3PathContained -CandidatePath $installDir -RootPath $resolvedRunnerTemp -FailureCode 'A3_INSTALL_PATH_UNSAFE' -RejectReparsePoint
        $safeUninstaller = $null
        if ($installedArtifactsVerified -and $null -ne $uninstallerPath) {
            $safeUninstaller = Assert-A3PathContained -CandidatePath $uninstallerPath -RootPath $safeInstallDir -FailureCode 'A3_INSTALL_PATH_UNSAFE' -RejectReparsePoint
            if (-not (Test-Path -LiteralPath $safeUninstaller -PathType Leaf)) {
                throw (New-A3SignatureError 'A3_INSTALL_PATH_UNSAFE' 'The installed uninstaller is unavailable.')
            }
        }

        $cleanupError = $null
        try {
            if ($null -ne $safeUninstaller) {
                $uninstallerExitCode = Invoke-A3LockedVerifiedExecutable -LiteralPath $safeUninstaller -ApprovedRoot $safeInstallDir -Arguments ([string[]]@('/S')) -ExpectedPublisher $ExpectedPublisher -ExpectedSha256 $verifiedUninstallerSha256 -RecordProvider $RecordProvider -NativeProcessProvider $NativeProcessProvider
                if ($uninstallerExitCode -ne 0) {
                    throw (New-A3SignatureError 'A3_UNINSTALLER_FAILED' 'The installed uninstaller returned a nonzero exit code.')
                }
            }
        }
        catch {
            $cleanupError = $_
        }
        Stop-A3ResidualProcesses -InstallDir $safeInstallDir -ProcessListProvider $ProcessListProvider -ProcessHandleProvider $ProcessHandleProvider -ProcessImagePathProvider $ProcessImagePathProvider -StopProcessProvider $StopProcessProvider -CloseProcessHandleProvider $CloseProcessHandleProvider
        Remove-A3IsolatedInstallDirectory -InstallDir $safeInstallDir -RunnerTemp $resolvedRunnerTemp -RemoveDirectoryProvider $RemoveDirectoryProvider
        if ($null -ne $cleanupError) { throw $cleanupError }
    }
}

Invoke-A3WindowsSignatureVerification @PSBoundParameters
