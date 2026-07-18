import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'

const require = createRequire(import.meta.url)
const {
  REQUIRED_VARIABLES,
  buildSignedConfig,
  loadSignedReleaseEnvironment,
} = require('../scripts/release/signing-config.cjs')

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

function captureConfigurationError(callback) {
  try {
    callback()
    assert.fail('expected signed release configuration to fail')
  } catch (error) {
    assert.doesNotMatch(error.message, new RegExp(fakeSecretValue))
    return error
  }
}

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
    assert.equal(blankError.code, 'A3_SIGNING_CONFIG_MISSING')
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
  for (const endpoint of ['http://example.test/', 'not a URL']) {
    const error = captureConfigurationError(() =>
      loadSignedReleaseEnvironment({ ...validEnvironment, AZURE_TRUSTED_SIGNING_ENDPOINT: endpoint }),
    )
    assert.equal(error.code, 'A3_SIGNING_ENDPOINT_INVALID')
  }
})

test('signed release environment trims and freezes validated values', () => {
  const values = loadSignedReleaseEnvironment({
    ...validEnvironment,
    AZURE_CODE_SIGNING_ACCOUNT_NAME: '  a3-signing  ',
  })

  assert.equal(values.AZURE_CODE_SIGNING_ACCOUNT_NAME, 'a3-signing')
  assert.equal(Object.isFrozen(values), true)
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
