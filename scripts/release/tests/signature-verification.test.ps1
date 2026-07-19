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

function Get-TestStreamSha256 {
    param([Parameter(Mandatory)] [IO.Stream]$ArtifactStream)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return -join @($sha256.ComputeHash($ArtifactStream) | ForEach-Object { $_.ToString('X2') })
    }
    finally {
        $sha256.Dispose()
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

foreach ($nonCanonicalDigestAlgorithm in @('sha256', 'Sha256', 'sHa256')) {
    $nonCanonicalDigest = Copy-Record $valid
    $nonCanonicalDigest.FileDigestAlgorithm = $nonCanonicalDigestAlgorithm
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $nonCanonicalDigest -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_DIGEST_NOT_SHA256' | Out-Null
}

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

$multipleSignatureOutput = @"
Signature Index: 0 (Primary Signature)
Hash of file (sha1): $('A' * 40)
The signature is timestamped: Wed Jul 08 18:30:00 2026
Signature Index: 1
Hash of file (sha256): $signToolHash
The signature is timestamped: $signToolTimestampText
Successfully verified: C:\release\a3-app.exe
"@
Assert-ThrowsCode {
    & $module {
        param([string]$OutputText)
        ConvertFrom-A3SignToolVerificationOutput -OutputText $OutputText
    } $multipleSignatureOutput
} 'A3_MULTIPLE_SIGNATURES_UNSUPPORTED' | Out-Null

$singleIndexedSignatureOutput = @"
Signature Index: 0 (Primary Signature)
Hash of file (sha256): $signToolHash
The signature is timestamped: $signToolTimestampText
Successfully verified: C:\release\a3-app.exe
"@
$singleIndexedResult = & $module {
    param([string]$OutputText)
    ConvertFrom-A3SignToolVerificationOutput -OutputText $OutputText
} $singleIndexedSignatureOutput
Assert-Equal $singleIndexedResult.FileDigestAlgorithm 'SHA256' 'A single indexed SHA-256 signature block must remain supported.'
Assert-Equal $singleIndexedResult.ReportedSha256 $signToolHash 'A single indexed block must parse its own SHA-256 digest.'

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

$normalizedDuplicateRecordPath = Copy-Record $valid
$normalizedDuplicateRecordPath.Path = 'C:\release\folder\..\a3-app.exe'
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $normalizedDuplicateRecordPath) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $missingHashMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$duplicateCaseMap = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
$duplicateCaseMap.Add($valid.Path, ('A' * 64))
$duplicateCaseMap.Add($valid.Path.ToUpperInvariant(), ('A' * 64))
$duplicateCaseMap.Add($second.Path, ('B' * 64))
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $duplicateCaseMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$duplicateNormalizedMap = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
$duplicateNormalizedMap.Add($valid.Path, ('A' * 64))
$duplicateNormalizedMap.Add('C:\release\folder\..\a3-app.exe', ('A' * 64))
$duplicateNormalizedMap.Add($second.Path, ('B' * 64))
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($valid, $second) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $duplicateNormalizedMap
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

$canonicalDosPath = & $module {
    param([string]$Path)
    ConvertTo-A3CanonicalWindowsPath -Path $Path
} 'C:\path\file.exe'
$canonicalExtendedDosPath = & $module {
    param([string]$Path)
    ConvertTo-A3CanonicalWindowsPath -Path $Path
} '\\?\C:\path\file.exe'
Assert-Equal $canonicalExtendedDosPath $canonicalDosPath 'Extended DOS paths must canonicalize to the same batch key as normal DOS paths.'

$canonicalUncPath = & $module {
    param([string]$Path)
    ConvertTo-A3CanonicalWindowsPath -Path $Path
} '\\server\share\file.exe'
$canonicalExtendedUncPath = & $module {
    param([string]$Path)
    ConvertTo-A3CanonicalWindowsPath -Path $Path
} '\\?\UNC\server\share\file.exe'
Assert-Equal $canonicalExtendedUncPath $canonicalUncPath 'Extended UNC paths must canonicalize to the same batch key as normal UNC paths.'

