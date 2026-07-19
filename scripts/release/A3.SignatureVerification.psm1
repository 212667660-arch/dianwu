Set-StrictMode -Version Latest

if ($null -eq ('A3.SignatureNativeMethods' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace A3 {
    [StructLayout(LayoutKind.Sequential)]
    public struct ByHandleFileInformation {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    public static class SignatureNativeMethods {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern uint GetFinalPathNameByHandle(
            IntPtr fileHandle,
            StringBuilder filePath,
            uint filePathLength,
            uint flags
        );

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetFileInformationByHandle(
            IntPtr fileHandle,
            out ByHandleFileInformation fileInformation
        );
    }
}
'@
}

function New-A3SignatureError {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Code,
        [Parameter(Mandatory)] [string]$Message
    )

    $exception = [System.InvalidOperationException]::new($Message)
    $exception.Data['A3Code'] = $Code
    return $exception
}

function Get-A3RecordString {
    param(
        [Parameter(Mandatory)] [pscustomobject]$Record,
        [Parameter(Mandatory)] [string]$Name,
        [switch]$AllowEmpty
    )

    $property = $Record.PSObject.Properties[$Name]
    if ($null -eq $property -or $property.Value -isnot [string]) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record is missing a required string field.')
    }
    if (-not $AllowEmpty -and [string]::IsNullOrWhiteSpace($property.Value)) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an empty required field.')
    }
    return [string]$property.Value
}

function Get-A3SafeRecordPath {
    param([Parameter(Mandatory)] [pscustomobject]$Record)

    $property = $Record.PSObject.Properties['Path']
    if ($null -ne $property -and $property.Value -is [string] -and -not [string]::IsNullOrWhiteSpace($property.Value)) {
        return [string]$property.Value
    }
    return '<unknown-artifact>'
}

function ConvertTo-A3UtcDate {
    param([Parameter(Mandatory)] [string]$Value)

    if ($Value -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?Z$') {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid UTC date value.')
    }

    $parsed = [DateTimeOffset]::MinValue
    [string[]]$formats = @(
        "yyyy-MM-dd'T'HH:mm:ss'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.f'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.ff'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.fff'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.ffff'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.fffff'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'"
        "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'"
    )
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor
        [Globalization.DateTimeStyles]::AdjustToUniversal
    if (-not [DateTimeOffset]::TryParseExact(
        $Value,
        $formats,
        [Globalization.CultureInfo]::InvariantCulture,
        $styles,
        [ref]$parsed
    )) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid UTC date value.')
    }
    return $parsed.ToUniversalTime()
}

function ConvertTo-A3CanonicalUtcText {
    param([Parameter(Mandatory)] [DateTimeOffset]$Value)

    return $Value.ToUniversalTime().UtcDateTime.ToString(
        "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'",
        [Globalization.CultureInfo]::InvariantCulture
    )
}

function Test-A3Sha256Text {
    param([AllowNull()] $Value)

    return $Value -is [string] -and
        $Value.Length -eq 64 -and
        $Value -match '\A[A-Fa-f0-9]{64}\z'
}

