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

    $parsed = [DateTimeOffset]::MinValue
    $styles = [Globalization.DateTimeStyles]::AllowWhiteSpaces -bor
        [Globalization.DateTimeStyles]::AssumeUniversal -bor
        [Globalization.DateTimeStyles]::AdjustToUniversal
    if (-not [DateTimeOffset]::TryParse(
        $Value,
        [Globalization.CultureInfo]::InvariantCulture,
        $styles,
        [ref]$parsed
    )) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'The signature record contains an invalid date value.')
    }
    return $parsed.ToUniversalTime()
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

function Assert-A3SignatureRecords {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [object[]]$Records,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [System.Collections.IDictionary]$ExpectedSha256ByPath
    )

    $validated = [System.Collections.Generic.List[pscustomobject]]::new()
    foreach ($record in $Records) {
        if ($record -isnot [pscustomobject]) {
            throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' 'Every signature record must be a PSCustomObject.')
        }

        $recordPath = Get-A3RecordString -Record $record -Name 'Path'
        if ($null -ne $ExpectedSha256ByPath -and $ExpectedSha256ByPath.Contains($recordPath)) {
            Assert-A3SignatureRecord -Record $record -ExpectedPublisher $ExpectedPublisher -ExpectedSha256 ([string]$ExpectedSha256ByPath[$recordPath])
        }
        else {
            Assert-A3SignatureRecord -Record $record -ExpectedPublisher $ExpectedPublisher
        }
        $validated.Add($record)
    }

    return $validated.ToArray()
}

function Find-A3SignTool {
    [CmdletBinding()]
    param([Alias('SignToolPath')] [string]$ExplicitPath)

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $explicit = Resolve-Path -LiteralPath $ExplicitPath -ErrorAction SilentlyContinue
        if ($null -ne $explicit -and
            (Test-Path -LiteralPath $explicit.Path -PathType Leaf) -and
            ([IO.Path]::GetFileName($explicit.Path) -ieq 'signtool.exe')) {
            return [IO.Path]::GetFullPath($explicit.Path)
        }
    }

    $command = Get-Command 'signtool.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command -and -not [string]::IsNullOrWhiteSpace($command.Source) -and
        (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return [IO.Path]::GetFullPath($command.Source)
    }

    $programFilesX86 = ${env:ProgramFiles(x86)}
    if (-not [string]::IsNullOrWhiteSpace($programFilesX86)) {
        $windowsKitBin = Join-Path $programFilesX86 'Windows Kits\10\bin'
        if (Test-Path -LiteralPath $windowsKitBin -PathType Container) {
            $candidates = @(
                Get-ChildItem -Path (Join-Path $windowsKitBin '*\x64\signtool.exe') -File -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        $versionText = Split-Path -Leaf (Split-Path -Parent (Split-Path -Parent $_.FullName))
                        $version = $null
                        if ([version]::TryParse($versionText, [ref]$version)) {
                            [pscustomobject]@{
                                Path = $_.FullName
                                Version = $version
                            }
                        }
                    } |
                    Sort-Object -Property @{ Expression = 'Version'; Descending = $true }, @{ Expression = 'Path'; Descending = $true }
            )
            if ($candidates.Count -gt 0) {
                return [IO.Path]::GetFullPath($candidates[0].Path)
            }
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

    $signTool = Find-A3SignTool -ExplicitPath $SignToolPath
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

    $timestampMatch = [regex]::Match(
        $outputText,
        '(?im)^\s*The signature is timestamped(?:\s+(?:at|on))?\s*:\s*(?<timestamp>.+?)\s*$'
    )
    if (-not $timestampMatch.Success) {
        throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $resolvedPath.")
    }

    $timestamp = [DateTimeOffset]::MinValue
    $timestampStyles = [Globalization.DateTimeStyles]::AllowWhiteSpaces -bor
        [Globalization.DateTimeStyles]::AssumeUniversal -bor
        [Globalization.DateTimeStyles]::AdjustToUniversal
    $timestampText = $timestampMatch.Groups['timestamp'].Value
    $timestampParsed = [DateTimeOffset]::TryParse(
        $timestampText,
        [Globalization.CultureInfo]::GetCultureInfo('en-US'),
        $timestampStyles,
        [ref]$timestamp
    )
    if (-not $timestampParsed) {
        throw (New-A3SignatureError 'A3_SIGNATURE_RECORD_INVALID' "The trusted timestamp is invalid for $resolvedPath.")
    }

    if ($outputText -notmatch '(?im)^\s*Hash of file \(sha256\):\s*[A-Fa-f0-9]{64}\s*$') {
        throw (New-A3SignatureError 'A3_DIGEST_NOT_SHA256' "A SHA-256 file digest was not reported for $resolvedPath.")
    }

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
        FileDigestAlgorithm = 'SHA256'
        TimestampUtc = $timestamp.ToUniversalTime().ToString('o', [Globalization.CultureInfo]::InvariantCulture)
        CertificateNotBeforeUtc = $notBefore.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
        CertificateNotAfterUtc = $notAfter.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
        Sha256 = $sha256
    }
}

Export-ModuleMember -Function Assert-A3SignatureRecord, Assert-A3SignatureRecords, Find-A3SignTool, Get-A3SignatureRecord, New-A3SignatureError
