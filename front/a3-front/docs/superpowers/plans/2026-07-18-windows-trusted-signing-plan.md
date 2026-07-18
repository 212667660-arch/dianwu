# Windows Trusted Signing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed Azure Trusted Signing release path that signs and verifies the A3 Windows installer, application, packaged backend, elevation helper, and uninstaller without changing ordinary unsigned development builds.

**Architecture:** Keep the current `package.json` build as the unsigned development path and layer a separate CommonJS signed configuration over it. A protected GitHub Actions Environment supplies Azure identity and publisher values, a PowerShell verification module validates every required Authenticode record and produces a release manifest, and the workflow refuses to publish unless build, test, install, signature, timestamp, hash, and cleanup gates all pass.

**Tech Stack:** Electron 32, electron-builder 25.1.8 Azure Trusted Signing integration, Node.js built-in test runner, PowerShell 7/Windows PowerShell, PyInstaller, GitHub Actions, Azure Trusted Signing, Authenticode, Windows SDK `signtool.exe`.

---

### Task 1: Add a Pure, Fail-Closed Signed Build Configuration

**Files:**
- Create: `front/a3-front/scripts/release/signing-config.cjs`
- Create: `front/a3-front/scripts/release/validate-signing-env.mjs`
- Create: `front/a3-front/electron-builder.signed.cjs`
- Create: `front/a3-front/electron/signed-release-config.test.mjs`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write the failing configuration tests**

Create `electron/signed-release-config.test.mjs` with a complete fake environment and table-driven missing-variable cases:

```js
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'

const require = createRequire(import.meta.url)
const { buildSignedConfig, loadSignedReleaseEnvironment } = require('../scripts/release/signing-config.cjs')

const secretVariableName = ['AZURE', 'CLIENT', 'SECRET'].join('_')
const validEnvironment = Object.freeze({
  A3_SIGNED_RELEASE: '1',
  AZURE_TENANT_ID: '00000000-0000-0000-0000-000000000001',
  AZURE_CLIENT_ID: '00000000-0000-0000-0000-000000000002',
  [secretVariableName]: ['unit', 'test', 'value', 'never', 'logged'].join('-'),
  AZURE_TRUSTED_SIGNING_ENDPOINT: 'https://eus.codesigning.azure.net/',
  AZURE_CODE_SIGNING_ACCOUNT_NAME: 'a3-signing',
  AZURE_CERTIFICATE_PROFILE_NAME: 'a3-public-trust',
  A3_EXPECTED_PUBLISHER: 'CN=A3 Learning Project',
})

test('signed release environment rejects every missing requirement without echoing secrets', () => {
  for (const name of Object.keys(validEnvironment)) {
    const environment = { ...validEnvironment }
    delete environment[name]
    assert.throws(
      () => loadSignedReleaseEnvironment(environment),
      error => error.code === 'A3_SIGNING_CONFIG_MISSING' && error.message.includes(name),
    )
  }
  try {
    loadSignedReleaseEnvironment({ ...validEnvironment, A3_SIGNED_RELEASE: '0' })
    assert.fail('expected signed release guard to fail')
  } catch (error) {
    assert.equal(error.code, 'A3_SIGNED_RELEASE_REQUIRED')
    assert.doesNotMatch(error.message, /unit-test-value/)
  }
})

test('signed release environment requires an https Azure endpoint', () => {
  assert.throws(
    () => loadSignedReleaseEnvironment({ ...validEnvironment, AZURE_TRUSTED_SIGNING_ENDPOINT: 'http://example.test/' }),
    error => error.code === 'A3_SIGNING_ENDPOINT_INVALID',
  )
})

test('signed config enables only Azure SHA-256 signing and preserves development config', () => {
  const baseBuild = {
    appId: 'com.a3.learning.agent',
    productName: '智学协作台',
    win: { icon: 'electron/assets/app-icon.ico', target: ['nsis'], signAndEditExecutable: true },
    nsis: { oneClick: false },
  }
  const config = buildSignedConfig(baseBuild, validEnvironment)
  assert.equal(config.forceCodeSigning, true)
  assert.deepEqual(config.win.target, ['nsis'])
  assert.equal(config.win.signAndEditExecutable, true)
  assert.deepEqual(config.win.signExts, ['.exe'])
  assert.deepEqual(config.win.azureSignOptions, {
    endpoint: 'https://eus.codesigning.azure.net/',
    codeSigningAccountName: 'a3-signing',
    certificateProfileName: 'a3-public-trust',
    FileDigest: 'SHA256',
    TimestampDigest: 'SHA256',
  })
  assert.equal(baseBuild.forceCodeSigning, undefined)
  assert.equal(baseBuild.win.azureSignOptions, undefined)
})
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run from `front/a3-front`:

```powershell
node --test electron/signed-release-config.test.mjs
```

Expected: FAIL with `Cannot find module '../scripts/release/signing-config.cjs'`.

- [ ] **Step 3: Implement deterministic environment validation and config construction**

Create `scripts/release/signing-config.cjs` with these public functions and stable error codes:

```js
const REQUIRED_VARIABLES = Object.freeze([
  'AZURE_TENANT_ID',
  'AZURE_CLIENT_ID',
  'AZURE_CLIENT_SECRET',
  'AZURE_TRUSTED_SIGNING_ENDPOINT',
  'AZURE_CODE_SIGNING_ACCOUNT_NAME',
  'AZURE_CERTIFICATE_PROFILE_NAME',
  'A3_EXPECTED_PUBLISHER',
])