function ConvertFrom-A3SignToolVerificationOutput {
    param(
        [Parameter(Mandatory)] [string]$OutputText,
        [string]$SafePath = '<artifact>'
    )

    $signatureIndexMatches = [regex]::Matches(
        $OutputText,
        '(?im)^\s*Signature Index:\s*\d+\b[^\r\n]*'
    )
    if ($signatureIndexMatches.Count -gt 1) {
        throw (New-A3SignatureError 'A3_MULTIPLE_SIGNATURES_UNSUPPORTED' "Multiple Authenticode signatures are not supported for $SafePath.")
    }

    $verificationBlock = $OutputText
    if ($signatureIndexMatches.Count -eq 1) {
        $verificationBlock = $OutputText.Substring($signatureIndexMatches[0].Index)
    }

    $timestampMatch = [regex]::Match(
        $verificationBlock,
        '(?im)^\s*The signature is timestamped(?:\s+(?:at|on))?\s*:\s*(?<timestamp>.+?)\s*$'
    )
    if (-not $timestampMatch.Success) {
        throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $SafePath.")
    }

    $localTimestamp = [datetime]::MinValue
    [string[]]$timestampFormats = @(
        'ddd MMM dd HH:mm:ss yyyy'
        'ddd MMM d HH:mm:ss yyyy'
    )
    if (-not [datetime]::TryParseExact(
        $timestampMatch.Groups['timestamp'].Value,
        $timestampFormats,
        [Globalization.CultureInfo]::GetCultureInfo('en-US'),
        [Globalization.DateTimeStyles]::AllowWhiteSpaces,
        [ref]$localTimestamp
    )) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The trusted timestamp is invalid for $SafePath.")
    }

    try {
        $unspecifiedTimestamp = [datetime]::SpecifyKind($localTimestamp, [DateTimeKind]::Unspecified)
        $timestampUtc = [TimeZoneInfo]::ConvertTimeToUtc($unspecifiedTimestamp, [TimeZoneInfo]::Local)
    }
    catch {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The trusted timestamp is invalid for $SafePath.")
    }

    $hashMatch = [regex]::Match(
        $verificationBlock,
        '(?im)^[ \t]*Hash of file \(sha256\):[ \t]*(?<sha256>[A-Fa-f0-9]{64})[ \t]*(?:\r?\n|\z)'
    )
    if (-not $hashMatch.Success -or -not (Test-A3Sha256Text -Value $hashMatch.Groups['sha256'].Value)) {
        throw (New-A3SignatureError 'A3_DIGEST_NOT_SHA256' "A SHA-256 file digest was not reported for $SafePath.")
    }

    return [pscustomobject][ordered]@{
        TimestampUtc = ConvertTo-A3CanonicalUtcText -Value ([DateTimeOffset]$timestampUtc)
        FileDigestAlgorithm = 'SHA256'
        ReportedSha256 = $hashMatch.Groups['sha256'].Value.ToUpperInvariant()
    }
}

function Assert-A3SignatureRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [AllowNull()] [pscustomobject]$Record,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [string]$ExpectedSha256
    )

    if ($null -eq $Record) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record must be a PSCustomObject.')
    }

    $path = Get-A3SafeRecordPath -Record $Record
    $recordPath = Get-A3RecordString -Record $Record -Name 'Path'
    $status = Get-A3RecordString -Record $Record -Name 'Status'
    $subject = Get-A3RecordString -Record $Record -Name 'Subject'
    $digestAlgorithm = Get-A3RecordString -Record $Record -Name 'FileDigestAlgorithm'

    if ([string]::IsNullOrWhiteSpace($ExpectedPublisher)) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The expected publisher must be a non-empty string.')
    }
    if ($status -cne 'Valid') {
        throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Invalid Authenticode status for $path.")
    }
    if ($subject -cne $ExpectedPublisher) {
        throw (New-A3SignatureError 'A3_PUBLISHER_MISMATCH' "Unexpected signer for $path.")
    }
    if ($digestAlgorithm -cne 'SHA256') {
        throw (New-A3SignatureError 'A3_DIGEST_NOT_SHA256' "Non-SHA256 file digest for $path.")
    }

    $timestampProperty = $Record.PSObject.Properties['TimestampUtc']
    if ($null -eq $timestampProperty -or $null -eq $timestampProperty.Value -or
        ($timestampProperty.Value -is [string] -and [string]::IsNullOrWhiteSpace($timestampProperty.Value))) {
        throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $path.")
    }
    if ($timestampProperty.Value -isnot [string]) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid timestamp field.')
    }

    $notBeforeText = Get-A3RecordString -Record $Record -Name 'CertificateNotBeforeUtc'
    $notAfterText = Get-A3RecordString -Record $Record -Name 'CertificateNotAfterUtc'
    $recordSha256 = Get-A3RecordString -Record $Record -Name 'Sha256'
    if (-not (Test-A3Sha256Text -Value $recordSha256)) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid SHA-256 value.')
    }

    $timestamp = ConvertTo-A3UtcDate -Value ([string]$timestampProperty.Value)
    $notBefore = ConvertTo-A3UtcDate -Value $notBeforeText
    $notAfter = ConvertTo-A3UtcDate -Value $notAfterText
    if ($notBefore -gt $notAfter) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid certificate validity interval.')
    }
    if ($timestamp -lt $notBefore -or $timestamp -gt $notAfter) {
        throw (New-A3SignatureError 'A3_TIMESTAMP_OUTSIDE_CERTIFICATE' "Timestamp outside signer certificate validity for $recordPath.")
    }

    if ($PSBoundParameters.ContainsKey('ExpectedSha256')) {
        if (-not (Test-A3Sha256Text -Value $ExpectedSha256)) {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The expected SHA-256 value is invalid.')
        }
        if ($recordSha256.ToUpperInvariant() -cne $ExpectedSha256.ToUpperInvariant()) {
            throw (New-A3SignatureError 'A3_HASH_MISMATCH' "SHA-256 mismatch for $recordPath.")
        }
    }
}

