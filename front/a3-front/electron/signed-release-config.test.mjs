import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const {
  REQUIRED_VARIABLES,
  buildSignedConfig,
  loadSignedReleaseEnvironment,
} = require('../scripts/release/signing-config.cjs')

const projectDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const repositoryDir = path.resolve(projectDir, '..', '..')
const packageJson = JSON.parse(fs.readFileSync(path.join(projectDir, 'package.json'), 'utf8'))
const secretVariableName = ['AZURE', 'CLIENT', 'SECRET'].join('_')
const fakeSecretValue = ['unit', 'test', 'value', 'never', 'logged'].join('-')
const requiredVariableNames = Object.freeze([
  'AZURE_TENANT_ID',
  'AZURE_CLIENT_ID',
  secretVariableName,
  'AZURE_TRUSTED_SIGNING_ENDPOINT',
  'AZURE_CODE_SIGNING_ACCOUNT_NAME',
  'AZURE_CERTIFICATE_PROFILE_NAME',
  'A3_EXPECTED_PUBLISHER',
])
const validEnvironment = Object.freeze({
  A3_SIGNED_RELEASE: '1',
  AZURE_TENANT_ID: '00000000-0000-0000-0000-000000000001',
  AZURE_CLIENT_ID: '00000000-0000-0000-0000-000000000002',
  [secretVariableName]: fakeSecretValue,
  AZURE_TRUSTED_SIGNING_ENDPOINT: 'https://eus.codesigning.azure.net/',
  AZURE_CODE_SIGNING_ACCOUNT_NAME: 'a3-signing',
  AZURE_CERTIFICATE_PROFILE_NAME: 'a3-public-trust',
  A3_EXPECTED_PUBLISHER: 'CN=A3 Learning Project',
})

function captureConfigurationError(callback, forbiddenValues = []) {
  try {
    callback()
    assert.fail('expected signed release configuration to fail')
  } catch (error) {
    assert.doesNotMatch(error.message, new RegExp(fakeSecretValue))
    for (const value of forbiddenValues) assert.equal(error.message.includes(value), false)
    return error
  }
}

function isIgnored(relativePath) {
  const result = spawnSync(
    'git',
    ['check-ignore', '--no-index', '--quiet', '--', relativePath],
    { cwd: repositoryDir, encoding: 'utf8' },
  )
  assert.equal(result.error, undefined)
  assert.ok(result.status === 0 || result.status === 1, result.stderr)
  return result.status === 0
}

function runSigningValidator(environment) {
  const result = spawnSync(
    process.execPath,
    ['scripts/release/validate-signing-env.mjs'],
    { cwd: projectDir, encoding: 'utf8', env: environment },
  )
  assert.equal(result.error, undefined)
  return result
}

test('release source allowlists do not expose credentials or generated output', () => {
  const sourceFiles = [
    'scripts/release/verify.ps1',
    'scripts/release/A3.Release.psm1',
    'scripts/release/tests/verify.test.ps1',
    'front/a3-front/scripts/release/config.cjs',
    'front/a3-front/scripts/release/validate.mjs',
  ]
  for (const relativePath of sourceFiles) {
    assert.equal(isIgnored(relativePath), false, `${relativePath} must remain trackable`)
  }

  const protectedNames = [
    '.env',
    '.env.local',
    'credential.pem',
    'credential.key',
    'credential.p12',
    'credential.pfx',
    'generated.json',
    'artifact.zip',
    'nested/output.exe',
  ]
  for (const sourceRoot of ['scripts/release', 'front/a3-front/scripts/release']) {
    for (const name of protectedNames) {
      const relativePath = `${sourceRoot}/${name}`
      assert.equal(isIgnored(relativePath), true, `${relativePath} must stay ignored`)
    }
  }
  assert.equal(isIgnored('front/a3-front/release/installer.exe'), true)
})

test('required signing variables are immutable and missing values fail with stable errors', () => {
  assert.deepEqual(REQUIRED_VARIABLES, requiredVariableNames)
  assert.equal(Object.isFrozen(REQUIRED_VARIABLES), true)

  for (const name of requiredVariableNames) {
    const missingEnvironment = { ...validEnvironment }
    delete missingEnvironment[name]
    const missingError = captureConfigurationError(() => loadSignedReleaseEnvironment(missingEnvironment))
    assert.equal(missingError.code, 'A3_SIGNING_CONFIG_MISSING')
    assert.match(missingError.message, new RegExp(name))

    const blankError = captureConfigurationError(() =>
      loadSignedReleaseEnvironment({ ...validEnvironment, [name]: '   ' }),
    )
    assert.equal(
      blankError.code,
      name === 'A3_EXPECTED_PUBLISHER'
        ? 'A3_SIGNING_PUBLISHER_INVALID'
        : 'A3_SIGNING_CONFIG_MISSING',
    )
    assert.match(blankError.message, new RegExp(name))
  }
})

test('signed release guard must be exactly 1 without echoing secrets', () => {
  for (const guardValue of [undefined, '0', 'true', ' 1 ']) {
    const environment = { ...validEnvironment }
    if (guardValue === undefined) delete environment.A3_SIGNED_RELEASE
    else environment.A3_SIGNED_RELEASE = guardValue

    const error = captureConfigurationError(() => loadSignedReleaseEnvironment(environment))
    assert.equal(error.code, 'A3_SIGNED_RELEASE_REQUIRED')
  }
})