$dosAliasMap = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
$dosAliasMap.Add('C:\path\file.exe', ('A' * 64))
$dosAliasMap.Add('\\?\C:\path\file.exe', ('A' * 64))
$dosAliasRecord = Copy-Record $valid
$dosAliasRecord.Path = 'C:\path\file.exe'
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($dosAliasRecord) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $dosAliasMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

$uncAliasMap = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
$uncAliasMap.Add('\\server\share\file.exe', ('A' * 64))
$uncAliasMap.Add('\\?\UNC\server\share\file.exe', ('A' * 64))
$uncAliasRecord = Copy-Record $valid
$uncAliasRecord.Path = '\\server\share\file.exe'
Assert-ThrowsCode {
    Assert-A3SignatureRecords -Records @($uncAliasRecord) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $uncAliasMap
} 'A3_HASH_MAP_MISMATCH' | Out-Null

foreach ($invalidProviderPath in @(
    'Registry::HKEY_CURRENT_USER\Software'
    'Variable:test'
    '\\.\PhysicalDrive0'
    '\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\file.exe'
)) {
    $pathError = Assert-ThrowsCode {
        & $module {
            param([string]$Path)
            ConvertTo-A3CanonicalWindowsPath -Path $Path
        } $invalidProviderPath
    } 'A3_PATH_INVALID'
    if ($pathError.Message -match 'ProviderInvocationException|GetUnresolvedProviderPath|at System') {
        throw 'Path normalization errors must not expose provider or stack details.'
    }
}