function Resolve-A3FileSystemPath {
    param([Parameter(Mandatory)] [string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw (New-A3SignatureError 'A3_PATH_INVALID' 'The artifact path is not a valid filesystem path.')
    }

    try {
        $resolved = @(Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue)
        if ($resolved.Count -gt 1) {
            throw [InvalidOperationException]::new('Multiple paths resolved.')
        }

        if ($resolved.Count -eq 1) {
            if ($resolved[0].Provider.Name -cne 'FileSystem') {
                throw [InvalidOperationException]::new('Non-filesystem provider.')
            }
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
            if ($null -eq $provider -or $provider.Name -cne 'FileSystem') {
                throw [InvalidOperationException]::new('Non-filesystem provider.')
            }
        }

        if ($providerPath.StartsWith('\\.\', [StringComparison]::OrdinalIgnoreCase) -or
            $providerPath.StartsWith('\\?\GLOBALROOT\', [StringComparison]::OrdinalIgnoreCase)) {
            throw [InvalidOperationException]::new('Device path.')
        }
        if ($providerPath.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
            $providerPath = '\\' + $providerPath.Substring(8)
        }
        elseif ($providerPath.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
            $withoutPrefix = $providerPath.Substring(4)
            if ($withoutPrefix -notmatch '\A[A-Za-z]:[\\/]') {
                throw [InvalidOperationException]::new('Unsupported extended path.')
            }
            $providerPath = $withoutPrefix
        }

        return [IO.Path]::GetFullPath($providerPath)
    }
    catch {
        throw (New-A3SignatureError 'A3_PATH_INVALID' 'The artifact path is not a valid filesystem path.')
    }
}

function ConvertTo-A3CanonicalWindowsPath {
    param([Parameter(Mandatory)] [string]$Path)

    return (Resolve-A3FileSystemPath -Path $Path).ToUpperInvariant()
}

function Assert-A3SignatureRecords {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [object[]]$Records,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [System.Collections.IDictionary]$ExpectedSha256ByPath
    )

    $recordEntries = [System.Collections.Generic.List[pscustomobject]]::new()
    $recordPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($record in $Records) {
        if ($record -isnot [pscustomobject]) {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'Every signature record must be a PSCustomObject.')
        }

        $recordPath = Get-A3RecordString -Record $record -Name 'Path'
        $canonicalPath = ConvertTo-A3CanonicalWindowsPath -Path $recordPath
        if (-not $recordPaths.Add($canonicalPath)) {
            throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
        }
        $recordEntries.Add([pscustomobject]@{
            Record = $record
            CanonicalPath = $canonicalPath
        })
    }

    $validated = [System.Collections.Generic.List[pscustomobject]]::new()
    if ($PSBoundParameters.ContainsKey('ExpectedSha256ByPath')) {
        if ($null -eq $ExpectedSha256ByPath) {
            throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
        }

        $expectedHashes = [System.Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($mapPath in $ExpectedSha256ByPath.Keys) {
            if ($mapPath -isnot [string]) {
                throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
            }
            $canonicalMapPath = ConvertTo-A3CanonicalWindowsPath -Path $mapPath
            if ($expectedHashes.ContainsKey($canonicalMapPath)) {
                throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
            }

            $expectedHash = $ExpectedSha256ByPath[$mapPath]
            if (-not (Test-A3Sha256Text -Value $expectedHash)) {
                throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The expected SHA-256 value is invalid.')
            }
            $expectedHashes.Add($canonicalMapPath, $expectedHash.ToUpperInvariant())
        }

        if ($expectedHashes.Count -ne $recordEntries.Count) {
            throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
        }
        foreach ($entry in $recordEntries) {
            if (-not $expectedHashes.ContainsKey($entry.CanonicalPath)) {
                throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
            }
        }

        foreach ($entry in $recordEntries) {
            Assert-A3SignatureRecord -Record $entry.Record -ExpectedPublisher $ExpectedPublisher -ExpectedSha256 $expectedHashes[$entry.CanonicalPath]
            $validated.Add($entry.Record)
        }
    }
    else {
        foreach ($entry in $recordEntries) {
            Assert-A3SignatureRecord -Record $entry.Record -ExpectedPublisher $ExpectedPublisher
            $validated.Add($entry.Record)
        }
    }
    return $validated.ToArray()
}

function Get-A3ApprovedSignToolInfo {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$SdkBinRoot
    )

    try {
        $rootPath = (Resolve-A3FileSystemPath -Path $SdkBinRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        $resolvedPath = Resolve-A3FileSystemPath -Path $Path
    }
    catch {
        return $null
    }
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf) -or
        (Test-A3PathChainContainsReparsePoint -RootPath $SdkBinRoot -Path $Path)) {
        return $null
    }

    if (-not $resolvedPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }

    $relativePath = $resolvedPath.Substring($rootPath.Length)
    $parts = @($relativePath -split '[\\/]')
    if ($parts.Count -ne 3 -or $parts[1] -ine 'x64' -or $parts[2] -ine 'signtool.exe') {
        return $null
    }

    $version = $null
    if (-not [version]::TryParse($parts[0], [ref]$version)) {
        return $null
    }

    return [pscustomobject]@{
        Path = $resolvedPath
        Version = $version
    }
}

