$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..\A3.SignatureVerification.psm1'
Import-Module $modulePath -Force

function Assert-Equal {
    param(
        [Parameter(Mandatory)] $Actual,
        [Parameter(Mandatory)] $Expected,
        [Parameter(Mandatory)] [string]$Message
    )

    if ($Actual -ne $Expected) {
        throw "$Message Expected '$Expected', received '$Actual'."
    }
}

function Assert-ThrowsCode {
    param(
        [Parameter(Mandatory)] [scriptblock]$Action,
        [Parameter(Mandatory)] [string]$Code
    )

    try {
        & $Action
        throw "Expected error code $Code."
    }
    catch {
        if ($_.Exception.Data['A3Code'] -ne $Code) {
            throw
        }
        return $_.Exception
    }
}

function Copy-Record {
    param([Parameter(Mandatory)] [pscustomobject]$Source)

    $copy = [ordered]@{}
    foreach ($property in $Source.PSObject.Properties) {
        $copy[$property.Name] = $property.Value
    }
    return [pscustomobject]$copy
}

function New-TestRecord {
    return [pscustomobject]@{
        Path = 'C:\release\a3-app.exe'
        Status = 'Valid'
        Subject = 'CN=A3 Learning Project'
        FileDigestAlgorithm = 'SHA256'
        TimestampUtc = '2026-07-18T08:00:00Z'
        CertificateNotBeforeUtc = '2026-07-01T00:00:00Z'
        CertificateNotAfterUtc = '2027-07-01T00:00:00Z'
        Sha256 = ('A' * 64)
    }
}

$expectedExports = @(
    'Assert-A3SignatureRecord'
    'Assert-A3SignatureRecords'
    'Find-A3SignTool'
    'Get-A3SignatureRecord'
    'New-A3SignatureError'
)
$module = Get-Module | Where-Object { $_.Path -eq (Resolve-Path -LiteralPath $modulePath).Path }
$actualExports = @($module.ExportedFunctions.Keys | Sort-Object)
Assert-Equal ($actualExports -join ',') (($expectedExports | Sort-Object) -join ',') 'Module exports must be exact.'

$constructedError = New-A3SignatureError -Code 'A3_TEST_CODE' -Message 'safe message'
Assert-Equal $constructedError.GetType().FullName 'System.InvalidOperationException' 'New-A3SignatureError must return InvalidOperationException.'
Assert-Equal $constructedError.Data['A3Code'] 'A3_TEST_CODE' 'New-A3SignatureError must attach A3Code.'

Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record $null -ExpectedPublisher 'CN=A3 Learning Project'
} 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

$valid = New-TestRecord
Assert-A3SignatureRecord -Record $valid -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 ('A' * 64)

$lowercaseDigest = Copy-Record $valid
$lowercaseDigest.FileDigestAlgorithm = 'sha256'
$lowercaseDigest.Sha256 = ('a' * 64)
Assert-A3SignatureRecord -Record $lowercaseDigest -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 ('A' * 64)

$fractionalUtc = Copy-Record $valid
$fractionalUtc.TimestampUtc = '2026-07-18T08:00:00.1234567Z'
$fractionalUtc.CertificateNotBeforeUtc = '2026-07-01T00:00:00.1Z'
$fractionalUtc.CertificateNotAfterUtc = '2027-07-01T00:00:00.0000001Z'
Assert-A3SignatureRecord -Record $fractionalUtc -ExpectedPublisher 'CN=A3 Learning Project'

foreach ($propertyName in @('TimestampUtc', 'CertificateNotBeforeUtc', 'CertificateNotAfterUtc')) {
    foreach ($looseDateValue in @(
        '07/18/2026 08:00'
        '2026-07-18'
        '2026-07-18T08:00:00+08:00'
    )) {
        $record = Copy-Record $valid
        $record.($propertyName) = $looseDateValue
        Assert-ThrowsCode {
            Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
        } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
    }
}

$signToolTimestampText = 'Thu Jul 09 19:44:12 2026'
$signToolHash = ('B' * 64)
$localTimestamp = [datetime]::ParseExact(
    $signToolTimestampText,
    'ddd MMM dd HH:mm:ss yyyy',
    [Globalization.CultureInfo]::GetCultureInfo('en-US'),
    [Globalization.DateTimeStyles]::None
)
$expectedTimestampUtc = [TimeZoneInfo]::ConvertTimeToUtc(
    [datetime]::SpecifyKind($localTimestamp, [DateTimeKind]::Unspecified),
    [TimeZoneInfo]::Local
).ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", [Globalization.CultureInfo]::InvariantCulture)

foreach ($timestampLine in @(
    "The signature is timestamped: $signToolTimestampText"
    "The signature is timestamped at: $signToolTimestampText"
    "The signature is timestamped on: $signToolTimestampText"
)) {
    $signToolOutput = @"
Hash of file (sha256): $signToolHash
$timestampLine
Successfully verified: C:\release\a3-app.exe
"@
    $parsedSignToolOutput = & $module {
        param([string]$OutputText)
        ConvertFrom-A3SignToolVerificationOutput -OutputText $OutputText
    } $signToolOutput
    Assert-Equal $parsedSignToolOutput.TimestampUtc $expectedTimestampUtc 'Signtool timestamps must be interpreted as local time and serialized as canonical UTC.'
    Assert-Equal $parsedSignToolOutput.FileDigestAlgorithm 'SHA256' 'Signtool output must contain the SHA-256 marker.'
    Assert-Equal $parsedSignToolOutput.ReportedSha256 $signToolHash 'Signtool output must parse the reported SHA-256 value.'
}