function configurationError(code, message) {
  const error = new Error(message)
  error.code = code
  return error
}

function loadSignedReleaseEnvironment(environment = process.env) {
  if (environment.A3_SIGNED_RELEASE !== '1') {
    throw configurationError('A3_SIGNED_RELEASE_REQUIRED', 'A3_SIGNED_RELEASE must be exactly 1.')
  }
  const values = {}
  for (const name of REQUIRED_VARIABLES) {
    const value = String(environment[name] ?? '').trim()
    if (!value) throw configurationError('A3_SIGNING_CONFIG_MISSING', `Missing required signing variable: ${name}`)
    values[name] = value
  }
  let endpoint
  try {
    endpoint = new URL(values.AZURE_TRUSTED_SIGNING_ENDPOINT)
  } catch {
    throw configurationError('A3_SIGNING_ENDPOINT_INVALID', 'AZURE_TRUSTED_SIGNING_ENDPOINT must be a valid HTTPS URL.')
  }
  if (endpoint.protocol !== 'https:') {
    throw configurationError('A3_SIGNING_ENDPOINT_INVALID', 'AZURE_TRUSTED_SIGNING_ENDPOINT must be a valid HTTPS URL.')
  }
  values.AZURE_TRUSTED_SIGNING_ENDPOINT = endpoint.href
  return Object.freeze(values)
}

function buildSignedConfig(baseBuild, environment = process.env) {
  const values = loadSignedReleaseEnvironment(environment)
  return {
    ...baseBuild,
    forceCodeSigning: true,
    win: {
      ...baseBuild.win,
      signAndEditExecutable: true,
      signExts: ['.exe'],
      azureSignOptions: {
        endpoint: values.AZURE_TRUSTED_SIGNING_ENDPOINT,
        codeSigningAccountName: values.AZURE_CODE_SIGNING_ACCOUNT_NAME,
        certificateProfileName: values.AZURE_CERTIFICATE_PROFILE_NAME,
        FileDigest: 'SHA256',
        TimestampDigest: 'SHA256',
      },
    },
  }
}

module.exports = { REQUIRED_VARIABLES, buildSignedConfig, loadSignedReleaseEnvironment }
```

Create `scripts/release/validate-signing-env.mjs`:

```js
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { loadSignedReleaseEnvironment } = require('./signing-config.cjs')

try {
  loadSignedReleaseEnvironment(process.env)
  process.stdout.write('Azure Trusted Signing configuration is present.\n')
} catch (error) {
  process.stderr.write(`${error.code ?? 'A3_SIGNING_CONFIG_INVALID'}: ${error.message}\n`)
  process.exitCode = 1
}
```

Create `electron-builder.signed.cjs`:

```js
const packageJson = require('./package.json')
const { buildSignedConfig } = require('./scripts/release/signing-config.cjs')

