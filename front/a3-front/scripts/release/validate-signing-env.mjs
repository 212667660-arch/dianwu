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