test('signed release environment requires a valid HTTPS Azure endpoint', () => {
  const invalidEndpoints = [
    'http://eus.codesigning.azure.net/',
    'https://example.test/',
    'https://codesigning.azure.net/',
    'https://nested.eus.codesigning.azure.net/',
    'https://user:password@eus.codesigning.azure.net/',
    'https://eus.codesigning.azure.net:8443/',
    'https://eus.codesigning.azure.net/path',
    'https://eus.codesigning.azure.net/?query=1',
    'https://eus.codesigning.azure.net/#fragment',
    'not a URL',
  ]
  for (const endpoint of invalidEndpoints) {
    const error = captureConfigurationError(() =>
      loadSignedReleaseEnvironment({ ...validEnvironment, AZURE_TRUSTED_SIGNING_ENDPOINT: endpoint }),
      [endpoint],
    )
    assert.equal(error.code, 'A3_SIGNING_ENDPOINT_INVALID')
  }
})

test('signed release environment rejects noncanonical Azure identity IDs', () => {
  for (const name of ['AZURE_TENANT_ID', 'AZURE_CLIENT_ID']) {
    for (const invalidValue of ['not-a-guid', '{00000000-0000-0000-0000-000000000001}', '00000000000000000000000000000001']) {
      const error = captureConfigurationError(
        () => loadSignedReleaseEnvironment({ ...validEnvironment, [name]: invalidValue }),
        [invalidValue],
      )
      assert.equal(error.code, 'A3_SIGNING_ID_INVALID')
      assert.match(error.message, new RegExp(name))
    }
  }
})

test('signed release environment rejects unsafe Azure resource names', () => {
  for (const name of ['AZURE_CODE_SIGNING_ACCOUNT_NAME', 'AZURE_CERTIFICATE_PROFILE_NAME']) {
    for (const invalidValue of ['-leading', 'trailing_', 'has space', 'unsafe;command', 'a'.repeat(65)]) {
      const error = captureConfigurationError(
        () => loadSignedReleaseEnvironment({ ...validEnvironment, [name]: invalidValue }),
        [invalidValue],
      )
      assert.equal(error.code, 'A3_SIGNING_RESOURCE_NAME_INVALID')
      assert.match(error.message, new RegExp(name))
    }
  }
})

test('signed release environment accepts ordinary publisher DNs but rejects unsafe values', () => {
  const publisher = 'CN=A3 Learning Project, O=A3 Education (China), C=CN'
  const values = loadSignedReleaseEnvironment({ ...validEnvironment, A3_EXPECTED_PUBLISHER: publisher })
  assert.equal(values.A3_EXPECTED_PUBLISHER, publisher)

  for (const invalidValue of ['   ', `CN=A3\u0000Project`, `CN=A3\nProject`, 'a'.repeat(257)]) {
    const error = captureConfigurationError(
      () => loadSignedReleaseEnvironment({ ...validEnvironment, A3_EXPECTED_PUBLISHER: invalidValue }),
      [invalidValue],
    )
    assert.equal(error.code, 'A3_SIGNING_PUBLISHER_INVALID')
    assert.match(error.message, /A3_EXPECTED_PUBLISHER/)
  }
})

test('signed release environment trims and freezes validated values', () => {
  const values = loadSignedReleaseEnvironment({
    ...validEnvironment,
    AZURE_CODE_SIGNING_ACCOUNT_NAME: '  a3-signing  ',
  })

  assert.equal(values.AZURE_CODE_SIGNING_ACCOUNT_NAME, 'a3-signing')
  assert.equal(Object.isFrozen(values), true)
  assert.equal(Object.hasOwn(values, secretVariableName), false)
  assert.equal(JSON.stringify(values).includes(fakeSecretValue), false)
})

test('signing environment validator fails closed without leaking secrets', () => {
  const environment = { ...validEnvironment }
  delete environment.A3_SIGNED_RELEASE

  const result = runSigningValidator(environment)

  assert.equal(result.status, 1)
  assert.equal(result.stdout, '')
  assert.equal(
    result.stderr,
    'A3_SIGNED_RELEASE_REQUIRED: A3_SIGNED_RELEASE must be exactly 1.\n',
  )
  assert.equal(result.stderr.includes(fakeSecretValue), false)
})

test('signing environment validator reports only the stable success message', () => {
  const result = runSigningValidator(validEnvironment)

  assert.equal(result.status, 0)
  assert.equal(result.stdout, 'Azure Trusted Signing configuration is present.\n')
  assert.equal(result.stderr, '')
})

test('package scripts keep unsigned builds exact and gate signed builds before compilation', () => {
  assert.equal(packageJson.scripts['desktop:pack'], 'npm run build:desktop && electron-builder --dir')
  assert.equal(packageJson.scripts['desktop:dist'], 'npm run build:desktop && electron-builder --win nsis')
  assert.equal(
    packageJson.scripts['desktop:dist:signed'],
    'node scripts/release/validate-signing-env.mjs && npm run build:desktop && electron-builder --config electron-builder.signed.cjs --win nsis',
  )
})

test('signed config enables Azure SHA-256 signing without mutating the base build', () => {
  const baseBuild = {
    appId: 'com.a3.learning.agent',
    productName: '智学协作台',
    win: {
      icon: 'electron/assets/app-icon.ico',
      target: ['nsis'],
      signAndEditExecutable: true,
    },
    nsis: { oneClick: false },
  }
  const originalBaseBuild = structuredClone(baseBuild)

  const config = buildSignedConfig(baseBuild, validEnvironment)

  assert.notEqual(config, baseBuild)
  assert.notEqual(config.win, baseBuild.win)
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
  assert.deepEqual(baseBuild, originalBaseBuild)
})