module.exports = buildSignedConfig(packageJson.build, process.env)
```

- [ ] **Step 4: Add the signed command without changing unsigned commands**

Modify `package.json` so the scripts include:

```json
"test:signing-config": "node --test electron/signed-release-config.test.mjs",
"desktop:dist:signed": "node scripts/release/validate-signing-env.mjs && npm run build:desktop && electron-builder --config electron-builder.signed.cjs --win nsis"
```

Keep `desktop:pack` and `desktop:dist` byte-for-byte equivalent to their current unsigned behavior. Add `electron/signed-release-config.test.mjs` to the main `node --test` file list.

- [ ] **Step 5: Run focused GREEN and the fail-closed command**

```powershell
node --test electron/signed-release-config.test.mjs
Remove-Item Env:A3_SIGNED_RELEASE -ErrorAction SilentlyContinue
npm run desktop:dist:signed
```

Expected: the Node test passes; the signed command exits nonzero with `A3_SIGNED_RELEASE_REQUIRED` before `build:desktop` or electron-builder starts.

- [ ] **Step 6: Commit the signed configuration slice**

```powershell
git add front/a3-front/package.json front/a3-front/electron-builder.signed.cjs front/a3-front/scripts/release/signing-config.cjs front/a3-front/scripts/release/validate-signing-env.mjs front/a3-front/electron/signed-release-config.test.mjs
git commit -m "feat: add fail-closed trusted signing config"
```

### Task 2: Build an Injectable Authenticode Verification Core

**Files:**
- Create: `scripts/release/A3.SignatureVerification.psm1`
- Create: `scripts/release/tests/signature-verification.test.ps1`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write a framework-free PowerShell test harness**

The test file imports the module, defines `Assert-ThrowsCode`, and exercises `Valid`, `NotSigned`, `HashMismatch`, `PublisherMismatch`, `NotTimeStamped`, `Sha1Digest`, and timestamp-outside-certificate records:

```powershell
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\A3.SignatureVerification.psm1') -Force

function Assert-ThrowsCode([scriptblock]$Action, [string]$Code) {
    try { & $Action; throw "Expected $Code" }
    catch {
        if ($_.Exception.Data['A3Code'] -ne $Code) { throw }
    }
}

function Copy-Record([pscustomobject]$Source) {
    $copy = [ordered]@{}
    foreach ($property in $Source.PSObject.Properties) { $copy[$property.Name] = $property.Value }
    return [pscustomobject]$copy
}

$valid = [pscustomobject]@{
    Path = 'C:\release\智学协作台.exe'
    Status = 'Valid'
    Subject = 'CN=A3 Learning Project'
    FileDigestAlgorithm = 'SHA256'
    TimestampUtc = '2026-07-18T08:00:00Z'
    CertificateNotBeforeUtc = '2026-07-01T00:00:00Z'
    CertificateNotAfterUtc = '2027-07-01T00:00:00Z'
    Sha256 = ('A' * 64)
}

Assert-A3SignatureRecord -Record $valid -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 ('A' * 64)

$notSigned = Copy-Record $valid
$notSigned.Status = 'NotSigned'
Assert-ThrowsCode { Assert-A3SignatureRecord -Record $notSigned -ExpectedPublisher 'CN=A3 Learning Project' } 'A3_SIGNATURE_INVALID'

$wrongExpectedPublisher = Copy-Record $valid
Assert-ThrowsCode { Assert-A3SignatureRecord -Record $wrongExpectedPublisher -ExpectedPublisher 'CN=Wrong' } 'A3_PUBLISHER_MISMATCH'

foreach ($case in @(
    @{ Property = 'Subject'; Value = 'CN=Other'; Code = 'A3_PUBLISHER_MISMATCH' },
    @{ Property = 'TimestampUtc'; Value = $null; Code = 'A3_TIMESTAMP_MISSING' },
    @{ Property = 'FileDigestAlgorithm'; Value = 'SHA1'; Code = 'A3_DIGEST_NOT_SHA256' },
    @{ Property = 'Sha256'; Value = ('B' * 64); Code = 'A3_HASH_MISMATCH' },
    @{ Property = 'TimestampUtc'; Value = '2028-01-01T00:00:00Z'; Code = 'A3_TIMESTAMP_OUTSIDE_CERTIFICATE' }
)) {
    $record = Copy-Record $valid
    $record.($case.Property) = $case.Value
    Assert-ThrowsCode { Assert-A3SignatureRecord -Record $record -ExpectedPublisher 'CN=A3 Learning Project' -ExpectedSha256 ('A' * 64) } $case.Code
}

Write-Host 'signature-verification.test.ps1 passed'
```

- [ ] **Step 2: Run the harness and confirm RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/signature-verification.test.ps1
```

Expected: FAIL because `A3.SignatureVerification.psm1` does not exist.

- [ ] **Step 3: Implement stable validation errors and record validation**

`A3.SignatureVerification.psm1` must export these functions:

