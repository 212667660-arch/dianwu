Set-StrictMode -Version Latest

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

function ConvertFrom-A3SignToolVerificationOutput {
    param(
        [Parameter(Mandatory)] [string]$OutputText,
        [string]$SafePath = '<artifact>'
    )

    $timestampMatch = [regex]::Match(
        $OutputText,
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
        $OutputText,
        '(?im)^\s*Hash of file \(sha256\):\s*(?<sha256>[A-Fa-f0-9]{64})\s*$'
    )
    if (-not $hashMatch.Success) {
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
    if ($digestAlgorithm.ToUpperInvariant() -cne 'SHA256') {
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
    if ($recordSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
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
        if ([string]::IsNullOrWhiteSpace($ExpectedSha256) -or $ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The expected SHA-256 value is invalid.')
        }
        if ($recordSha256.ToUpperInvariant() -cne $ExpectedSha256.ToUpperInvariant()) {
            throw (New-A3SignatureError 'A3_HASH_MISMATCH' "SHA-256 mismatch for $recordPath.")
        }
    }
}

function ConvertTo-A3CanonicalWindowsPath {
    param([Parameter(Mandatory)] [string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
    }
    try {
        return [IO.Path]::GetFullPath($Path).ToUpperInvariant()
    }
    catch {
        throw (New-A3SignatureError 'A3_HASH_MAP_MISMATCH' 'Signature record and expected-hash paths must match one-to-one.')
    }
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
            if ($expectedHash -isnot [string] -or $expectedHash -notmatch '^[A-Fa-f0-9]{64}$') {
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

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if ($null -eq $resolved -or -not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        return $null
    }

    $rootPath = [IO.Path]::GetFullPath($SdkBinRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $resolvedPath = [IO.Path]::GetFullPath($resolved.Path)
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

function Find-A3SignTool {
    [CmdletBinding()]
    param([Alias('SignToolPath')] [string]$ExplicitPath)

    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ([string]::IsNullOrWhiteSpace($programFilesX86)) {
        if ($PSBoundParameters.ContainsKey('ExplicitPath')) {
            throw (New-A3SignatureError 'A3_SIGNTOOL_NOT_APPROVED' 'The explicit signtool path is outside the approved Windows SDK location.')
        }
        throw (New-A3SignatureError 'A3_SIGNTOOL_NOT_FOUND' 'Windows SDK signtool.exe was not found in an approved location.')
    }

    $windowsKitBin = Join-Path $programFilesX86 'Windows Kits\10\bin'
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

function Get-A3SignatureRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$LiteralPath,
        [string]$SignToolPath
    )

    $resolved = Resolve-Path -LiteralPath $LiteralPath -ErrorAction SilentlyContinue
    if ($null -eq $resolved -or -not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        throw (New-A3SignatureError 'A3_ARTIFACT_MISSING' "Required signed artifact is missing: $LiteralPath.")
    }
    $resolvedPath = [IO.Path]::GetFullPath($resolved.Path)

    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $resolvedPath -ErrorAction Stop
    }
    catch {
        throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Authenticode verification failed for $resolvedPath.")
    }
    if ($null -eq $signature -or $signature.Status.ToString() -cne 'Valid' -or $null -eq $signature.SignerCertificate) {
        throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Invalid Authenticode signature for $resolvedPath.")
    }

    if ($PSBoundParameters.ContainsKey('SignToolPath')) {
        $signTool = Find-A3SignTool -ExplicitPath $SignToolPath
    }
    else {
        $signTool = Find-A3SignTool
    }
    $arguments = @('verify', '/pa', '/all', '/v', $resolvedPath)
    try {
        $signToolOutput = @(& $signTool @arguments 2>&1)
        $signToolExitCode = $LASTEXITCODE
    }
    catch {
        throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Windows signature verification failed for $resolvedPath.")
    }
    if ($signToolExitCode -ne 0) {
        throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Windows signature verification failed for $resolvedPath.")
    }

    $outputText = ($signToolOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
    if ($null -eq $signature.TimeStamperCertificate) {
        throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $resolvedPath.")
    }

    $parsedSignToolOutput = ConvertFrom-A3SignToolVerificationOutput -OutputText $outputText -SafePath $resolvedPath

    try {
        $sha256 = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToUpperInvariant()
    }
    catch {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The SHA-256 digest could not be read for $resolvedPath.")
    }

    $certificate = $signature.SignerCertificate
    $notBefore = ([DateTimeOffset]$certificate.NotBefore).ToUniversalTime()
    $notAfter = ([DateTimeOffset]$certificate.NotAfter).ToUniversalTime()
    return [pscustomobject][ordered]@{
        Path = $resolvedPath
        Status = $signature.Status.ToString()
        Subject = [string]$certificate.Subject
        FileDigestAlgorithm = $parsedSignToolOutput.FileDigestAlgorithm
        TimestampUtc = $parsedSignToolOutput.TimestampUtc
        CertificateNotBeforeUtc = ConvertTo-A3CanonicalUtcText -Value $notBefore
        CertificateNotAfterUtc = ConvertTo-A3CanonicalUtcText -Value $notAfter
        Sha256 = $sha256
    }
}

Export-ModuleMember -Function Assert-A3SignatureRecord, Assert-A3SignatureRecords, Find-A3SignTool, Get-A3SignatureRecord, New-A3SignatureError
