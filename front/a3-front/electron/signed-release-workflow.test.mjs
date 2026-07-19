import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('the signed Windows release workflow is protected and verifies before publishing', async () => {
  const workflow = await readFile(new URL('../../../.github/workflows/windows-signed-release.yml', import.meta.url), 'utf8')

  assert.match(workflow, /environment:\s*windows-signing/)
  assert.match(workflow, /permissions:\s*[\s\S]*contents:\s*write/)
  assert.match(workflow, /group:\s*windows-signed-release-\$\{\{ github\.ref \}\}/)
  assert.match(workflow, /cancel-in-progress:\s*false/)
  assert.match(workflow, /runs-on:\s*windows-2022/)
  assert.match(workflow, /timeout-minutes:\s*120/)
  assert.match(workflow, /push:\s*[\s\S]*tags:\s*\[?'v\*'/)
  assert.match(workflow, /workflow_dispatch:/)
  assert.doesNotMatch(workflow, /pull_request:/)
  assert.match(workflow, /persist-credentials:\s*false/)
  assert.match(workflow, /ref:\s*\$\{\{ github\.sha \}\}/)
  assert.match(workflow, /fetch-depth:\s*0/)
  assert.match(workflow, /actions\/setup-python@v5[\s\S]*python-version:\s*['"]?3\.11/)
  assert.match(workflow, /actions\/setup-node@v4[\s\S]*node-version:\s*['"]?20/)
  assert.match(workflow, /cache-dependency-path:\s*front\/a3-front\/package-lock\.json/)
  assert.match(workflow, /git rev-parse HEAD/)
  assert.match(workflow, /GITHUB_SHA/)
  assert.match(workflow, /refs\/heads\/main/)
  assert.match(workflow, /v\$version/)
  assert.match(workflow, /npm ci/)
  assert.match(workflow, /python -m pytest -q backend/)
  assert.match(workflow, /build_api\.ps1/)
  assert.match(workflow, /prepare-desktop-backend\.ps1/)
  assert.match(workflow, /desktop:dist:signed/)
  assert.match(workflow, /verify-windows-signatures\.ps1/)
  assert.match(workflow, /A3_EXPECTED_PUBLISHER/)
  assert.match(workflow, /gh release/)

  for (const name of [
    'AZURE_TENANT_ID',
    'AZURE_CLIENT_ID',
    'AZURE_CLIENT_SECRET',
    'AZURE_TRUSTED_SIGNING_ENDPOINT',
    'AZURE_CODE_SIGNING_ACCOUNT_NAME',
    'AZURE_CERTIFICATE_PROFILE_NAME',
    'A3_EXPECTED_PUBLISHER',
  ]) {
    assert.match(workflow, new RegExp(`^\\s{6}${name}:`, 'm'))
  }

  const orderedGates = [
    'python -m pip install --upgrade pip',
    'python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt pyinstaller',
    'python -m compileall -q backend',
    'python -m pytest -q backend',
    'npm ci',
    'npm test',
    'npm run build:desktop',
    'backend/build_api.ps1',
    'backend/verify_api_package.ps1',
    'scripts/release/prepare-desktop-backend.ps1',
    'scripts/release/test-release-secrets.ps1',
    'npm run desktop:dist:signed',
    'scripts/release/verify-windows-signatures.ps1',
  ]
  let previous = -1
  for (const gate of orderedGates) {
    const current = workflow.indexOf(gate)
    assert.ok(current > previous, `${gate} must follow the preceding release gate`)
    previous = current
  }

  const verification = workflow.indexOf('scripts/release/verify-windows-signatures.ps1')
  for (const publish of ['actions/upload-artifact@v4', 'gh release']) {
    assert.ok(verification < workflow.indexOf(publish), `${publish} must occur after signature verification`)
  }
  assert.match(workflow, /retention-days:\s*7/)
  assert.match(workflow, /-InstallAndVerify/)
  assert.match(workflow, /-Version\s+\$version/)
  assert.match(workflow, /-SourceCommit\s+\$env:GITHUB_SHA/)
  assert.match(workflow, /-ExpectedPublisher\s+\$env:A3_EXPECTED_PUBLISHER/)
  assert.match(workflow, /-ReleaseDir\s+[^\r\n]+/)
  assert.match(workflow, /-ManifestPath\s+[^\r\n]+/)

  assert.ok(
    workflow.indexOf('verify-windows-signatures.ps1') < workflow.indexOf('gh release'),
    'signature verification must complete before a release can be published',
  )
})
