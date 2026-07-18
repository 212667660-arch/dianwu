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
    if (!value) {
      throw configurationError(
        'A3_SIGNING_CONFIG_MISSING',
        `Missing required signing variable: ${name}`,
      )
    }
    values[name] = value
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
  if (endpoint.protocol !== 'https:') {
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