function Test-A3PathChainContainsReparsePoint {
    param(
        [Parameter(Mandatory)] [string]$RootPath,
        [Parameter(Mandatory)] [string]$Path
    )

    try {
        $rootFullPath = [IO.Path]::GetFullPath($RootPath).TrimEnd('\', '/')
        $pathFullPath = [IO.Path]::GetFullPath($Path)
        if ($pathFullPath -ine $rootFullPath -and
            -not $pathFullPath.StartsWith($rootFullPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }

        $currentPath = $rootFullPath
        $pathsToCheck = [Collections.Generic.List[string]]::new()
        $pathsToCheck.Add($currentPath)
        if ($pathFullPath -ine $rootFullPath) {
            $relativePath = $pathFullPath.Substring($rootFullPath.Length).TrimStart('\', '/')
            foreach ($part in @($relativePath -split '[\\/]')) {
                $currentPath = Join-Path $currentPath $part
                $pathsToCheck.Add($currentPath)
            }
        }

        foreach ($pathToCheck in $pathsToCheck) {
            if (Test-Path -LiteralPath $pathToCheck) {
                $attributes = [IO.File]::GetAttributes($pathToCheck)
                if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    return $true
                }
            }
        }
        return $false
    }
    catch {
        return $true
    }
}

function Get-A3WindowsSdkRootFromRegistry {
    foreach ($registryView in @(
        [Microsoft.Win32.RegistryView]::Registry64
        [Microsoft.Win32.RegistryView]::Registry32
    )) {
        $baseKey = $null
        $installedRootsKey = $null
        try {
            $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
                [Microsoft.Win32.RegistryHive]::LocalMachine,
                $registryView
            )
            $installedRootsKey = $baseKey.OpenSubKey('SOFTWARE\Microsoft\Windows Kits\Installed Roots', $false)
            if ($null -ne $installedRootsKey) {
                $kitsRoot10 = $installedRootsKey.GetValue('KitsRoot10', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                if ($kitsRoot10 -is [string] -and -not [string]::IsNullOrWhiteSpace($kitsRoot10)) {
                    return $kitsRoot10
                }
            }
        }
        catch {
            continue
        }
        finally {
            if ($null -ne $installedRootsKey) {
                $installedRootsKey.Dispose()
            }
            if ($null -ne $baseKey) {
                $baseKey.Dispose()
            }
        }
    }

    throw (New-A3SignatureError 'A3_WINDOWS_SDK_ROOT_INVALID' 'The Windows SDK root could not be obtained from the installed-roots registry.')
}

function Resolve-A3WindowsSdkRoot {
    param([Parameter(Mandatory)] [scriptblock]$SdkRootProvider)

    try {
        $providedRoot = & $SdkRootProvider
        if ($providedRoot -isnot [string] -or [string]::IsNullOrWhiteSpace($providedRoot)) {
            throw [InvalidOperationException]::new('Missing SDK root.')
        }
        $sdkRoot = Resolve-A3FileSystemPath -Path $providedRoot
        if (-not (Test-Path -LiteralPath $sdkRoot -PathType Container)) {
            throw [InvalidOperationException]::new('Missing SDK root.')
        }
        $attributes = [IO.File]::GetAttributes($sdkRoot)
        if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw [InvalidOperationException]::new('Reparse SDK root.')
        }
        $pathRoot = [IO.Path]::GetPathRoot($sdkRoot)
        if ([string]::IsNullOrWhiteSpace($pathRoot) -or
            (Test-A3PathChainContainsReparsePoint -RootPath $pathRoot -Path $sdkRoot)) {
            throw [InvalidOperationException]::new('Reparse SDK root chain.')
        }
        return $sdkRoot
    }
    catch {
        throw (New-A3SignatureError 'A3_WINDOWS_SDK_ROOT_INVALID' 'The Windows SDK root is missing or invalid.')
    }
}

function Find-A3SignToolCore {
    param(
        [Parameter(Mandatory)] [scriptblock]$SdkRootProvider,
        [string]$ExplicitPath
    )

    $sdkRoot = Resolve-A3WindowsSdkRoot -SdkRootProvider $SdkRootProvider
    $windowsKitBin = Join-Path $sdkRoot 'bin'
    if (Test-Path -LiteralPath $windowsKitBin -PathType Container) {
        $binAttributes = [IO.File]::GetAttributes($windowsKitBin)
        if (($binAttributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw (New-A3SignatureError 'A3_WINDOWS_SDK_ROOT_INVALID' 'The Windows SDK root is missing or invalid.')
        }
    }

    if ($PSBoundParameters.ContainsKey('ExplicitPath')) {
        $approved = Get-A3ApprovedSignToolInfo -Path $ExplicitPath -SdkBinRoot $windowsKitBin
        if ($null -eq $approved) {
            throw (New-A3SignatureError 'A3_SIGNTOOL_NOT_APPROVED' 'The explicit signtool path is outside the approved Windows SDK location.')
        }
        return $approved.Path
    }

    if (Test-Path -LiteralPath $windowsKitBin -PathType Container) {
        $candidates = @(
            Get-ChildItem -LiteralPath $windowsKitBin -Directory -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $version = $null
                    if ([version]::TryParse($_.Name, [ref]$version)) {
                        $candidatePath = Join-Path $_.FullName 'x64\signtool.exe'
                        Get-A3ApprovedSignToolInfo -Path $candidatePath -SdkBinRoot $windowsKitBin
                    }
                } |
                Where-Object { $null -ne $_ } |
                Sort-Object -Property @{ Expression = 'Version'; Descending = $true }, @{ Expression = 'Path'; Descending = $true }
        )
        if ($candidates.Count -gt 0) {
            return $candidates[0].Path
        }
    }

    throw (New-A3SignatureError 'A3_SIGNTOOL_NOT_FOUND' 'Windows SDK signtool.exe was not found in an approved location.')
}

function Find-A3SignTool {
    [CmdletBinding()]
    param([Alias('SignToolPath')] [string]$ExplicitPath)

    $sdkRootProvider = { Get-A3WindowsSdkRootFromRegistry }
    if ($PSBoundParameters.ContainsKey('ExplicitPath')) {
        return Find-A3SignToolCore -SdkRootProvider $sdkRootProvider -ExplicitPath $ExplicitPath
    }
    return Find-A3SignToolCore -SdkRootProvider $sdkRootProvider
}

function Invoke-A3RawSha256Provider {
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [Parameter(Mandatory)] [IO.Stream]$ArtifactStream,
        [Parameter(Mandatory)] [scriptblock]$HashProvider
    )

    try {
        $ArtifactStream.Position = 0
        $sha256 = & $HashProvider $ArtifactStream
        $ArtifactStream.Position = 0
    }
    catch {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The SHA-256 digest could not be read for $LiteralPath.")
    }
    if (-not (Test-A3Sha256Text -Value $sha256)) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The SHA-256 digest could not be read for $LiteralPath.")
    }
    return $sha256.ToUpperInvariant()
}

