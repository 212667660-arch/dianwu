$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$modulePath = Join-Path $PSScriptRoot '..\A3.SignatureVerification.psm1'
Import-Module $modulePath -Force

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

function New-ValidRecord {
    param([string]$LiteralPath, [string]$Subject = 'CN=A3 Learning Project')
    return [pscustomobject][ordered]@{
        Path = $LiteralPath
        Status = 'Valid'
        Subject = $Subject
        FileDigestAlgorithm = 'SHA256'
        TimestampUtc = '2026-07-18T08:00:00.0000000Z'
        CertificateNotBeforeUtc = '2026-07-01T00:00:00.0000000Z'
        CertificateNotAfterUtc = '2027-07-01T00:00:00.0000000Z'
        Sha256 = (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash
    }
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("a3-release-artifacts-{0}" -f [guid]::NewGuid())
$releaseDir = Join-Path $testRoot '发布目录'
$installDir = Join-Path $testRoot 'installed'
$manifestPath = Join-Path $releaseDir 'a3-windows-release-manifest.json'

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $installDir -Force | Out-Null

try {
    $expected = @(
        @{ Scope = 'package'; RelativePath = 'win-unpacked/智学协作台.exe'; Path = Join-Path $releaseDir 'win-unpacked\智学协作台.exe' },
        @{ Scope = 'package'; RelativePath = 'win-unpacked/resources/backend/api.exe'; Path = Join-Path $releaseDir 'win-unpacked\resources\backend\api.exe' },
        @{ Scope = 'package'; RelativePath = 'win-unpacked/resources/elevate.exe'; Path = Join-Path $releaseDir 'win-unpacked\resources\elevate.exe' },
        @{ Scope = 'release'; RelativePath = '智学协作台 Setup 1.0.0.exe'; Path = Join-Path $releaseDir '智学协作台 Setup 1.0.0.exe' },
        @{ Scope = 'installed'; RelativePath = '智学协作台.exe'; Path = Join-Path $installDir '智学协作台.exe' },
        @{ Scope = 'installed'; RelativePath = 'resources/backend/api.exe'; Path = Join-Path $installDir 'resources\backend\api.exe' },
        @{ Scope = 'installed'; RelativePath = 'resources/elevate.exe'; Path = Join-Path $installDir 'resources\elevate.exe' },
        @{ Scope = 'installed'; RelativePath = 'Uninstall 智学协作台.exe'; Path = Join-Path $installDir 'Uninstall 智学协作台.exe' }
    )

    $seed = 10
    foreach ($entry in $expected) {
        Write-DummyFile -LiteralPath $entry.Path -Seed ([byte]$seed)
        $seed += 10
    }

    $artifacts = @(Get-A3RequiredArtifacts -ReleaseDir $releaseDir -InstallDir $installDir -Version '1.0.0')
    Assert-Equal $artifacts.Count 8 'The installed verification mode must return exactly eight artifacts.'
    for ($index = 0; $index -lt $expected.Count; $index++) {
        Assert-Equal $artifacts[$index].Scope $expected[$index].Scope "Artifact $index scope mismatch."
        Assert-Equal $artifacts[$index].RelativePath $expected[$index].RelativePath "Artifact $index relative path mismatch."
        Assert-Equal ([IO.Path]::GetFullPath($artifacts[$index].Path)) ([IO.Path]::GetFullPath($expected[$index].Path)) "Artifact $index path mismatch."
    }

    $packageArtifacts = @(Get-A3RequiredArtifacts -ReleaseDir $releaseDir -Version '1.0.0')
    Assert-Equal $packageArtifacts.Count 4 'The pre-install verification mode must return exactly four artifacts.'
    for ($index = 0; $index -lt 4; $index++) {
        Assert-Equal $packageArtifacts[$index].RelativePath $expected[$index].RelativePath "Pre-install artifact $index mismatch."
    }

    $providerCalls = [Collections.Generic.List[string]]::new()
    $recordProvider = {
        param([string]$LiteralPath)
        $providerCalls.Add($LiteralPath)
        return New-ValidRecord -LiteralPath $LiteralPath
    }.GetNewClosure()
    $records = @(Assert-A3ArtifactSet -Artifacts $artifacts -ExpectedPublisher 'CN=A3 Learning Project' -RecordProvider $recordProvider)
    Assert-Equal $records.Count 8 'Every artifact must produce one verified record.'
    for ($index = 0; $index -lt $records.Count; $index++) {
        Assert-Equal $records[$index].Path $artifacts[$index].Path "Verified record $index order mismatch."
        Assert-Equal $records[$index].Sha256 (Get-FileHash -LiteralPath $artifacts[$index].Path -Algorithm SHA256).Hash "Verified record $index must contain the raw dummy-file SHA-256."
    }

    New-A3ReleaseManifest `
        -ManifestPath $manifestPath `
        -SourceCommit '0123456789abcdef' `
        -AppVersion '1.0.0' `
        -Artifacts $artifacts `
        -Records $records `
        -VerifiedAtUtc '2026-07-19T01:02:03.0000000Z'

    $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    Assert-True ($manifestBytes.Length -gt 3) 'The release manifest must not be empty.'
    Assert-True (-not ($manifestBytes[0] -eq 0xEF -and $manifestBytes[1] -eq 0xBB -and $manifestBytes[2] -eq 0xBF)) 'The release manifest must be UTF-8 without BOM.'
    $manifestText = [Text.Encoding]::UTF8.GetString($manifestBytes)
    $manifest = $manifestText | ConvertFrom-Json
    Assert-Equal $manifest.schema 'a3-windows-release-manifest/v1' 'Manifest schema mismatch.'
    Assert-Equal $manifest.source_commit '0123456789abcdef' 'Manifest source commit mismatch.'
    Assert-Equal $manifest.app_version '1.0.0' 'Manifest app version mismatch.'
    Assert-Equal $manifest.artifacts.Count 8 'Manifest artifact count mismatch.'

    $expectedSorted = @($artifacts | Sort-Object -Property Scope, RelativePath)
    for ($index = 0; $index -lt $manifest.artifacts.Count; $index++) {
        $entry = $manifest.artifacts[$index]
        Assert-Equal $entry.scope $expectedSorted[$index].Scope "Manifest entry $index scope mismatch."
        Assert-Equal $entry.relative_path $expectedSorted[$index].RelativePath "Manifest entry $index relative path mismatch."
        Assert-Equal $entry.size ([IO.FileInfo]::new($expectedSorted[$index].Path).Length) "Manifest entry $index size mismatch."
        Assert-Equal $entry.sha256 (Get-FileHash -LiteralPath $expectedSorted[$index].Path -Algorithm SHA256).Hash "Manifest entry $index hash mismatch."
        Assert-Equal $entry.subject 'CN=A3 Learning Project' "Manifest entry $index subject mismatch."
        Assert-Equal $entry.timestamp_utc '2026-07-18T08:00:00.0000000Z' "Manifest entry $index timestamp mismatch."
        Assert-Equal $entry.verified_at_utc '2026-07-19T01:02:03.0000000Z' "Manifest entry $index verification timestamp mismatch."
        $fieldNames = @($entry.PSObject.Properties.Name)
        Assert-Equal ($fieldNames -join ',') 'scope,relative_path,size,sha256,subject,timestamp_utc,verified_at_utc' "Manifest entry $index field set mismatch."
    }

    $firstManifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    New-A3ReleaseManifest -ManifestPath $manifestPath -SourceCommit '0123456789abcdef' -AppVersion '1.0.0' -Artifacts $artifacts -Records $records -VerifiedAtUtc '2026-07-19T01:02:03.0000000Z'
    $secondManifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    Assert-Equal ([Convert]::ToBase64String($secondManifestBytes)) ([Convert]::ToBase64String($firstManifestBytes)) 'Manifest output must be deterministic.'

    Remove-Item -LiteralPath $artifacts[2].Path -Force
    $missingProviderState = [pscustomobject]@{ Calls = 0 }
    $missingProvider = {
        param([string]$LiteralPath)
        $missingProviderState.Calls++
        return New-ValidRecord -LiteralPath $LiteralPath
    }.GetNewClosure()
    Assert-ThrowsCode { Assert-A3ArtifactSet -Artifacts $artifacts -ExpectedPublisher 'CN=A3 Learning Project' -RecordProvider $missingProvider } 'A3_ARTIFACT_MISSING' | Out-Null
    Assert-Equal $missingProviderState.Calls 0 'All missing artifacts must be rejected before the record provider is called.'
    Write-DummyFile -LiteralPath $artifacts[2].Path -Seed 30

    $wrongPublisherProvider = {
        param([string]$LiteralPath)
        return New-ValidRecord -LiteralPath $LiteralPath -Subject 'CN=Unexpected Publisher'
    }
    Assert-ThrowsCode { Assert-A3ArtifactSet -Artifacts $artifacts -ExpectedPublisher 'CN=A3 Learning Project' -RecordProvider $wrongPublisherProvider } 'A3_PUBLISHER_MISMATCH' | Out-Null

    $wrongHashProvider = {
        param([string]$LiteralPath)
        $record = New-ValidRecord -LiteralPath $LiteralPath
        $record.Sha256 = ('F' * 64)
        return $record
    }
    Assert-ThrowsCode { Assert-A3ArtifactSet -Artifacts $artifacts -ExpectedPublisher 'CN=A3 Learning Project' -RecordProvider $wrongHashProvider } 'A3_HASH_MISMATCH' | Out-Null

    [IO.File]::WriteAllText($manifestPath, 'old-manifest', [Text.UTF8Encoding]::new($false))
    $failingWriter = {
        param([string]$TemporaryPath, [string]$Json)
        [IO.File]::WriteAllText($TemporaryPath, 'partial', [Text.UTF8Encoding]::new($false))
        throw [IO.IOException]::new('simulated manifest write failure')
    }
    try {
        New-A3ReleaseManifest -ManifestPath $manifestPath -SourceCommit '0123456789abcdef' -AppVersion '1.0.0' -Artifacts $artifacts -Records $records -VerifiedAtUtc '2026-07-19T01:02:03.0000000Z' -WriteProvider $failingWriter
        throw 'Expected the injected manifest writer to fail.'
    }
    catch {
        if ($_.Exception.Message -cne 'simulated manifest write failure') { throw }
    }
    Assert-Equal ([IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8)) 'old-manifest' 'A failed manifest update must preserve the old manifest.'
    Assert-Equal @(Get-ChildItem -LiteralPath $releaseDir -File | Where-Object Name -Like '.a3-windows-release-manifest.json.*.tmp').Count 0 'A failed manifest update must clean its sibling temporary file.'

    Assert-ThrowsCode { Get-A3RequiredArtifacts -ReleaseDir $releaseDir -Version '..\1.0.0' } 'A3_PATH_INVALID' | Out-Null
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$wrapperPath = Join-Path $PSScriptRoot '..\verify-windows-signatures.ps1'
if (-not (Test-Path -LiteralPath $wrapperPath -PathType Leaf)) {
    throw 'The production signature verification wrapper is missing.'
}

$parseTokens = $null
$parseErrors = $null
$wrapperAst = [Management.Automation.Language.Parser]::ParseFile(
    $wrapperPath,
    [ref]$parseTokens,
    [ref]$parseErrors
)
Assert-Equal $parseErrors.Count 0 'The production wrapper must parse without errors.'
$parameterNames = @($wrapperAst.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
Assert-Equal ($parameterNames -join ',') 'ReleaseDir,Version,ExpectedPublisher,SourceCommit,ManifestPath,InstallAndVerify' 'The public wrapper parameter surface must remain exact.'
foreach ($mandatoryName in @('ReleaseDir', 'Version', 'ExpectedPublisher', 'SourceCommit')) {
    $parameter = @($wrapperAst.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -ceq $mandatoryName })[0]
    $mandatoryAttribute = @($parameter.Attributes | Where-Object { $_.TypeName.Name -ceq 'Parameter' })[0]
    Assert-True ($mandatoryAttribute.NamedArguments.ArgumentName -contains 'Mandatory') "$mandatoryName must be mandatory."
}

$functionAsts = @($wrapperAst.FindAll({
    param($Node)
    return $Node -is [Management.Automation.Language.FunctionDefinitionAst]
}, $true))
foreach ($functionAst in $functionAsts) {
    Invoke-Expression $functionAst.Extent.Text
}

$wrapperTestRoot = Join-Path ([IO.Path]::GetTempPath()) ("a3-wrapper-tests-{0}" -f [guid]::NewGuid())
$repositoryRoot = Join-Path $wrapperTestRoot 'repository'
$wrapperReleaseDir = Join-Path $repositoryRoot 'front\a3-front\release'
$runnerTemp = Join-Path $wrapperTestRoot 'runner-temp'
New-Item -ItemType Directory -Path $wrapperReleaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $runnerTemp -Force | Out-Null

try {
    $artifactSafetyRoot = Join-Path $repositoryRoot 'artifact-safety'
    $artifactOutsideRoot = Join-Path $wrapperTestRoot 'artifact-outside'
    $artifactJunction = Join-Path $artifactSafetyRoot 'linked'
    New-Item -ItemType Directory -Path $artifactSafetyRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $artifactOutsideRoot -Force | Out-Null
    Write-DummyFile -LiteralPath (Join-Path $artifactOutsideRoot 'api.exe') -Seed 91
    New-Item -ItemType Junction -Path $artifactJunction -Target $artifactOutsideRoot | Out-Null
    $unsafeArtifact = [pscustomobject]@{
        Scope = 'package'
        RelativePath = 'linked/api.exe'
        Path = Join-Path $artifactJunction 'api.exe'
    }
    Assert-ThrowsCode { Assert-A3ArtifactPathsSafe -Artifacts @($unsafeArtifact) -ReleaseDir $artifactSafetyRoot } 'A3_ARTIFACT_PATH_UNSAFE' | Out-Null

    $preInstallArtifacts = @(
        (Join-Path $wrapperReleaseDir 'win-unpacked\智学协作台.exe'),
        (Join-Path $wrapperReleaseDir 'win-unpacked\resources\backend\api.exe'),
        (Join-Path $wrapperReleaseDir 'win-unpacked\resources\elevate.exe'),
        (Join-Path $wrapperReleaseDir '智学协作台 Setup 1.0.0.exe')
    )
    $seed = 100
    foreach ($path in $preInstallArtifacts) {
        Write-DummyFile -LiteralPath $path -Seed ([byte]$seed)
        $seed += 10
    }

    $nativeCalls = [Collections.Generic.List[pscustomobject]]::new()
    $removedDirectories = [Collections.Generic.List[string]]::new()
    $stoppedProcesses = [Collections.Generic.List[int]]::new()
    $insideProcess = [pscustomobject]@{ Id = 701; Path = $null }
    $outsideProcessPath = Join-Path $wrapperTestRoot 'unrelated.exe'
    Write-DummyFile -LiteralPath $outsideProcessPath -Seed 90
    $outsideProcess = [pscustomobject]@{ Id = 702; Path = $outsideProcessPath }

    $nativeProvider = {
        param([string]$FilePath, [string[]]$Arguments, [bool]$Hidden)
        $nativeCalls.Add([pscustomobject]@{ FilePath = $FilePath; Arguments = @($Arguments); Hidden = $Hidden })
        if ([IO.Path]::GetFileName($FilePath) -ceq '智学协作台 Setup 1.0.0.exe') {
            Assert-Equal $Arguments.Count 2 'The installer must receive exactly two arguments.'
            Assert-Equal $Arguments[0] '/S' 'The first installer argument must be /S.'
            $installArgument = @($Arguments | Where-Object { $_.StartsWith('/D=', [StringComparison]::Ordinal) })
            Assert-Equal $installArgument.Count 1 'The installer must receive exactly one /D argument.'
            $installPath = $installArgument[0].Substring(3)
            Write-DummyFile -LiteralPath (Join-Path $installPath '智学协作台.exe') -Seed 150
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\backend\api.exe') -Seed 160
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\elevate.exe') -Seed 170
            Write-DummyFile -LiteralPath (Join-Path $installPath 'Uninstall 智学协作台.exe') -Seed 180
            $insideProcess.Path = Join-Path $installPath 'resources\backend\api.exe'
        }
        return [pscustomobject]@{ ExitCode = 0 }
    }.GetNewClosure()
    $recordProvider = {
        param([string]$LiteralPath)
        return New-ValidRecord -LiteralPath $LiteralPath
    }
    $processListProvider = { return @($insideProcess, $outsideProcess) }.GetNewClosure()
    $stopProvider = {
        param($Process)
        $stoppedProcesses.Add([int]$Process.Id)
    }.GetNewClosure()
    $removeProvider = {
        param([string]$LiteralPath)
        $removedDirectories.Add($LiteralPath)
        Remove-Item -LiteralPath $LiteralPath -Recurse -Force
    }.GetNewClosure()

    $preflightNativeCalls = [Collections.Generic.List[string]]::new()
    $preflightNativeProvider = {
        param([string]$FilePath, [string[]]$Arguments, [bool]$Hidden)
        $preflightNativeCalls.Add($FilePath)
        if ([IO.Path]::GetFileName($FilePath) -ceq '智学协作台 Setup 1.0.0.exe') {
            $installPath = (@($Arguments | Where-Object { $_.StartsWith('/D=', [StringComparison]::Ordinal) })[0]).Substring(3)
            Write-DummyFile -LiteralPath (Join-Path $installPath '智学协作台.exe') -Seed 141
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\backend\api.exe') -Seed 142
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\elevate.exe') -Seed 143
            Write-DummyFile -LiteralPath (Join-Path $installPath 'Uninstall 智学协作台.exe') -Seed 144
        }
        return [pscustomobject]@{ ExitCode = 0 }
    }.GetNewClosure()
    $preflightPublisherFailureProvider = {
        param([string]$LiteralPath)
        return New-ValidRecord -LiteralPath $LiteralPath -Subject 'CN=Wrong Publisher'
    }
    Assert-ThrowsCode {
        Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -InstallAndVerify -RepositoryRoot $repositoryRoot -RunnerTemp $runnerTemp -RecordProvider $preflightPublisherFailureProvider -NativeProcessProvider $preflightNativeProvider -ProcessListProvider { @() } -StopProcessProvider { param($Process) } -RemoveDirectoryProvider $removeProvider
    } 'A3_PUBLISHER_MISMATCH' | Out-Null
    Assert-Equal $preflightNativeCalls.Count 0 'No installer may execute before all four pre-install artifacts pass signature verification.'

    $installedManifestPath = Join-Path $wrapperReleaseDir 'installed-manifest.json'
    Invoke-A3WindowsSignatureVerification `
        -ReleaseDir $wrapperReleaseDir `
        -Version '1.0.0' `
        -ExpectedPublisher 'CN=A3 Learning Project' `
        -SourceCommit '0123456789abcdef' `
        -ManifestPath $installedManifestPath `
        -InstallAndVerify `
        -RepositoryRoot $repositoryRoot `
        -RunnerTemp $runnerTemp `
        -RecordProvider $recordProvider `
        -NativeProcessProvider $nativeProvider `
        -ProcessListProvider $processListProvider `
        -StopProcessProvider $stopProvider `
        -RemoveDirectoryProvider $removeProvider `
        -VerifiedAtUtc '2026-07-19T02:03:04.0000000Z'

    $installerCalls = @($nativeCalls | Where-Object { [IO.Path]::GetFileName($_.FilePath) -ceq '智学协作台 Setup 1.0.0.exe' })
    Assert-Equal $installerCalls.Count 1 'The installer must run exactly once.'
    Assert-Equal ($installerCalls[0].Arguments -join '|') ("/S|/D={0}" -f $installerCalls[0].Arguments[1].Substring(3)) 'The installer arguments must be an exact two-element array.'
    Assert-True $installerCalls[0].Hidden 'The installer window must be hidden.'
    $uninstallerCalls = @($nativeCalls | Where-Object { [IO.Path]::GetFileName($_.FilePath) -ceq 'Uninstall 智学协作台.exe' })
    Assert-Equal $uninstallerCalls.Count 1 'The exact installed uninstaller must run in finally.'
    Assert-Equal ($uninstallerCalls[0].Arguments -join '|') '/S' 'The uninstaller must receive only /S.'
    Assert-True $uninstallerCalls[0].Hidden 'The uninstaller window must be hidden.'
    Assert-Equal ($stoppedProcesses -join ',') '701' 'Only residual processes resolving inside the isolated install directory may be stopped.'
    Assert-Equal $removedDirectories.Count 1 'The isolated install directory must be removed exactly once.'
    Assert-True (-not (Test-Path -LiteralPath $removedDirectories[0])) 'The verified isolated install directory must be gone after cleanup.'
    $installedManifest = Get-Content -LiteralPath $installedManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Equal $installedManifest.artifacts.Count 8 'Install-and-verify mode must write all eight manifest entries.'

    $nativeCalls.Clear()
    $packageManifestPath = Join-Path $wrapperReleaseDir 'package-manifest.json'
    Invoke-A3WindowsSignatureVerification `
        -ReleaseDir $wrapperReleaseDir `
        -Version '1.0.0' `
        -ExpectedPublisher 'CN=A3 Learning Project' `
        -SourceCommit '0123456789abcdef' `
        -ManifestPath $packageManifestPath `
        -RepositoryRoot $repositoryRoot `
        -RecordProvider $recordProvider `
        -NativeProcessProvider $nativeProvider `
        -VerifiedAtUtc '2026-07-19T02:03:04.0000000Z'
    Assert-Equal $nativeCalls.Count 0 'Pre-install mode must not execute an installer or uninstaller.'
    $packageManifest = Get-Content -LiteralPath $packageManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Equal $packageManifest.artifacts.Count 4 'Pre-install mode must write only four manifest entries.'
    Assert-Equal @($packageManifest.artifacts | Where-Object scope -eq 'installed').Count 0 'Pre-install manifest must omit installed entries.'

    $nonzeroCalls = [Collections.Generic.List[string]]::new()
    $nonzeroProvider = {
        param([string]$FilePath, [string[]]$Arguments, [bool]$Hidden)
        $nonzeroCalls.Add($FilePath)
        return [pscustomobject]@{ ExitCode = 23 }
    }.GetNewClosure()
    Assert-ThrowsCode {
        Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -ManifestPath (Join-Path $wrapperReleaseDir 'nonzero.json') -InstallAndVerify -RepositoryRoot $repositoryRoot -RunnerTemp $runnerTemp -RecordProvider $recordProvider -NativeProcessProvider $nonzeroProvider -ProcessListProvider { @() } -StopProcessProvider { param($Process) } -RemoveDirectoryProvider $removeProvider
    } 'A3_INSTALLER_FAILED' | Out-Null
    Assert-Equal $nonzeroCalls.Count 1 'A nonzero installer must stop before verification or uninstaller execution.'

    $finallyCalls = [Collections.Generic.List[string]]::new()
    $installThenFailProvider = {
        param([string]$FilePath, [string[]]$Arguments, [bool]$Hidden)
        $finallyCalls.Add([IO.Path]::GetFileName($FilePath))
        if ([IO.Path]::GetFileName($FilePath) -ceq '智学协作台 Setup 1.0.0.exe') {
            $installPath = (@($Arguments | Where-Object { $_.StartsWith('/D=', [StringComparison]::Ordinal) })[0]).Substring(3)
            Write-DummyFile -LiteralPath (Join-Path $installPath '智学协作台.exe') -Seed 201
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\backend\api.exe') -Seed 202
            Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\elevate.exe') -Seed 203
            Write-DummyFile -LiteralPath (Join-Path $installPath 'Uninstall 智学协作台.exe') -Seed 204
        }
        return [pscustomobject]@{ ExitCode = 0 }
    }.GetNewClosure()
    $publisherFailureProvider = {
        param([string]$LiteralPath)
        if ($LiteralPath.StartsWith($runnerTemp.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return New-ValidRecord -LiteralPath $LiteralPath -Subject 'CN=Wrong Publisher'
        }
        return New-ValidRecord -LiteralPath $LiteralPath
    }.GetNewClosure()
    Assert-ThrowsCode {
        Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -ManifestPath (Join-Path $wrapperReleaseDir 'publisher-failure.json') -InstallAndVerify -RepositoryRoot $repositoryRoot -RunnerTemp $runnerTemp -RecordProvider $publisherFailureProvider -NativeProcessProvider $installThenFailProvider -ProcessListProvider { @() } -StopProcessProvider { param($Process) } -RemoveDirectoryProvider $removeProvider
    } 'A3_PUBLISHER_MISMATCH' | Out-Null
    Assert-Equal ($finallyCalls -join ',') '智学协作台 Setup 1.0.0.exe,Uninstall 智学协作台.exe' 'Verification failure must still execute the exact uninstaller in finally.'

    Assert-ThrowsCode { Assert-A3PathContained -CandidatePath $wrapperReleaseDir -RootPath $runnerTemp -FailureCode 'A3_INSTALL_PATH_UNSAFE' } 'A3_INSTALL_PATH_UNSAFE' | Out-Null
    Assert-ThrowsCode { Invoke-A3WindowsSignatureVerification -ReleaseDir $runnerTemp -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -RepositoryRoot $repositoryRoot -RecordProvider $recordProvider } 'A3_RELEASE_OUTSIDE_REPOSITORY' | Out-Null
    Assert-ThrowsCode { Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -ManifestPath (Join-Path $runnerTemp 'escaped-manifest.json') -RepositoryRoot $repositoryRoot -RecordProvider $recordProvider } 'A3_MANIFEST_PATH_UNSAFE' | Out-Null

    $ambiguousCleanupState = [pscustomobject]@{ Calls = 0 }
    $ambiguousCleanupProvider = {
        param([string]$LiteralPath)
        $ambiguousCleanupState.Calls++
        Remove-Item -LiteralPath $LiteralPath -Recurse -Force
    }.GetNewClosure()
    $ambiguousInstallProvider = {
        param([string]$FilePath, [string[]]$Arguments, [bool]$Hidden)
        $installPath = (@($Arguments | Where-Object { $_.StartsWith('/D=', [StringComparison]::Ordinal) })[0]).Substring(3)
        Write-DummyFile -LiteralPath (Join-Path $installPath '智学协作台.exe') -Seed 211
        Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\backend\api.exe') -Seed 212
        Write-DummyFile -LiteralPath (Join-Path $installPath 'resources\elevate.exe') -Seed 213
        Write-DummyFile -LiteralPath (Join-Path $installPath 'Uninstall 智学协作台.exe') -Seed 214
        return [pscustomobject]@{ ExitCode = 0 }
    }
    $ambiguousLifecycleChildProvider = {
        param([string]$DirectoryPath)
        if ([IO.Path]::GetFileName($DirectoryPath).StartsWith('a3-signed-install-', [StringComparison]::Ordinal)) {
            return @(
                [pscustomobject]@{ Name = 'Uninstall 智学协作台.exe'; FullName = (Join-Path $DirectoryPath 'Uninstall 智学协作台.exe') },
                [pscustomobject]@{ Name = 'Uninstall 智学协作台.exe'; FullName = (Join-Path $DirectoryPath 'duplicate-uninstaller.exe') }
            )
        }
        return @(Get-ChildItem -LiteralPath $DirectoryPath -File -Force)
    }
    Assert-ThrowsCode {
        Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -InstallAndVerify -RepositoryRoot $repositoryRoot -RunnerTemp $runnerTemp -RecordProvider $recordProvider -NativeProcessProvider $ambiguousInstallProvider -ProcessListProvider { @() } -StopProcessProvider { param($Process) } -RemoveDirectoryProvider $ambiguousCleanupProvider -ArtifactChildProvider $ambiguousLifecycleChildProvider
    } 'A3_ARTIFACT_AMBIGUOUS' | Out-Null
    Assert-Equal $ambiguousCleanupState.Calls 0 'Ambiguous uninstaller discovery must leave the isolated directory untouched.'

    $ambiguousProvider = {
        param([string]$DirectoryPath)
        return @(
            [pscustomobject]@{ Name = '智学协作台 Setup 1.0.0.exe'; FullName = (Join-Path $DirectoryPath 'one.exe') },
            [pscustomobject]@{ Name = '智学协作台 Setup 1.0.0.exe'; FullName = (Join-Path $DirectoryPath 'two.exe') },
            [pscustomobject]@{ Name = 'Uninstall 智学协作台.exe'; FullName = (Join-Path $DirectoryPath 'uninstall-one.exe') },
            [pscustomobject]@{ Name = 'Uninstall 智学协作台.exe'; FullName = (Join-Path $DirectoryPath 'uninstall-two.exe') }
        )
    }
    Assert-ThrowsCode { Find-A3ExactChildArtifact -DirectoryPath $wrapperReleaseDir -FileName '智学协作台 Setup 1.0.0.exe' -ChildProvider $ambiguousProvider } 'A3_ARTIFACT_AMBIGUOUS' | Out-Null
    Assert-ThrowsCode { Find-A3ExactChildArtifact -DirectoryPath $wrapperReleaseDir -FileName 'Uninstall 智学协作台.exe' -ChildProvider $ambiguousProvider } 'A3_ARTIFACT_AMBIGUOUS' | Out-Null

    $junctionTarget = Join-Path $repositoryRoot 'junction-target'
    $junctionPath = Join-Path $repositoryRoot 'junction-release'
    New-Item -ItemType Directory -Path $junctionTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $junctionPath -Target $junctionTarget | Out-Null
    Assert-ThrowsCode { Assert-A3PathContained -CandidatePath $junctionPath -RootPath $repositoryRoot -FailureCode 'A3_REPARSE_POINT' -RejectReparsePoint } 'A3_REPARSE_POINT' | Out-Null

    $runnerJunctionTarget = Join-Path $wrapperTestRoot 'runner-junction-target'
    $runnerJunction = Join-Path $wrapperTestRoot 'runner-junction'
    New-Item -ItemType Directory -Path $runnerJunctionTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $runnerJunction -Target $runnerJunctionTarget | Out-Null
    Assert-ThrowsCode { Invoke-A3WindowsSignatureVerification -ReleaseDir $wrapperReleaseDir -Version '1.0.0' -ExpectedPublisher 'CN=A3 Learning Project' -SourceCommit '0123456789abcdef' -InstallAndVerify -RepositoryRoot $repositoryRoot -RunnerTemp $runnerJunction -RecordProvider $recordProvider -NativeProcessProvider $nativeProvider } 'A3_INSTALL_PATH_UNSAFE' | Out-Null

    $cleanupState = [pscustomobject]@{ Calls = 0 }
    $cleanupProvider = {
        param([string]$LiteralPath)
        $cleanupState.Calls++
    }.GetNewClosure()
    Assert-ThrowsCode { Remove-A3IsolatedInstallDirectory -InstallDir (Join-Path $wrapperTestRoot 'outside-install') -RunnerTemp $runnerTemp -RemoveDirectoryProvider $cleanupProvider } 'A3_INSTALL_PATH_UNSAFE' | Out-Null
    Assert-Equal $cleanupState.Calls 0 'Cleanup must do nothing when install path containment is uncertain.'

    $cleanupReparseTarget = Join-Path $wrapperTestRoot 'cleanup-reparse-target'
    $cleanupReparsePath = Join-Path $runnerTemp 'a3-signed-install-reparse'
    New-Item -ItemType Directory -Path $cleanupReparseTarget -Force | Out-Null
    New-Item -ItemType Junction -Path $cleanupReparsePath -Target $cleanupReparseTarget | Out-Null
    Assert-ThrowsCode { Remove-A3IsolatedInstallDirectory -InstallDir $cleanupReparsePath -RunnerTemp $runnerTemp -RemoveDirectoryProvider $cleanupProvider } 'A3_INSTALL_PATH_UNSAFE' | Out-Null
    Assert-Equal $cleanupState.Calls 0 'Cleanup must do nothing when the isolated directory is a reparse point.'
}
finally {
    Remove-Item -LiteralPath $wrapperTestRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$packageJsonPath = Join-Path $PSScriptRoot '..\..\..\front\a3-front\package.json'
$packageJson = Get-Content -LiteralPath $packageJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-Equal $packageJson.scripts.'test:release-artifacts' 'powershell -NoProfile -ExecutionPolicy Bypass -File ../../scripts/release/tests/release-artifacts.test.ps1' 'package.json must expose the release artifact harness.'
Assert-True $packageJson.scripts.test.EndsWith('npm run test:signatures && npm run test:release-artifacts', [StringComparison]::Ordinal) 'The main npm test command must run release artifact tests immediately after signature tests.'

Write-Host 'release-artifacts.test.ps1 passed'