foreach ($hashLineEnding in @("`n", "`r`n")) {
    $hashWithLineEnding = ('A' * 64) + $hashLineEnding
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $valid -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 $hashWithLineEnding
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

    $recordWithHashLineEnding = Copy-Record $valid
    $recordWithHashLineEnding.Sha256 = $hashWithLineEnding
    Assert-ThrowsCode {
        Assert-A3SignatureRecord -Record $recordWithHashLineEnding -ExpectedPublisher 'CN=A3 Learning Project'
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null

    $mapWithHashLineEnding = @{ $valid.Path = $hashWithLineEnding }
    Assert-ThrowsCode {
        Assert-A3SignatureRecords -Records @($valid) -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256ByPath $mapWithHashLineEnding
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
}

Assert-ThrowsCode {
    Get-A3SignatureRecord -LiteralPath 'Registry::HKEY_CURRENT_USER\Software'
} 'A3_PATH_INVALID' | Out-Null

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
    $originalProgramFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)', 'Process')
    $originalPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
    try {
        $sdkRoot = Join-Path $temporaryDirectory 'Windows Kits\10'
        $olderSignTool = Join-Path $sdkRoot 'bin\10.0.22000.0\x64\signtool.exe'
        $newerSignTool = Join-Path $sdkRoot 'bin\10.0.26100.0\x64\signtool.exe'
        $pathHijackDirectory = Join-Path $temporaryDirectory 'path-hijack'
        $pathHijackSignTool = Join-Path $pathHijackDirectory 'signtool.exe'
        $outsideSignTool = Join-Path $temporaryDirectory 'outside-sdk\signtool.exe'
        foreach ($path in @($olderSignTool, $newerSignTool, $pathHijackSignTool, $outsideSignTool)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
            [System.IO.File]::WriteAllBytes($path, [byte[]](0))
        }

        $sdkRootProvider = {
            return $sdkRoot
        }.GetNewClosure()
        $maliciousProgramFilesX86 = Join-Path $temporaryDirectory 'malicious-program-files-x86'
        [Environment]::SetEnvironmentVariable('ProgramFiles(x86)', $maliciousProgramFilesX86, 'Process')
        [Environment]::SetEnvironmentVariable('Path', $pathHijackDirectory, 'Process')

        $automaticallyResolved = & $module {
            param($SdkRootProvider)
            Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
        } $sdkRootProvider
        Assert-Equal $automaticallyResolved ([IO.Path]::GetFullPath($newerSignTool)) 'SDK-root discovery must ignore PATH and select the newest approved SDK version.'

        Assert-ThrowsCode {
            & $module {
                param($SdkRootProvider, [string]$ExplicitPath)
                Find-A3SignToolCore -SdkRootProvider $SdkRootProvider -ExplicitPath $ExplicitPath
            } $sdkRootProvider $outsideSignTool
        } 'A3_SIGNTOOL_NOT_APPROVED' | Out-Null

        $explicitlyResolved = & $module {
            param($SdkRootProvider, [string]$ExplicitPath)
            Find-A3SignToolCore -SdkRootProvider $SdkRootProvider -ExplicitPath $ExplicitPath
        } $sdkRootProvider $olderSignTool
        Assert-Equal $explicitlyResolved ([IO.Path]::GetFullPath($olderSignTool)) 'SDK-root discovery must accept an explicit canonical SDK x64 path.'

        New-PSDrive -Name 'A3SDK' -PSProvider FileSystem -Root $sdkRoot | Out-Null
        try {
            $customPsDriveRootProvider = { return 'A3SDK:\' }
            Assert-ThrowsCode {
                & $module {
                    param($SdkRootProvider)
                    Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
                } $customPsDriveRootProvider
            } 'A3_WINDOWS_SDK_ROOT_INVALID' | Out-Null
        }
        finally {
            Remove-PSDrive -Name 'A3SDK' -Force -ErrorAction SilentlyContinue
        }

        foreach ($nonDosSdkRoot in @(
            "FileSystem::$sdkRoot"
            "\\?\$sdkRoot"
            '\\server\share\Windows Kits\10'
            '\\.\C:\Windows Kits\10'
            'relative-sdk-root'
        )) {
            $nonDosSdkRootProvider = {
                return $nonDosSdkRoot
            }.GetNewClosure()
            Assert-ThrowsCode {
                & $module {
                    param($SdkRootProvider)
                    Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
                } $nonDosSdkRootProvider
            } 'A3_WINDOWS_SDK_ROOT_INVALID' | Out-Null
        }

        foreach ($invalidSdkRootProvider in @(
            { return $null }
            { return 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE' }
            { throw 'registry read failed' }
        )) {
            Assert-ThrowsCode {
                & $module {
                    param($SdkRootProvider)
                    Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
                } $invalidSdkRootProvider
            } 'A3_WINDOWS_SDK_ROOT_INVALID' | Out-Null
        }

        $realReparseRoot = Join-Path $temporaryDirectory 'real-sdk-root'
        $reparseSdkRoot = Join-Path $temporaryDirectory 'reparse-sdk-root'
        New-Item -ItemType Directory -Path $realReparseRoot | Out-Null
        New-Item -ItemType Junction -Path $reparseSdkRoot -Target $realReparseRoot | Out-Null
        $reparseSdkRootProvider = {
            return $reparseSdkRoot
        }.GetNewClosure()
        Assert-ThrowsCode {
            & $module {
                param($SdkRootProvider)
                Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
            } $reparseSdkRootProvider
        } 'A3_WINDOWS_SDK_ROOT_INVALID' | Out-Null

        $realSdkParent = Join-Path $temporaryDirectory 'real-sdk-parent'
        $realNestedSdkRoot = Join-Path $realSdkParent 'sdk-root'
        $reparseSdkParent = Join-Path $temporaryDirectory 'reparse-sdk-parent'
        New-Item -ItemType Directory -Path $realNestedSdkRoot -Force | Out-Null
        New-Item -ItemType Junction -Path $reparseSdkParent -Target $realSdkParent | Out-Null
        $nestedSdkRootThroughReparseProvider = {
            return (Join-Path $reparseSdkParent 'sdk-root')
        }.GetNewClosure()
        Assert-ThrowsCode {
            & $module {
                param($SdkRootProvider)
                Find-A3SignToolCore -SdkRootProvider $SdkRootProvider
            } $nestedSdkRootThroughReparseProvider
        } 'A3_WINDOWS_SDK_ROOT_INVALID' | Out-Null
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

$lockTestDirectory = Join-Path ([IO.Path]::GetTempPath()) ("a3-signature-lock-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $lockTestDirectory | Out-Null
try {
    $lockTestPath = Join-Path $lockTestDirectory 'artifact.exe'
    $renamedLockTestPath = Join-Path $lockTestDirectory 'artifact-renamed.exe'
    $lockedBytes = [byte[]](1..32)
    $replacementBytes = [byte[]](33..64)
    [IO.File]::WriteAllBytes($lockTestPath, $lockedBytes)
    $lockedSha256 = (Get-FileHash -LiteralPath $lockTestPath -Algorithm SHA256).Hash
    $lockMutationState = [pscustomobject]@{
        OverwriteDenied = $false
        RenameDenied = $false
        DeleteDenied = $false
    }
    $lockValidSignature = [pscustomobject]@{
        Status = 'Valid'
        SignerCertificate = [pscustomobject]@{
            Subject = 'CN=A3 Learning Project'
            NotBefore = [datetime]'2026-07-01T00:00:00Z'
            NotAfter = [datetime]'2027-07-01T00:00:00Z'
        }
        TimeStamperCertificate = [pscustomobject]@{
            Subject = 'CN=A3 Test Timestamp Authority'
        }
    }
    $lockSignatureProvider = {
        param([string]$LiteralPath)
        return $lockValidSignature
    }.GetNewClosure()
    $pathHashProvider = {
        param([IO.Stream]$ArtifactStream)
        return Get-TestStreamSha256 -ArtifactStream $ArtifactStream
    }
    $mutatingNativeProcessProvider = {
        param([string]$FilePath, [string[]]$Arguments)
        try {
            [IO.File]::WriteAllBytes($lockTestPath, $replacementBytes)
            [IO.File]::WriteAllBytes($lockTestPath, $lockedBytes)
        }
        catch {
            $lockMutationState.OverwriteDenied = $true
        }
        try {
            [IO.File]::Move($lockTestPath, $renamedLockTestPath)
            [IO.File]::Move($renamedLockTestPath, $lockTestPath)
        }
        catch {
            $lockMutationState.RenameDenied = $true
        }
        try {
            [IO.File]::Delete($lockTestPath)
            [IO.File]::WriteAllBytes($lockTestPath, $lockedBytes)
        }
        catch {
            $lockMutationState.DeleteDenied = $true
        }
        return [pscustomobject]@{
            ExitCode = 0
            Output = @(
                "Hash of file (sha256): $('D' * 64)"
                "The signature is timestamped: $signToolTimestampText"
                "Successfully verified: $lockTestPath"
            )
        }
    }.GetNewClosure()

    $lockedRecord = & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $lockTestPath 'C:\approved-sdk\signtool.exe' $lockSignatureProvider $pathHashProvider $mutatingNativeProcessProvider
    if (-not $lockMutationState.OverwriteDenied -or
        -not $lockMutationState.RenameDenied -or
        -not $lockMutationState.DeleteDenied) {
        throw 'The verification window must deny overwrite, rename, and delete mutations.'
    }
    Assert-Equal $lockedRecord.Sha256 $lockedSha256 'The locked verification record must bind to the bytes held by the open stream.'
}
finally {
    Remove-Item -LiteralPath $lockTestDirectory -Recurse -Force -ErrorAction SilentlyContinue
}

$junctionTestDirectory = Join-Path ([IO.Path]::GetTempPath()) ("a3-signature-junction-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $junctionTestDirectory | Out-Null
try {
    $junctionTargetA = Join-Path $junctionTestDirectory 'target-a'
    $junctionTargetB = Join-Path $junctionTestDirectory 'target-b'
    $junctionPath = Join-Path $junctionTestDirectory 'current'
    New-Item -ItemType Directory -Path $junctionTargetA | Out-Null
    New-Item -ItemType Directory -Path $junctionTargetB | Out-Null
    $junctionBytesA = [byte[]](1..32)
    $junctionBytesB = [byte[]](33..64)
    $junctionTargetPathA = Join-Path $junctionTargetA 'artifact.exe'
    $junctionTargetPathB = Join-Path $junctionTargetB 'artifact.exe'
    [IO.File]::WriteAllBytes($junctionTargetPathA, $junctionBytesA)
    [IO.File]::WriteAllBytes($junctionTargetPathB, $junctionBytesB)
    New-Item -ItemType Junction -Path $junctionPath -Target $junctionTargetA | Out-Null
    $junctionArtifactPath = Join-Path $junctionPath 'artifact.exe'
    $junctionHashA = (Get-FileHash -LiteralPath $junctionTargetPathA -Algorithm SHA256).Hash
    $junctionState = [pscustomobject]@{
        Rebound = $false
        SignaturePath = $null
        NativePath = $null
        NativeObservedHash = $null
    }
    $junctionSignature = [pscustomobject]@{
        Status = 'Valid'
        SignerCertificate = [pscustomobject]@{
            Subject = 'CN=A3 Learning Project'
            NotBefore = [datetime]'2026-07-01T00:00:00Z'
            NotAfter = [datetime]'2027-07-01T00:00:00Z'
        }
        TimeStamperCertificate = [pscustomobject]@{
            Subject = 'CN=A3 Test Timestamp Authority'
        }
    }
    $junctionSignatureProvider = {
        param([string]$LiteralPath)
        $junctionState.SignaturePath = $LiteralPath
        return $junctionSignature
    }.GetNewClosure()
    $junctionHashProvider = {
        param([IO.Stream]$ArtifactStream)
        return Get-TestStreamSha256 -ArtifactStream $ArtifactStream
    }
    $junctionNativeProvider = {
        param([string]$FilePath, [string[]]$Arguments)
        [IO.Directory]::Delete($junctionPath)
        New-Item -ItemType Junction -Path $junctionPath -Target $junctionTargetB | Out-Null
        $junctionState.Rebound = $true
        $junctionState.NativePath = $Arguments[-1]
        $junctionState.NativeObservedHash = (Get-FileHash -LiteralPath $Arguments[-1] -Algorithm SHA256).Hash
        return [pscustomobject]@{
            ExitCode = 0
            Output = @(
                "Hash of file (sha256): $('D' * 64)"
                "The signature is timestamped: $signToolTimestampText"
                "Successfully verified: $($Arguments[-1])"
            )
        }
    }.GetNewClosure()

    Assert-ThrowsCode {
        & $module {
            param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
            Get-A3SignatureRecordCore `
                -LiteralPath $LiteralPath `
                -SignToolPath $SignToolPath `
                -SignatureProvider $SignatureProvider `
                -HashProvider $HashProvider `
                -NativeProcessProvider $NativeProcessProvider
        } $junctionArtifactPath 'C:\approved-sdk\signtool.exe' $junctionSignatureProvider $junctionHashProvider $junctionNativeProvider
    } 'A3_ARTIFACT_IDENTITY_CHANGED' | Out-Null
    if (-not $junctionState.Rebound) {
        throw 'The junction reproduction must rebind after the artifact handle is opened.'
    }
    if ($junctionState.SignaturePath -eq $junctionArtifactPath -or $junctionState.NativePath -eq $junctionArtifactPath) {
        throw 'External signature verification must use the locked handle final path, not the rebindable logical path.'
    }
    Assert-Equal $junctionState.NativeObservedHash $junctionHashA 'The native verifier path must remain bound to target A after the junction points to target B.'
}
finally {
    Remove-Item -LiteralPath $junctionTestDirectory -Recurse -Force -ErrorAction SilentlyContinue
}

$coreTestDirectory = Join-Path ([IO.Path]::GetTempPath()) ("a3-signature-core-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $coreTestDirectory | Out-Null
$corePath = Join-Path $coreTestDirectory 'a3-app.exe'
[IO.File]::WriteAllBytes($corePath, [byte[]](65..96))
$rawHashA = ('A' * 64)
$rawHashB = ('B' * 64)
$authenticodeDigest = ('D' * 64)
$validSignature = [pscustomobject]@{
    Status = 'Valid'
    SignerCertificate = [pscustomobject]@{
        Subject = 'CN=A3 Learning Project'
        NotBefore = [datetime]'2026-07-01T00:00:00Z'
        NotAfter = [datetime]'2027-07-01T00:00:00Z'
    }
    TimeStamperCertificate = [pscustomobject]@{
        Subject = 'CN=A3 Test Timestamp Authority'
    }
}
$signatureProvider = {
    param([string]$LiteralPath)
    return $validSignature
}.GetNewClosure()
$nativeProcessProvider = {
    param([string]$FilePath, [string[]]$Arguments)
    return [pscustomobject]@{
        ExitCode = 0
        Output = @(
            "Hash of file (sha256): $authenticodeDigest"
            "The signature is timestamped: $signToolTimestampText"
            "Successfully verified: $corePath"
        )
    }
}.GetNewClosure()

$changingHashes = [Collections.Generic.Queue[string]]::new()
$changingHashes.Enqueue($rawHashA)
$changingHashes.Enqueue($rawHashB)
$changingHashProvider = {
    param([IO.Stream]$ArtifactStream)
    return $changingHashes.Dequeue()
}.GetNewClosure()
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $changingHashProvider $nativeProcessProvider
} 'A3_HASH_MISMATCH' | Out-Null

$stableHashes = [Collections.Generic.Queue[string]]::new()
$stableHashes.Enqueue($rawHashA)
$stableHashes.Enqueue($rawHashA)
$stableHashProvider = {
    param([IO.Stream]$ArtifactStream)
    return $stableHashes.Dequeue()
}.GetNewClosure()
$stableRecord = & $module {
    param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
    Get-A3SignatureRecordCore `
        -LiteralPath $LiteralPath `
        -SignToolPath $SignToolPath `
        -SignatureProvider $SignatureProvider `
        -HashProvider $HashProvider `
        -NativeProcessProvider $NativeProcessProvider
} $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $stableHashProvider $nativeProcessProvider
Assert-Equal $stableRecord.Status 'Valid' 'The injectable core must preserve the valid Authenticode status.'
Assert-Equal $stableRecord.FileDigestAlgorithm 'SHA256' 'The injectable core must require signtool SHA-256 output.'
Assert-Equal $stableRecord.Sha256 $rawHashA 'The safe record must bind to the stable raw file hash.'
if ($null -ne $stableRecord.PSObject.Properties['ReportedSha256']) {
    throw 'The signtool Authenticode digest must remain internal to verification.'
}

$constantHashProvider = {
    param([IO.Stream]$ArtifactStream)
    return $rawHashA
}.GetNewClosure()

$signatureWithoutStatus = [pscustomobject]@{
    SignerCertificate = $validSignature.SignerCertificate
    TimeStamperCertificate = $validSignature.TimeStamperCertificate
}
$signatureWithoutStatusProvider = {
    param([string]$LiteralPath)
    return $signatureWithoutStatus
}.GetNewClosure()
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureWithoutStatusProvider $constantHashProvider $nativeProcessProvider
} 'A3_SIGNATURE_INVALID' | Out-Null

$signatureWithoutSigner = [pscustomobject]@{
    Status = 'Valid'
    TimeStamperCertificate = $validSignature.TimeStamperCertificate
}
$signatureWithoutSignerProvider = {
    param([string]$LiteralPath)
    return $signatureWithoutSigner
}.GetNewClosure()
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureWithoutSignerProvider $constantHashProvider $nativeProcessProvider
} 'A3_SIGNATURE_INVALID' | Out-Null

foreach ($missingCertificateDate in @('NotBefore', 'NotAfter')) {
    $incompleteCertificate = [ordered]@{
        Subject = 'CN=A3 Learning Project'
        NotBefore = [datetime]'2026-07-01T00:00:00Z'
        NotAfter = [datetime]'2027-07-01T00:00:00Z'
    }
    $incompleteCertificate.Remove($missingCertificateDate)
    $signatureWithoutDate = [pscustomobject]@{
        Status = 'Valid'
        SignerCertificate = [pscustomobject]$incompleteCertificate
        TimeStamperCertificate = $validSignature.TimeStamperCertificate
    }
    $signatureWithoutDateProvider = {
        param([string]$LiteralPath)
        return $signatureWithoutDate
    }.GetNewClosure()
    Assert-ThrowsCode {
        & $module {
            param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
            Get-A3SignatureRecordCore `
                -LiteralPath $LiteralPath `
                -SignToolPath $SignToolPath `
                -SignatureProvider $SignatureProvider `
                -HashProvider $HashProvider `
                -NativeProcessProvider $NativeProcessProvider
        } $corePath 'C:\approved-sdk\signtool.exe' $signatureWithoutDateProvider $constantHashProvider $nativeProcessProvider
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
}

$nonzeroNativeProcessProvider = {
    param([string]$FilePath, [string[]]$Arguments)
    return [pscustomobject]@{
        ExitCode = 1
        Output = @('SignTool Error: verification failed.')
    }
}
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $constantHashProvider $nonzeroNativeProcessProvider
} 'A3_SIGNATURE_INVALID' | Out-Null

$missingSha256MarkerProvider = {
    param([string]$FilePath, [string[]]$Arguments)
    return [pscustomobject]@{
        ExitCode = 0
        Output = @(
            "The signature is timestamped: $signToolTimestampText"
            "Successfully verified: $corePath"
        )
    }
}.GetNewClosure()
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $constantHashProvider $missingSha256MarkerProvider
} 'A3_DIGEST_NOT_SHA256' | Out-Null

$missingTimestampLineProvider = {
    param([string]$FilePath, [string[]]$Arguments)
    return [pscustomobject]@{
        ExitCode = 0
        Output = @(
            "Hash of file (sha256): $authenticodeDigest"
            "Successfully verified: $corePath"
        )
    }
}.GetNewClosure()
Assert-ThrowsCode {
    & $module {
        param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
        Get-A3SignatureRecordCore `
            -LiteralPath $LiteralPath `
            -SignToolPath $SignToolPath `
            -SignatureProvider $SignatureProvider `
            -HashProvider $HashProvider `
            -NativeProcessProvider $NativeProcessProvider
    } $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $constantHashProvider $missingTimestampLineProvider
} 'A3_TIMESTAMP_MISSING' | Out-Null

foreach ($hashLineEnding in @("`n", "`r`n")) {
    $providerHashWithLineEnding = $rawHashA + $hashLineEnding
    $invalidHashProvider = {
        param([IO.Stream]$ArtifactStream)
        return $providerHashWithLineEnding
    }.GetNewClosure()
    Assert-ThrowsCode {
        & $module {
            param($LiteralPath, $SignToolPath, $SignatureProvider, $HashProvider, $NativeProcessProvider)
            Get-A3SignatureRecordCore `
                -LiteralPath $LiteralPath `
                -SignToolPath $SignToolPath `
                -SignatureProvider $SignatureProvider `
                -HashProvider $HashProvider `
                -NativeProcessProvider $NativeProcessProvider
        } $corePath 'C:\approved-sdk\signtool.exe' $signatureProvider $invalidHashProvider $nativeProcessProvider
    } 'A3_SIGNATURE_RECORD_INVALID' | Out-Null
}

Remove-Item -LiteralPath $coreTestDirectory -Recurse -Force

Write-Host 'signature-verification.test.ps1 passed'