function Get-A3ArtifactIdentity {
    param(
        [Parameter(Mandatory)] [string]$SafePath,
        [Parameter(Mandatory)] [IO.FileStream]$ArtifactStream
    )

    $information = New-Object A3.ByHandleFileInformation
    if (-not [A3.SignatureNativeMethods]::GetFileInformationByHandle(
        $ArtifactStream.SafeFileHandle.DangerousGetHandle(),
        [ref]$information
    )) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' "The signed artifact identity could not be established: $SafePath.")
    }

    return [pscustomobject]@{
        VolumeSerialNumber = $information.VolumeSerialNumber
        FileIndexHigh = $information.FileIndexHigh
        FileIndexLow = $information.FileIndexLow
    }
}

function Get-A3FinalPathFromArtifactHandle {
    param(
        [Parameter(Mandatory)] [string]$SafePath,
        [Parameter(Mandatory)] [IO.FileStream]$ArtifactStream
    )

    $capacity = 32768
    $builder = [Text.StringBuilder]::new($capacity)
    $length = [A3.SignatureNativeMethods]::GetFinalPathNameByHandle(
        $ArtifactStream.SafeFileHandle.DangerousGetHandle(),
        $builder,
        [uint32]$capacity,
        [uint32]0
    )
    if ($length -eq 0 -or $length -ge $capacity) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' "The signed artifact final path could not be established: $SafePath.")
    }

    try {
        return Resolve-A3FileSystemPath -Path $builder.ToString()
    }
    catch {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' "The signed artifact final path could not be established: $SafePath.")
    }
}