foreach ($status in @('NotSigned', 'HashMismatch')) {
    $record = Copy-Record $valid
    $record.Status = $status
    Assert-ThrowsCode { Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project' } 'A3_SIGNATURE_INVALID' | Out-Null
}

Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record $valid -ExpectedPublisher 'CN=Wrong Publisher'
} 'A3_PUBLISHER_MISMATCH' | Out-Null

foreach ($subject in @('CN=Other Publisher', 'cn=a3 learning project')) {
    $record = Copy-Record $valid
    $record.Subject = $subject
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_PUBLISHER_MISMATCH' | Out-Null
}

foreach ($timestampValue in @($null, '')) {
    $record = Copy-Record $valid
    $record.TimestampUtc = $timestampValue
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_TIMESTAMP_MISSING' | Out-Null
}

$sha1 = Copy-Record $valid
$sha1.FileDigestAlgorithm = 'SHA1'
Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record $sha1 -ExpectedPublisher 'CN=A3 Learning Project'
} 'A3_DIGEST_NOT_SHA256' | Out-Null

$wrongHash = Copy-Record $valid
$wrongHash.Sha256 = ('B' * 64)
Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record $wrongHash -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 ('A' * 64)
} 'A3_HASH_MISMATCH' | Out-Null

foreach ($timestampValue in @('2026-06-30T23:59:59Z', '2027-07-01T00:00:01Z')) {
    $record = Copy-Record $valid
    $record.TimestampUtc = $timestampValue
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_TIMESTAMP_OUTSIDE_CERTIFICATE' | Out-Null
}

foreach ($timestampValue in @('2026-07-01T00:00:00Z', '2027-07-01T00:00:00Z')) {
    $record = Copy-Record $valid
    $record.TimestampUtc = $timestampValue
    Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
}

foreach ($invalidDateCase in @(
    @{ Property = 'TimestampUtc'; Value = 'not-a-timestamp' }
    @{ Property = 'CertificateNotBeforeUtc'; Value = 'not-a-date' }
    @{ Property = 'CertificateNotAfterUtc'; Value = '2027-99-99' }
)) {
    $record = Copy-Record $valid
    $record.($invalidDateCase.Property) = $invalidDateCase.Value
    $capturedException = Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_SIGNATURE_RECORD_INVALID'
    if ($capturedException.Message -match 'DateTime|Parse|FormatException|at System') {
        throw 'Invalid date errors must not expose parser details.'
    }
}

foreach ($invalidHash in @('ABC', ('G' * 64), ('A' * 63))) {
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $valid -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 $invalidHash
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
}

foreach ($invalidRecordHash in @('', 'ABC', ('G' * 64))) {
    $record = Copy-Record $valid
    $record.Sha256 = $invalidRecordHash
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
}

$missingSubject = [ordered]@{}
foreach ($property in $valid.PSObject.Properties) {
    if ($property.Name -ne 'Subject') {
        $missingSubject[$property.Name] = $property.Value
    }
}
Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record ([pscustomobject]$missingSubject) -ExpectedPublisher 'CN=A3 Learning Project'
} 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

$nonScalarSubject = Copy-Record $valid
$nonScalarSubject.Subject = @('CN=A3 Learning Project', 'CN=Other')
Assert-ThrowsCode {
    Assert-A3SignatureRecord -Record $nonScalarSubject -ExpectedPublisher 'CN=A3 Learning Project'
} 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

$second = Copy-Record $valid
$second.Path = 'C:\release\[literal]\second.exe'
$second.Sha256 = ('B' * 64)
$hashes = @{
    $valid.Path = ('A' * 64)
    $second.Path = ('B' * 64)
}
$validated = @(Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $hashes)
Assert-Equal $validated.Count 2 'Assert-A3SignatureRecords must preserve record count.'
Assert-Equal $validated[0].Path $valid.Path 'Assert-A3SignatureRecords must preserve first record.'
Assert-Equal $validated[1].Path $second.Path 'Assert-A3SignatureRecords must preserve second record.'

$missingHashMap = @{ $valid.Path = ('A' * 64) }
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $missingHashMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$extraHashMap = @{
    $valid.Path = ('A' * 64)
    $second.Path = ('B' * 64)
    'C:\release\extra.exe' = ('C' * 64)
}
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $extraHashMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$duplicateRecordPath = Copy-Record $valid
$duplicateRecordPath.Path = $valid.Path.ToUpperInvariant()
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $duplicateRecordPath) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $missingHashMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$duplicateCaseMap = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
$duplicateCaseMap.Add($valid.Path, ('A' * 64))
$duplicateCaseMap.Add($valid.Path.ToUpperInvariant(), ('A' * 64))
$duplicateCaseMap.Add($second.Path, ('B' * 64))
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $duplicateCaseMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$invalidHashMap = @{
    $valid.Path = 'not-a-sha256'
    $second.Path = ('B' * 64)
}
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $invalidHashMap
} 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

