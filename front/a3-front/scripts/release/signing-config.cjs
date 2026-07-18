const REQUIRED_VARIABLES = Object.freeze([
  'AZURE_TENANT_ID',
  'AZURE_CLIENT_ID',
  'AZURE_CLIENT_SECRET',
  'AZURE_TRUSTED_SIGNING_ENDPOINT',
  'AZURE_CODE_SIGNING_ACCOUNT_NAME',
  'AZURE_CERTIFICATE_PROFILE_NAME',
  'A3_EXPECTED_PUBLISHER',
])
const GUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const RESOURCE_NAME_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,62}[A-Za-z0-9])?$/
const TRUSTED_SIGNING_HOST_PATTERN = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.codesigning\.azure\.net$/
const PUBLISHER_MAX_LENGTH = 256
const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001F\u007F]/

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
    if (!value) {
      if (name === 'A3_EXPECTED_PUBLISHER' && environment[name] != null) {
        throw configurationError(
          'A3_SIGNING_PUBLISHER_INVALID',
          'A3_EXPECTED_PUBLISHER must be a bounded publisher name without control characters.',
        )
      }
      throw configurationError(
        'A3_SIGNING_CONFIG_MISSING',
        `Missing required signing variable: ${name}`,
      )
    }
    if (name !== 'AZURE_CLIENT_SECRET') values[name] = value
  }

  for (const name of ['AZURE_TENANT_ID', 'AZURE_CLIENT_ID']) {
    if (!GUID_PATTERN.test(values[name])) {
      throw configurationError('A3_SIGNING_ID_INVALID', `${name} must be a canonical GUID.`)
    }
  }

  for (const name of ['AZURE_CODE_SIGNING_ACCOUNT_NAME', 'AZURE_CERTIFICATE_PROFILE_NAME']) {
    if (!RESOURCE_NAME_PATTERN.test(values[name])) {
      throw configurationError(
        'A3_SIGNING_RESOURCE_NAME_INVALID',
        `${name} must use a shell-safe Azure resource name.`,
      )
    }
  }

  if (
    values.A3_EXPECTED_PUBLISHER.length > PUBLISHER_MAX_LENGTH ||
    CONTROL_CHARACTER_PATTERN.test(values.A3_EXPECTED_PUBLISHER)
  ) {
    throw configurationError(
      'A3_SIGNING_PUBLISHER_INVALID',
      'A3_EXPECTED_PUBLISHER must be a bounded publisher name without control characters.',
    )
  }

  let endpoint
  try {
    endpoint = new URL(values.AZURE_TRUSTED_SIGNING_ENDPOINT)
  } catch {
    throw configurationError(
      'A3_SIGNING_ENDPOINT_INVALID',
      'AZURE_TRUSTED_SIGNING_ENDPOINT must be a valid HTTPS URL.',
    )
  }
  if (
    endpoint.protocol !== 'https:' ||
    !TRUSTED_SIGNING_HOST_PATTERN.test(endpoint.hostname) ||
    endpoint.username !== '' ||
    endpoint.password !== '' ||
    endpoint.port !== '' ||
    endpoint.pathname !== '/' ||
    endpoint.search !== '' ||
    endpoint.hash !== ''
  ) {
    throw configurationError(
      'A3_SIGNING_ENDPOINT_INVALID',
      'AZURE_TRUSTED_SIGNING_ENDPOINT must be a valid HTTPS URL.',
    )
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