function Assert-A3ArtifactPathIdentity {
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [Parameter(Mandatory)] [pscustomobject]$ExpectedIdentity
    )

    $pathStream = $null
    try {
        $pathStream = [IO.File]::Open(
            $LiteralPath,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
        $actualIdentity = Get-A3ArtifactIdentity -SafePath $LiteralPath -ArtifactStream $pathStream
    }
    catch {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' "The signed artifact path no longer identifies the locked file: $LiteralPath.")
    }
    finally {
        if ($null -ne $pathStream) {
            $pathStream.Dispose()
        }
    }

    if ($actualIdentity.VolumeSerialNumber -ne $ExpectedIdentity.VolumeSerialNumber -or
        $actualIdentity.FileIndexHigh -ne $ExpectedIdentity.FileIndexHigh -or
        $actualIdentity.FileIndexLow -ne $ExpectedIdentity.FileIndexLow) {
        throw (New-A3SignatureError 'A3_ARTIFACT_IDENTITY_CHANGED' "The signed artifact path no longer identifies the locked file: $LiteralPath.")
    }
}

function Get-A3SignatureRecordCore {
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [Parameter(Mandatory)] [string]$SignToolPath,
        [Parameter(Mandatory)] [scriptblock]$SignatureProvider,
        [Parameter(Mandatory)] [scriptblock]$HashProvider,
        [Parameter(Mandatory)] [scriptblock]$NativeProcessProvider
    )

    try {
        $artifactStream = [IO.File]::Open(
            $LiteralPath,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
    }
    catch {
        throw (New-A3SignatureError 'A3_ARTIFACT_LOCK_FAILED' "The signed artifact could not be locked for verification: $LiteralPath.")
    }

    try {
        $lockedIdentity = Get-A3ArtifactIdentity -SafePath $LiteralPath -ArtifactStream $artifactStream
        $verificationPath = Get-A3FinalPathFromArtifactHandle -SafePath $LiteralPath -ArtifactStream $artifactStream
        Assert-A3ArtifactPathIdentity -LiteralPath $LiteralPath -ExpectedIdentity $lockedIdentity

        $sha256BeforeVerification = Invoke-A3RawSha256Provider `
            -LiteralPath $LiteralPath `
            -ArtifactStream $artifactStream `
            -HashProvider $HashProvider
        Assert-A3ArtifactPathIdentity -LiteralPath $LiteralPath -ExpectedIdentity $lockedIdentity

        try {
            $signature = & $SignatureProvider $verificationPath
        }
        catch {
            throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Authenticode verification failed for $LiteralPath.")
        }
        if ($null -eq $signature) {
            throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Invalid Authenticode signature for $LiteralPath.")
        }
        $statusProperty = $signature.PSObject.Properties['Status']
        $signerProperty = $signature.PSObject.Properties['SignerCertificate']
        if ($null -eq $statusProperty -or $null -eq $statusProperty.Value -or
            $statusProperty.Value.ToString() -cne 'Valid' -or
            $null -eq $signerProperty -or $null -eq $signerProperty.Value) {
            throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Invalid Authenticode signature for $LiteralPath.")
        }
        $signatureStatus = $statusProperty.Value.ToString()
        $certificate = $signerProperty.Value
        Assert-A3ArtifactPathIdentity -LiteralPath $LiteralPath -ExpectedIdentity $lockedIdentity

        $arguments = @('verify', '/pa', '/all', '/v', $verificationPath)
        try {
            $nativeResult = & $NativeProcessProvider $SignToolPath $arguments
        }
        catch {
            throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Windows signature verification failed for $LiteralPath.")
        }
        if ($null -eq $nativeResult -or
            $null -eq $nativeResult.PSObject.Properties['ExitCode'] -or
            $null -eq $nativeResult.PSObject.Properties['Output'] -or
            $nativeResult.ExitCode -ne 0) {
            throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Windows signature verification failed for $LiteralPath.")
        }
        Assert-A3ArtifactPathIdentity -LiteralPath $LiteralPath -ExpectedIdentity $lockedIdentity

        $outputText = @($nativeResult.Output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        $timestampCertificateProperty = $signature.PSObject.Properties['TimeStamperCertificate']
        if ($null -eq $timestampCertificateProperty -or $null -eq $timestampCertificateProperty.Value) {
            throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $LiteralPath.")
        }

        $parsedSignToolOutput = ConvertFrom-A3SignToolVerificationOutput -OutputText $outputText -SafePath $LiteralPath
        $sha256AfterVerification = Invoke-A3RawSha256Provider `
            -LiteralPath $LiteralPath `
            -ArtifactStream $artifactStream `
            -HashProvider $HashProvider
        Assert-A3ArtifactPathIdentity -LiteralPath $LiteralPath -ExpectedIdentity $lockedIdentity
        if ($sha256BeforeVerification -cne $sha256AfterVerification) {
            throw (New-A3SignatureError 'A3_HASH_MISMATCH' "SHA-256 changed during signature verification for $LiteralPath.")
        }

        $subjectProperty = $certificate.PSObject.Properties['Subject']
        $notBeforeProperty = $certificate.PSObject.Properties['NotBefore']
        $notAfterProperty = $certificate.PSObject.Properties['NotAfter']
        if ($null -eq $subjectProperty -or $subjectProperty.Value -isnot [string] -or
            [string]::IsNullOrWhiteSpace($subjectProperty.Value) -or
            $null -eq $notBeforeProperty -or $null -eq $notBeforeProperty.Value -or
            $null -eq $notAfterProperty -or $null -eq $notAfterProperty.Value) {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The signer certificate metadata is invalid for $LiteralPath.")
        }
        try {
            $notBefore = ([DateTimeOffset]$notBeforeProperty.Value).ToUniversalTime()
            $notAfter = ([DateTimeOffset]$notAfterProperty.Value).ToUniversalTime()
        }
        catch {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The signer certificate metadata is invalid for $LiteralPath.")
        }
        return [pscustomobject][ordered]@{
            Path = $LiteralPath
            Status = $signatureStatus
            Subject = [string]$subjectProperty.Value
            FileDigestAlgorithm = $parsedSignToolOutput.FileDigestAlgorithm
            TimestampUtc = $parsedSignToolOutput.TimestampUtc
            CertificateNotBeforeUtc = ConvertTo-A3CanonicalUtcText -Value $notBefore
            CertificateNotAfterUtc = ConvertTo-A3CanonicalUtcText -Value $notAfter
            Sha256 = $sha256BeforeVerification
        }
    }
    finally {
        $artifactStream.Dispose()
    }
}

