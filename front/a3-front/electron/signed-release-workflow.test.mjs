import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

function sanitizePowerShell(script) {
  let blockComment = false
  let hereTerminator = ''
  const cleaned = []
  for (const line of script.split(/\r?\n/)) {
    if (hereTerminator) {
      if (line.trim() === hereTerminator) hereTerminator = ''
      cleaned.push('')
      continue
    }
    let output = ''
    let quote = ''
    for (let index = 0; index < line.length; index += 1) {
      const pair = line.slice(index, index + 2)
      if (blockComment) {
        if (pair === '#>') {
          blockComment = false
          index += 1
        }
        continue
      }
      if (!quote && pair === '<#') {
        blockComment = true
        index += 1
        continue
      }
      if (!quote && (pair === "@'" || pair === '@"') && line.slice(index + 2).trim() === '') {
        hereTerminator = pair === "@'" ? "'@" : '"@'
        break
      }
      const character = line[index]
      if (!quote && character === '#') break
      if (!quote && (character === "'" || character === '"')) {
        quote = character
        output += ' '
        continue
      }
      if (quote) {
        if (quote === "'" && character === "'" && line[index + 1] === "'") {
          index += 1
          continue
        }
        if (quote === '"' && character === '`') {
          index += 1
          continue
        }
        if (character === quote) quote = ''
        continue
      }
      output += character
    }
    cleaned.push(output)
  }
  return cleaned.join('\n')
}

function parseWorkflowSteps(workflow) {
  const steps = []
  let current
  let collectingRun = false
  for (const line of workflow.split(/\r?\n/)) {
    if (/^ {6}- name:/.test(line)) {
      current = { if: '', uses: '', run: '' }
      steps.push(current)
      collectingRun = false
      continue
    }
    if (!current) continue
    const property = line.match(/^ {8}(if|uses):\s*(.+)$/)
    if (property) {
      current[property[1]] = property[2].trim()
      collectingRun = false
      continue
    }
    if (/^ {8}run:\s*\|?\s*$/.test(line)) {
      collectingRun = true
      continue
    }
    const inlineRun = line.match(/^ {8}run:\s*(.+)$/)
    if (inlineRun) {
      current.run = `${inlineRun[1].trim()}\n`
      collectingRun = false
      continue
    }
    if (collectingRun && /^ {10}/.test(line)) {
      const command = line.slice(10)
      if (!/^\s*#/.test(command)) current.run += `${command}\n`
    } else if (line.trim() !== '') {
      collectingRun = false
    }
  }
  return steps.map((step) => ({ ...step, run: sanitizePowerShell(step.run) }))
}

function assertVerificationPrecedesPublishing(steps) {
  const verification = steps.findIndex((step) => step.run.includes('scripts/release/verify-windows-signatures.ps1'))
  const upload = steps.findIndex((step) => step.uses === 'actions/upload-artifact@v4')
  const publish = steps.findIndex((step) => step.run.includes('gh release'))
  assert.ok(verification >= 0, 'signature verification execution step is required')
  assert.ok(verification < upload, 'artifact upload must occur after signature verification')
  assert.ok(verification < publish, 'tag publishing must occur after signature verification')
  return { verification, upload, publish }
}

test('workflow execution parsing rejects verification text hidden in PowerShell non-execution contexts', () => {
  const maliciousWorkflow = `jobs:
  signed-release:
    steps:
      - name: Fake verification references
        run: |
          Write-Host 'scripts/release/verify-windows-signatures.ps1'
          Write-Host "safe" # scripts/release/verify-windows-signatures.ps1
          <#
          ./scripts/release/verify-windows-signatures.ps1
          #>
          @'
          scripts/release/verify-windows-signatures.ps1
          '@
      - name: Publish too early
        run: gh release upload v1 artifact.exe
      - name: Real verification too late
        run: ./scripts/release/verify-windows-signatures.ps1 -InstallAndVerify
      - name: Upload too late
        uses: actions/upload-artifact@v4
`
  assert.throws(
    () => assertVerificationPrecedesPublishing(parseWorkflowSteps(maliciousWorkflow)),
    /tag publishing must occur after signature verification/,
  )
})

test('the signed Windows release workflow is protected and verifies before publishing', async () => {
  const workflow = await readFile(new URL('../../../.github/workflows/windows-signed-release.yml', import.meta.url), 'utf8')
  const steps = parseWorkflowSteps(workflow)

  assert.match(workflow, /environment:\s*windows-signing/)
  assert.match(workflow, /permissions:\s*[\s\S]*contents:\s*write/)
  assert.match(workflow, /group:\s*windows-signed-release-\$\{\{ github\.ref \}\}/)
  assert.match(workflow, /cancel-in-progress:\s*false/)
  assert.match(workflow, /runs-on:\s*windows-2022/)
  assert.match(workflow, /timeout-minutes:\s*120/)
  assert.match(
    workflow,
    /if:\s*github\.event_name == 'push' && startsWith\(github\.ref, 'refs\/tags\/v'\) \|\| github\.event_name == 'workflow_dispatch' && github\.ref == 'refs\/heads\/main'/,
  )
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
  assert.match(workflow, /if \(\$env:GITHUB_EVENT_NAME -ceq 'push'\)/)
  assert.match(workflow, /elseif \(\$env:GITHUB_EVENT_NAME -ceq 'workflow_dispatch'\)/)
  assert.match(workflow, /v\$version/)
  assert.match(workflow, /npm ci/)
  assert.match(workflow, /python -m pytest -q backend/)
  assert.match(workflow, /build_api\.ps1/)
  assert.match(workflow, /prepare-desktop-backend\.ps1/)
  assert.match(workflow, /desktop:dist:signed/)
  assert.match(workflow, /verify-windows-signatures\.ps1/)
  assert.match(workflow, /A3_EXPECTED_PUBLISHER/)
  assert.match(workflow, /gh release/)
  assert.match(workflow, /if:\s*github\.event_name == 'push' && startsWith\(github\.ref, 'refs\/tags\/v'\)/)

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
    const current = steps.findIndex((step, index) => index > previous && `${step.uses}\n${step.run}`.includes(gate))
    assert.ok(current > previous, `${gate} must follow the preceding release gate`)
    previous = current
  }

  const { verification, upload, publish } = assertVerificationPrecedesPublishing(steps)
  assert.equal(steps[upload].if, "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'")
  assert.equal(steps[publish].if, "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')")
  assert.match(workflow, /retention-days:\s*7/)
  const verificationRun = steps[verification].run
  assert.match(verificationRun, /-InstallAndVerify/)
  assert.match(verificationRun, /-Version\s+\$version/)
  assert.match(verificationRun, /-SourceCommit\s+\$env:GITHUB_SHA/)
  assert.match(verificationRun, /-ExpectedPublisher\s+\$env:A3_EXPECTED_PUBLISHER/)
  assert.match(verificationRun, /-ReleaseDir\s+[^\r\n]+/)
  assert.match(verificationRun, /-ManifestPath\s+[^\r\n]+/)
})