```powershell
function New-A3SignatureError([string]$Code, [string]$Message) {
    $exception = [System.InvalidOperationException]::new($Message)
    $exception.Data['A3Code'] = $Code
    return $exception
}

function Assert-A3SignatureRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject]$Record,
        [Parameter(Mandatory)] [string]$ExpectedPublisher,
        [string]$ExpectedSha256
    )
    if ($Record.Status -ne 'Valid') { throw (New-A3SignatureError 'A3_SIGNATURE_INVALID' "Invalid Authenticode status for $($Record.Path).") }
    if ($Record.Subject -cne $ExpectedPublisher) { throw (New-A3SignatureError 'A3_PUBLISHER_MISMATCH' "Unexpected signer for $($Record.Path).") }
    if ($Record.FileDigestAlgorithm -cne 'SHA256') { throw (New-A3SignatureError 'A3_DIGEST_NOT_SHA256' "Non-SHA256 file digest for $($Record.Path).") }
    if (-not $Record.TimestampUtc) { throw (New-A3SignatureError 'A3_TIMESTAMP_MISSING' "Missing trusted timestamp for $($Record.Path).") }
    $timestamp = [DateTimeOffset]::Parse($Record.TimestampUtc).ToUniversalTime()
    $notBefore = [DateTimeOffset]::Parse($Record.CertificateNotBeforeUtc).ToUniversalTime()
    $notAfter = [DateTimeOffset]::Parse($Record.CertificateNotAfterUtc).ToUniversalTime()
    if ($timestamp -lt $notBefore -or $timestamp -gt $notAfter) { throw (New-A3SignatureError 'A3_TIMESTAMP_OUTSIDE_CERTIFICATE' "Timestamp outside signer certificate validity for $($Record.Path).") }
    if ($ExpectedSha256 -and $Record.Sha256 -cne $ExpectedSha256.ToUpperInvariant()) { throw (New-A3SignatureError 'A3_HASH_MISMATCH' "SHA-256 mismatch for $($Record.Path).") }
}
```

Add `Find-A3SignTool`, `Get-A3SignatureRecord`, and `Assert-A3SignatureRecords`. `Get-A3SignatureRecord` must:

1. Resolve an existing literal path.
2. Call `Get-AuthenticodeSignature`.
3. Require the Windows SDK `signtool.exe` discovered below `%ProgramFiles(x86)%\Windows Kits\10\bin\*\x64\signtool.exe`.
4. Run `signtool verify /pa /all /v <path>` and require exit code 0.
5. Parse `The signature is timestamped:` and `Hash of file (sha256):` from the English GitHub runner output.
6. Return only the record fields used above; never include command environment variables or certificate private data.

Export exactly:

```powershell
Export-ModuleMember -Function Assert-A3SignatureRecord, Assert-A3SignatureRecords, Find-A3SignTool, Get-A3SignatureRecord, New-A3SignatureError
```

- [ ] **Step 4: Make the test record construction explicit and run GREEN**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/signature-verification.test.ps1
```

Expected: `signature-verification.test.ps1 passed` and exit code 0.

- [ ] **Step 5: Add the harness to npm verification**

Add:

```json
"test:signatures": "powershell -NoProfile -ExecutionPolicy Bypass -File ../../scripts/release/tests/signature-verification.test.ps1"
```

Append `npm run test:signatures` to the main `test` script after Node and Vitest tests so Windows release verification cannot silently lose the PowerShell unit coverage.

- [ ] **Step 6: Commit the verification core**

```powershell
git add scripts/release/A3.SignatureVerification.psm1 scripts/release/tests/signature-verification.test.ps1 front/a3-front/package.json
git commit -m "test: validate Windows signature records"
```

### Task 3: Verify the Complete Packaged and Installed Artifact Set

**Files:**
- Create: `scripts/release/verify-windows-signatures.ps1`
- Create: `scripts/release/tests/release-artifacts.test.ps1`
- Modify: `scripts/release/A3.SignatureVerification.psm1`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write failing artifact-set and manifest tests**

The test creates a temporary `release/win-unpacked` tree with these exact relative paths:

```text
win-unpacked/智学协作台.exe
win-unpacked/resources/backend/api.exe
win-unpacked/resources/elevate.exe
智学协作台 Setup 1.0.0.exe
installed/智学协作台.exe
installed/resources/backend/api.exe
installed/resources/elevate.exe
installed/Uninstall 智学协作台.exe
```

Use small dummy byte files and inject a record provider that returns valid constructed records with the real dummy-file SHA-256. Assert that `New-A3ReleaseManifest` writes:

```json
{
  "schema": "a3-windows-release-manifest/v1",
  "source_commit": "0123456789abcdef",
  "app_version": "1.0.0",
  "artifacts": []
}
```

Each artifact entry must contain `scope`, `relative_path`, `size`, `sha256`, `subject`, `timestamp_utc`, and `verified_at_utc`. Remove one file and expect `A3_ARTIFACT_MISSING`; return an unexpected subject and expect `A3_PUBLISHER_MISMATCH`.

- [ ] **Step 2: Run the artifact harness and confirm RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/release-artifacts.test.ps1
```

Expected: FAIL because artifact-set functions are not exported.

- [ ] **Step 3: Add exact artifact discovery and manifest construction**

