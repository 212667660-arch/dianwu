import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('the signed Windows release workflow is protected and verifies before publishing', async () => {
  const workflow = await readFile(new URL('../../../.github/workflows/windows-signed-release.yml', import.meta.url), 'utf8')

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

  assert.ok(
    workflow.indexOf('verify-windows-signatures.ps1') < workflow.indexOf('gh release'),
    'signature verification must complete before a release can be published',
  )
})
