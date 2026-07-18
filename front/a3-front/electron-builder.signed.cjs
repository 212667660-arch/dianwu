const packageJson = require('./package.json')
const { buildSignedConfig } = require('./scripts/release/signing-config.cjs')

module.exports = buildSignedConfig(packageJson.build, process.env)