Extend the module with:

```powershell
function Get-A3RequiredArtifacts {
    param([string]$ReleaseDir, [string]$InstallDir, [string]$Version)
    @(
        @{ Scope = 'package'; RelativePath = 'win-unpacked/智学协作台.exe'; Path = Join-Path $ReleaseDir 'win-unpacked\智学协作台.exe' },
        @{ Scope = 'package'; RelativePath = 'win-unpacked/resources/backend/api.exe'; Path = Join-Path $ReleaseDir 'win-unpacked\resources\backend\api.exe' },
        @{ Scope = 'package'; RelativePath = 'win-unpacked/resources/elevate.exe'; Path = Join-Path $ReleaseDir 'win-unpacked\resources\elevate.exe' },
        @{ Scope = 'release'; RelativePath = "智学协作台 Setup $Version.exe"; Path = Join-Path $ReleaseDir "智学协作台 Setup $Version.exe" },
        @{ Scope = 'installed'; RelativePath = '智学协作台.exe'; Path = Join-Path $InstallDir '智学协作台.exe' },
        @{ Scope = 'installed'; RelativePath = 'resources/backend/api.exe'; Path = Join-Path $InstallDir 'resources\backend\api.exe' },
        @{ Scope = 'installed'; RelativePath = 'resources/elevate.exe'; Path = Join-Path $InstallDir 'resources\elevate.exe' },
        @{ Scope = 'installed'; RelativePath = 'Uninstall 智学协作台.exe'; Path = Join-Path $InstallDir 'Uninstall 智学协作台.exe' }
    ) | ForEach-Object { [pscustomobject]$_ }
}
```

`Assert-A3ArtifactSet` must reject missing paths before invoking the provider, call `Assert-A3SignatureRecord` for every path, and return verified records in the same order. `New-A3ReleaseManifest` must sort artifact entries by `scope, relative_path`, serialize with `ConvertTo-Json -Depth 6`, write UTF-8 without BOM to a sibling temporary file, and replace the target only after serialization succeeds.

- [ ] **Step 4: Implement the production wrapper and isolated install lifecycle**

Create `verify-windows-signatures.ps1` with mandatory parameters:

```powershell
param(
    [Parameter(Mandatory)] [string]$ReleaseDir,
    [Parameter(Mandatory)] [string]$Version,
    [Parameter(Mandatory)] [string]$ExpectedPublisher,
    [Parameter(Mandatory)] [string]$SourceCommit,
    [string]$ManifestPath,
    [switch]$InstallAndVerify
)
```

Resolve `ReleaseDir`, require it to be inside the repository, and default `ManifestPath` to `release/a3-windows-release-manifest.json`. With `-InstallAndVerify`:

1. Create an empty `%RUNNER_TEMP%\a3-signed-install-<guid>`.
2. Start the exact installer with `@('/S', "/D=$installDir")`, hidden, and require exit code 0.
3. Discover and verify all eight artifacts.
4. Write the manifest only after every verification passes.
5. In `finally`, run the exact installed uninstaller with `/S`, wait for exit, terminate only residual processes whose executable path resolves under the isolated install directory, and remove only that verified temporary directory.

Without `-InstallAndVerify`, verify the four pre-install artifacts and omit installed entries. Never use wildcard selection when more than one installer or uninstaller matches; ambiguity is `A3_ARTIFACT_AMBIGUOUS`.

- [ ] **Step 5: Run the artifact tests and main PowerShell tests**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/release-artifacts.test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/signature-verification.test.ps1
```

Expected: both print their passed marker and exit 0.

- [ ] **Step 6: Wire the artifact harness into npm and commit**

Add `test:release-artifacts` and append it after `test:signatures` in `npm test`, then commit:

```powershell
git add scripts/release/A3.SignatureVerification.psm1 scripts/release/verify-windows-signatures.ps1 scripts/release/tests/release-artifacts.test.ps1 front/a3-front/package.json
git commit -m "feat: verify signed Windows release artifacts"
```

### Task 4: Stage the Verified PyInstaller Backend Safely

**Files:**
- Create: `scripts/release/prepare-desktop-backend.ps1`
- Create: `scripts/release/tests/prepare-desktop-backend.test.ps1`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write failing atomic-copy tests**

Use a temporary repository-shaped directory, create `dist/api/api.exe` and `_internal/marker.txt`, seed `front/a3-front/desktop-backend` with an old marker, and assert:

- source and target outside the supplied repository root are rejected with `A3_PATH_OUTSIDE_REPOSITORY`;
- a missing `api.exe` is rejected with `A3_BACKEND_EXECUTABLE_MISSING`;
- a successful copy replaces the target atomically and preserves the full relative file set;
- an injected failure before final rename restores the original target and removes staging/backup directories.

Expose failure injection only as a script parameter named `-TestFailurePoint` and reject it unless `A3_RELEASE_SCRIPT_TEST_MODE=1`.

- [ ] **Step 2: Run the copy harness and confirm RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/prepare-desktop-backend.test.ps1
```

