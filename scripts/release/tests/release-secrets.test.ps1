$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scannerPath = Join-Path $PSScriptRoot '..\test-release-secrets.ps1'

function Assert-ThrowsCode {
    param([scriptblock]$Action, [string]$Code)
    try {
        & $Action
        throw "Expected $Code"
    }
    catch {
        if ($_.Exception.Data['A3Code'] -cne $Code) { throw }
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Write-Utf8File {
    param([string]$LiteralPath, [string]$Content)
    $parent = Split-Path -Parent $LiteralPath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    [IO.File]::WriteAllText($LiteralPath, $Content, [Text.UTF8Encoding]::new($false))
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("a3-release-secrets-{0}" -f [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

try {
    $azureSecretName = @('AZURE', 'CLIENT', 'SECRET') -join '_'
    $cscLinkName = @('CSC', 'LINK') -join '_'
    $winCscLinkName = @('WIN', 'CSC', 'LINK') -join '_'
    $cscPasswordName = @('CSC', 'KEY', 'PASSWORD') -join '_'
    $privateKeyHeader = '-----BEGIN ' + 'PRIVATE KEY-----'
    $safePath = 'docs\safe.md'
    Write-Utf8File -LiteralPath (Join-Path $testRoot $safePath) -Content '<stored-only-in-GitHub-Environment>'
    & $scannerPath -RepositoryRoot $testRoot -TrackedFiles @($safePath)

    $binaryPath = 'assets\image.png'
    New-Item -ItemType Directory -Path (Split-Path -Parent (Join-Path $testRoot $binaryPath)) -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $testRoot $binaryPath), [byte[]](0, 255, 0, 128))
    & $scannerPath -RepositoryRoot $testRoot -TrackedFiles @($safePath, $binaryPath)

    $unsafeCases = @(
        @{ Path = 'secrets\certificate.pfx'; Content = 'binary fixture'; Rule = 'tracked extension' },
        @{ Path = 'secrets\certificate.p12'; Content = 'binary fixture'; Rule = 'tracked extension' },
        @{ Path = 'secrets\certificate.pem'; Content = 'binary fixture'; Rule = 'tracked extension' },
        @{ Path = 'secrets\certificate.key'; Content = 'binary fixture'; Rule = 'tracked extension' },
        @{ Path = 'docs\private.txt'; Content = $privateKeyHeader; Rule = 'private key' },
        @{ Path = 'config\azure.env'; Content = "$azureSecretName = real-secret"; Rule = 'Azure secret' },
        @{ Path = 'config\csc.env'; Content = "$($cscLinkName): https://example.invalid/signing.pfx"; Rule = 'CSC link' },
        @{ Path = 'config\win-csc.env'; Content = "$winCscLinkName = https://example.invalid/signing.pfx"; Rule = 'Windows CSC link' },
        @{ Path = 'config\password.env'; Content = "$cscPasswordName = real-password"; Rule = 'CSC password' }
    )
    foreach ($unsafeCase in $unsafeCases) {
        Write-Utf8File -LiteralPath (Join-Path $testRoot $unsafeCase.Path) -Content $unsafeCase.Content
        Assert-ThrowsCode {
            & $scannerPath -RepositoryRoot $testRoot -TrackedFiles @($safePath, $unsafeCase.Path)
        } 'A3_RELEASE_SECRET_DETECTED'
    }

    $placeholderPath = 'docs\workflow-placeholder.yml'
    Write-Utf8File -LiteralPath (Join-Path $testRoot $placeholderPath) -Content "${azureSecretName}: `${{ secrets.AZURE_CLIENT_SECRET }}"
    & $scannerPath -RepositoryRoot $testRoot -TrackedFiles @($safePath, $placeholderPath)
    Assert-True $true 'The scanner must allow documented GitHub secret expressions.'
}
finally {
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output 'release-secrets.test.ps1 passed'