$relativeRecord = Copy-Record $valid
$relativeRecord.Path = '.\release\canonical.exe'
$relativeRecord.Sha256 = ('C' * 64)
$normalizedMapPath = [IO.Path]::GetFullPath((Join-Path (Get-Location).Path 'release\folder\..\canonical.exe')).ToUpperInvariant()
$normalizedMismatchMap = @{ $normalizedMapPath = ('D' * 64) }
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($relativeRecord) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $normalizedMismatchMap
} 'A3_HASH_MISMATCH' | Out-Null

$normalizedSuccessMap = @{ $normalizedMapPath = ('C' * 64) }
$normalizedRecords = @(Assert-A3SignatureRecords -Records @($relativeRecord) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $normalizedSuccessMap)
Assert-Equal $normalizedRecords.Count 1 'Canonical hash-map matching must preserve the record.'
Assert-Equal $normalizedRecords[0].Path $relativeRecord.Path 'Canonical hash-map matching must preserve the original path text.'

$badSecond = Copy-Record $second
$badSecond.Subject = 'CN=Other Publisher'
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $badSecond) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $hashes
} 'A3_PUBLISHER_MISMATCH' | Out-Null

$secretMarker = 'A3-SENSITIVE-ENVIRONMENT-VALUE'
$privateMarker = 'A3-PRIVATE-CERTIFICATE-MATERIAL'
$env:A3_TEST_SENSITIVE_VALUE = $secretMarker
try {
    $unsafeRecord = Copy-Record $valid
    $unsafeRecord.Status = 'NotSigned'
    $unsafeRecord | Add-Member -NotePropertyName PrivateKeyMaterial -NotePropertyValue $privateMarker
    $capturedException = Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $unsafeRecord -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_SIGNATURE_INVALID'
    if ($capturedException.Message.Contains($secretMarker) -or $capturedException.Message.Contains($privateMarker)) {
        throw 'Validation messages must not expose environment values or private certificate material.'
    }
}
finally {
    Remove-Item Env:A3_TEST_SENSITIVE_VALUE -ErrorAction SilentlyContinue
}

$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("a3-signtool-test-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
try {
    $unsignedFile = Join-Path $temporaryDirectory 'unsigned.ps1'
    [System.IO.File]::WriteAllText($unsignedFile, "Write-Output 'unsigned'", [Text.UTF8Encoding]::new($false))
    $originalProgramFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)', 'Process')
    $originalPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
    try {
        $programFilesX86 = Join-Path $temporaryDirectory 'Program Files (x86)'
        $olderSignTool = Join-Path $programFilesX86 'Windows Kits\10\bin\10.0.22000.0\x64\signtool.exe'
        $newerSignTool = Join-Path $programFilesX86 'Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
        $pathHijackDirectory = Join-Path $temporaryDirectory 'path-hijack'
        $pathHijackSignTool = Join-Path $pathHijackDirectory 'signtool.exe'
        $outsideSignTool = Join-Path $temporaryDirectory 'outside-sdk\signtool.exe'
        foreach ($path in @($olderSignTool, $newerSignTool, $pathHijackSignTool, $outsideSignTool)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
            [System.IO.File]::WriteAllBytes($path, [byte[]](0))
        }

        [Environment]::SetEnvironmentVariable('ProgramFiles(x86)', $programFilesX86, 'Process')
        [Environment]::SetEnvironmentVariable('Path', $pathHijackDirectory, 'Process')
        Assert-ThrowsCode {
            Get-A3SignatureRecord -LiteralPath $unsignedFile
        } 'A3_SIGNATURE_INVALID' | Out-Null

        $automaticallyResolved = Find-A3SignTool
        Assert-Equal $automaticallyResolved ([IO.Path]::GetFullPath($newerSignTool)) 'Find-A3SignTool must ignore PATH and select the newest approved SDK version.'

        Assert-ThrowsCode {
            Find-A3SignTool -ExplicitPath $outsideSignTool
        } 'A3_SIGNTOOL_NOT_APPROVED' | Out-Null

        $explicitlyResolved = Find-A3SignTool -ExplicitPath $olderSignTool
        Assert-Equal $explicitlyResolved ([IO.Path]::GetFullPath($olderSignTool)) 'Find-A3SignTool must accept an explicit canonical SDK x64 path.'
    }
    finally {
        [Environment]::SetEnvironmentVariable('ProgramFiles(x86)', $originalProgramFilesX86, 'Process')
        [Environment]::SetEnvironmentVariable('Path', $originalPath, 'Process')
    }
}
finally {
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
}

Assert-ThrowsCode {
    Get-A3SignatureRecord -LiteralPath 'C:\definitely-missing\a3-app.exe'
} 'A3_ARTIFACT_MISSING' | Out-Null

Write-Host 'signature-verification.test.ps1 passed'