Expected: FAIL because `prepare-desktop-backend.ps1` does not exist.

- [ ] **Step 3: Implement verified absolute-path containment and rollback**

The script parameters are:

```powershell
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent),
    [string]$Source = 'dist\api',
    [string]$Target = 'front\a3-front\desktop-backend',
    [ValidateSet('', 'AfterBackup', 'AfterStage')] [string]$TestFailurePoint = ''
)
```

Resolve root, source, and target to absolute paths; append a directory separator to the root comparison; reject reparse points in source; require `api.exe`; copy source into a target sibling `.staging-<guid>`; compare relative file lists, lengths, and SHA-256 values; rename the existing target to `.backup-<guid>`; rename staging to the exact target; and remove the backup only after the target is re-verified. `catch` restores the backup if needed, while `finally` removes only staging/backup paths already proven to be target siblings under the repository root.

- [ ] **Step 4: Run GREEN and add the test to npm**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/prepare-desktop-backend.test.ps1
```

Add `test:prepare-backend` to `package.json` and append it to `npm test`.

- [ ] **Step 5: Commit the staging slice**

```powershell
git add scripts/release/prepare-desktop-backend.ps1 scripts/release/tests/prepare-desktop-backend.test.ps1 front/a3-front/package.json
git commit -m "feat: stage verified desktop backend atomically"
```

### Task 5: Add Release Secret Scanning and Workflow Contract Tests

**Files:**
- Create: `scripts/release/test-release-secrets.ps1`
- Create: `scripts/release/tests/release-secrets.test.ps1`
- Create: `front/a3-front/electron/signed-release-workflow.test.mjs`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write failing scanner and workflow tests**

The scanner harness creates a temporary tracked-file list containing safe documentation, then separate fixtures for `.pfx`, `.p12`, `.pem`, `.key`, a private-key header, a nonempty Azure client-secret assignment, and a nonempty CSC link assignment. Construct sensitive variable names and assignment strings from fragments at test runtime so the tracked test source does not itself match the production scanner. Every unsafe case must exit nonzero with `A3_RELEASE_SECRET_DETECTED`, while the safe case passes.

The Node workflow test reads `.github/workflows/windows-signed-release.yml` and asserts:

```js
assert.match(workflow, /environment:\s*windows-signing/)
assert.match(workflow, /push:\s*[\s\S]*tags:\s*\[?'v\*'/)
assert.match(workflow, /workflow_dispatch:/)
assert.doesNotMatch(workflow, /pull_request:/)
assert.match(workflow, /persist-credentials:\s*false/)
assert.match(workflow, /npm ci/)
assert.match(workflow, /python -m pytest -q backend/)
assert.match(workflow, /build_api\.ps1/)
assert.match(workflow, /prepare-desktop-backend\.ps1/)
assert.match(workflow, /desktop:dist:signed/)
assert.match(workflow, /verify-windows-signatures\.ps1/)
assert.match(workflow, /A3_EXPECTED_PUBLISHER/)
assert.match(workflow, /gh release/)
```

- [ ] **Step 2: Run both tests and confirm RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/release-secrets.test.ps1
node --test front/a3-front/electron/signed-release-workflow.test.mjs
```

Expected: scanner script and workflow file are missing.

- [ ] **Step 3: Implement a tracked-file release scanner**

`test-release-secrets.ps1` must accept `-RepositoryRoot` and optional `-TrackedFiles` for test injection. In production, obtain paths from `git -C $RepositoryRoot ls-files -z`, reject tracked extensions `.pfx`, `.p12`, `.pem`, `.key`, and scan UTF-8 text for:

```text
-----BEGIN ... PRIVATE KEY-----
AZURE_CLIENT_SECRET followed by = or : and a non-placeholder value
CSC_LINK or WIN_CSC_LINK followed by = or : and a non-placeholder value
CSC_KEY_PASSWORD or WIN_CSC_KEY_PASSWORD followed by = or : and a non-placeholder value
```

Allow only the literal documentation markers `<stored-only-in-GitHub-Environment>`, `${{ secrets.NAME }}`, and variable names without assigned values. Print file paths and rule ids, never the matched value.

- [ ] **Step 4: Add npm test entries**

Add the workflow test to the main Node test list. Add `test:release-secrets` and append it to `npm test`.

- [ ] **Step 5: Run GREEN and commit**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/tests/release-secrets.test.ps1
node --test front/a3-front/electron/signed-release-workflow.test.mjs
git add scripts/release/test-release-secrets.ps1 scripts/release/tests/release-secrets.test.ps1 front/a3-front/electron/signed-release-workflow.test.mjs front/a3-front/package.json
git commit -m "test: guard signed release secrets and workflow"
```

### Task 6: Create the Protected Windows Signed Release Workflow

**Files:**
- Create: `.github/workflows/windows-signed-release.yml`
- Modify: `front/a3-front/electron/signed-release-workflow.test.mjs`

- [ ] **Step 1: Add the workflow with protected triggers and permissions**

The workflow must use this top-level shape:

```yaml
name: Windows signed release

on:
  push:
    tags: ['v*']
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: windows-signed-release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  signed-release:
    if: startsWith(github.ref, 'refs/tags/v') || github.ref == 'refs/heads/main'
    runs-on: windows-2022
    environment: windows-signing
    timeout-minutes: 120
    env:
      A3_SIGNED_RELEASE: '1'
      AZURE_TENANT_ID: ${{ vars.AZURE_TENANT_ID }}
      AZURE_CLIENT_ID: ${{ vars.AZURE_CLIENT_ID }}
      AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
      AZURE_TRUSTED_SIGNING_ENDPOINT: ${{ vars.AZURE_TRUSTED_SIGNING_ENDPOINT }}
      AZURE_CODE_SIGNING_ACCOUNT_NAME: ${{ vars.AZURE_CODE_SIGNING_ACCOUNT_NAME }}
      AZURE_CERTIFICATE_PROFILE_NAME: ${{ vars.AZURE_CERTIFICATE_PROFILE_NAME }}
      A3_EXPECTED_PUBLISHER: ${{ vars.A3_EXPECTED_PUBLISHER }}
```

Use `actions/checkout@v4` with `ref: ${{ github.sha }}`, `fetch-depth: 0`, and `persist-credentials: false`; `actions/setup-python@v5` with Python 3.11; `actions/setup-node@v4` with the repository Node version chosen for Electron 32 and npm cache at `front/a3-front/package-lock.json`.

- [ ] **Step 2: Add source identity and version gates**

Use PowerShell to require `git rev-parse HEAD` equals `$env:GITHUB_SHA`. For tags, require `v<package.json version>` equals `$env:GITHUB_REF_NAME`. For manual runs, require `refs/heads/main`. Print only commit, version, actor, and ref.

- [ ] **Step 3: Add build and test gates in exact order**

The workflow steps are:

```text
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt pyinstaller
python -m compileall -q backend
python -m pytest -q backend
npm ci                           (front/a3-front)
npm test                         (front/a3-front)
npm run build:desktop            (front/a3-front)
backend/build_api.ps1
backend/verify_api_package.ps1
scripts/release/prepare-desktop-backend.ps1
scripts/release/test-release-secrets.ps1
npm run desktop:dist:signed      (front/a3-front)
scripts/release/verify-windows-signatures.ps1 -InstallAndVerify
```

Pass the package version, `$env:GITHUB_SHA`, expected publisher, release directory, and manifest path explicitly to the verification script.

- [ ] **Step 4: Publish only after verification**

For manual `main` runs, upload the installer and JSON manifest using `actions/upload-artifact@v4` with retention 7 days. For tag runs, use authenticated `gh release view/create/upload` commands to create the exact tag release if absent and upload the installer plus manifest with `--clobber`. No publish command may appear before the signature verification step.

- [ ] **Step 5: Run workflow contract GREEN and commit**

```powershell
cd front/a3-front
node --test electron/signed-release-workflow.test.mjs
cd ../..
git add .github/workflows/windows-signed-release.yml front/a3-front/electron/signed-release-workflow.test.mjs
git commit -m "ci: add protected Windows signed release"
```

### Task 7: Document Azure Resource Setup and Credential Rotation

**Files:**
- Create: `docs/release/azure-trusted-signing.md`
- Modify: `README.md`
- Modify: `front/a3-front/README.md`

- [ ] **Step 1: Write the exact resource and identity checklist**

The document must state that Azure resources are not created by repository code and list this order:

1. Confirm Azure Trusted Signing availability and identity-verification eligibility in the chosen region.
2. Create one Trusted Signing account and one public-trust certificate profile dedicated to A3 Windows releases.
3. Create a Microsoft Entra application/service principal dedicated to GitHub signed releases.
4. Assign only `Trusted Signing Certificate Profile Signer` on the target account/profile scope.
5. Create the GitHub Environment `windows-signing`, enable required reviewers, deployment branch/tag restrictions, and prevent administrator bypass where repository policy permits.
6. Add the six non-secret variables and one secret using the exact names from the design.

No example may contain a real tenant, client, secret, certificate, password, PFX/P12, or private key.

- [ ] **Step 2: Document secret-safe validation and rotation**

Include commands that validate variable presence without values:

```powershell
cd front/a3-front
$env:A3_SIGNED_RELEASE = '1'
node scripts/release/validate-signing-env.mjs
```

Explain that this command checks shape only and the protected workflow is the real Azure connection test. Rotation order is: create a second client credential, replace only the GitHub Environment secret, run an approved manual signed build, then revoke the old credential. Azure/profile revocation must immediately block release; never work around it by disabling `forceCodeSigning`.

- [ ] **Step 3: Document expected blocked behavior and local unsigned builds**

State explicitly:

```text
npm run desktop:pack          # local unsigned development package
npm run desktop:dist          # local unsigned development installer
npm run desktop:dist:signed   # formal path; fails before packaging without protected configuration
```

Add links from both READMEs and state that credentials must never be pasted into issues, chat, logs, commits, or artifacts.

- [ ] **Step 4: Run the secret scanner and commit documentation**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/test-release-secrets.ps1
git diff --check
git add docs/release/azure-trusted-signing.md README.md front/a3-front/README.md
git commit -m "docs: explain Azure Trusted Signing setup"
```

### Task 8: Run Local Release Verification and Record the External Gate

**Files:**
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Run all deterministic tests**

From the repository root:

```powershell
& .\.test-venv\Scripts\python.exe -m compileall -q backend
& .\.test-venv\Scripts\python.exe -m pytest -q backend
cd front/a3-front
npm test
npm run build:desktop
cd ../..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release/test-release-secrets.ps1
git diff --check
```

Expected: no failures; record actual post-change test counts rather than copying the baseline counts.

- [ ] **Step 2: Prove signed and unsigned command separation**

```powershell
cd front/a3-front
Remove-Item Env:A3_SIGNED_RELEASE -ErrorAction SilentlyContinue
npm run desktop:dist:signed
npm run desktop:dist
cd ../..
```

Expected: signed command exits nonzero with `A3_SIGNED_RELEASE_REQUIRED` before packaging; ordinary unsigned installer build succeeds.

- [ ] **Step 3: Review the produced unsigned artifact and repository state**

Run `Get-AuthenticodeSignature` on the unsigned installer only to confirm the development path remains unsigned, verify no generated `release/` or `desktop-backend/` content is staged, and preserve `.tmp/` plus `dist-s033*` directories.

- [ ] **Step 4: Update the queue truthfully**

If deterministic implementation passes but Azure resources are still absent, set S-042 to `阻塞` with the sole blocker “create/configure Azure Trusted Signing account, profile, service principal and protected GitHub Environment, then run the formal workflow.” Record implementation commits, files, exact test counts, unsigned build result, fail-closed result, and absence of credentials. Set S-043 to `进行中` so language implementation continues immediately.

- [ ] **Step 5: Commit the verification record**

```powershell
git add codex/AI模型任务队列.md
git commit -m "docs: record trusted signing implementation gate"
```

### Task 9: Complete Real Azure-Signed Acceptance When Resources Exist

**Files:**
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Run the protected workflow without exposing credentials**

Use a manually approved `main` run first. Do not print Environment values. Require all tests, PyInstaller verification, electron-builder signing, isolated install, signature verification, manifest generation, uninstall, and zero-residual-process checks to pass.

- [ ] **Step 2: Perform tamper rejection inside the protected job**

Copy one signed unpacked executable to `$env:RUNNER_TEMP`, flip one byte after the PE signature has been created, call `Get-A3SignatureRecord`, and require `A3_SIGNATURE_INVALID` or `A3_HASH_MISMATCH`. Delete only the verified temporary copy.

- [ ] **Step 3: Verify the tag release**

Push an approved `v<package version>` tag after the manual run. Confirm the GitHub Release contains exactly the signed installer and JSON manifest, and that manifest SHA-256 matches a fresh download.

- [ ] **Step 4: Mark S-042 complete**

Record workflow run URL/id, source commit, tag, installer size/SHA-256, exact signer Subject, timestamp result, signed child executable results, install/uninstall lifecycle, and zero residual processes. Never record tenant ids, client ids, secrets, access tokens, certificate material, or absolute runner paths.

- [ ] **Step 5: Commit and push the completion record**

```powershell
git add codex/AI模型任务队列.md
git commit -m "docs: record trusted Windows release acceptance"
git push
```