function Get-A3SignatureRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [string]$SignToolPath
    )

    $resolvedPath = Resolve-A3FileSystemPath -Path $LiteralPath
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' "Required signed artifact is missing: $LiteralPath.")
    }

    if ($PSBoundParameters.ContainsKey('SignToolPath')) {
        $signTool = Find-A3SignTool -ExplicitPath $SignToolPath
    }
    else {
        $signTool = Find-A3SignTool
    }

    $signatureProvider = {
        param([string]$Path)
        return Get-AuthenticodeSignature -LiteralPath $Path -ErrorAction Stop
    }
    $hashProvider = {
        param([IO.Stream]$ArtifactStream)
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try {
            return -join @($sha256.ComputeHash($ArtifactStream) | ForEach-Object { $_.ToString('X2') })
        }
        finally {
            $sha256.Dispose()
        }
    }
    $nativeProcessProvider = {
        param([string]$FilePath, [string[]]$Arguments)
        $output = @(& $FilePath @Arguments 2>&1)
        return [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output = $output
        }
    }

    return Get-A3SignatureRecordCore `
        -LiteralPath $resolvedPath `
        -SignToolPath $signTool `
        -SignatureProvider $signatureProvider `
        -HashProvider $hashProvider `
        -NativeProcessProvider $nativeProcessProvider
}

Export-ModuleMember -Function Assert-A3SignatureRecord, Assert-A3SignatureRecords, Find-A3SignTool, Get-A3SignatureRecord, New-A3SignatureError
