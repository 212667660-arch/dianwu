import fs from 'node:fs/promises'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

export const MODEL_PROFILE_VAULT_VERSION = 2

const PROFILE_FIELDS = new Set(['id', 'label', 'enabled', 'provider', 'base_url', 'api_key', 'anthropic_version', 'request_timeout_seconds', 'default_model_id', 'models'])
const MODEL_FIELDS = new Set(['id', 'provider_model_name', 'label', 'max_output_tokens', 'supported_reasoning_efforts', 'reasoning_adapter'])
const EFFORTS = new Set(['auto', 'off', 'low', 'medium', 'high', 'xhigh'])
const ADAPTERS = new Set(['none', 'openai_reasoning_effort', 'anthropic_thinking'])

export function createModelProfileVault({ safeStorage, filePath, legacyStore = null, fsImpl = fs }) {
  if (!safeStorage || typeof filePath !== 'string' || !filePath) throw new TypeError('Model profile vault requires safeStorage and filePath.')

  return { load, snapshot, save, restore }

  async function load() {
    let bytes
    try {
      bytes = await fsImpl.readFile(filePath)
    } catch (error) {
      if (error?.code !== 'ENOENT') throw vaultError()
      const legacy = legacyStore ? await legacyStore.load() : null
      return legacy ? migrateLegacy(legacy) : emptyVault()
    }
    try {
      const envelope = JSON.parse(bytes.toString('utf8'))
      if (envelope?.version !== 2 || typeof envelope.payload !== 'string') throw new Error('invalid envelope')
      const encrypted = decodeBase64(envelope.payload)
      return normalizeVault(JSON.parse(safeStorage.decryptString(encrypted)))
    } catch {
      throw vaultError()
    }
  }

  async function snapshot() {
    try { return await fsImpl.readFile(filePath) } catch (error) {
      if (error?.code === 'ENOENT') return null
      throw vaultError()
    }
  }

  async function save(input) {
    if (safeStorage.isEncryptionAvailable?.() !== true) throw Object.assign(new Error('当前系统无法安全保存模型凭据。'), { code: 'MODEL_CREDENTIAL_STORE_UNAVAILABLE' })
    let value
    try { value = normalizeVault(input) } catch { throw vaultError() }
    let encrypted
    try { encrypted = safeStorage.encryptString(JSON.stringify(value)) } catch { throw Object.assign(new Error('当前系统无法安全保存模型凭据。'), { code: 'MODEL_CREDENTIAL_STORE_UNAVAILABLE' }) }
    await writeAtomic(Buffer.from(JSON.stringify({ version: 2, payload: Buffer.from(encrypted).toString('base64') }), 'utf8'))
    return value
  }

  async function restore(bytes) {
    if (bytes === null) return fsImpl.rm(filePath, { force: true })
    if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) throw new TypeError('Vault snapshot must be bytes or null.')
    await writeAtomic(Buffer.from(bytes))
  }

  async function writeAtomic(bytes) {
    await fsImpl.mkdir(path.dirname(filePath), { recursive: true })
    const temporary = `${filePath}.${randomUUID()}.tmp`
    try {
      await fsImpl.writeFile(temporary, bytes, { flag: 'wx' })
      await fsImpl.rename(temporary, filePath)
    } finally {
      await fsImpl.rm(temporary, { force: true }).catch(() => {})
    }
  }
}

function emptyVault() {
  return { version: 2, global: { default_profile_id: null, auto_failover: true, fallback_profile_ids: [] }, profiles: [] }
}

function migrateLegacy(value) {
  const profileId = 'legacy-profile'
  return normalizeVault({
    version: 2,
    global: { default_profile_id: profileId, auto_failover: true, fallback_profile_ids: [] },
    profiles: [{
      id: profileId, label: '原模型配置', enabled: true, provider: value.provider,
      base_url: value.base_url, api_key: value.api_key, anthropic_version: value.anthropic_version,
      request_timeout_seconds: value.request_timeout_seconds, default_model_id: 'legacy-model',
      models: [{ id: 'legacy-model', provider_model_name: value.model_name, label: value.model_name, max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'], reasoning_adapter: 'none' }],
    }],
  })
}

function normalizeVault(input) {
  plain(input, new Set(['version', 'global', 'profiles']))
  if (input.version !== 2) throw new TypeError('invalid version')
  plain(input.global, new Set(['default_profile_id', 'auto_failover', 'fallback_profile_ids']))
  if (typeof input.global.auto_failover !== 'boolean' || !Array.isArray(input.global.fallback_profile_ids) || !Array.isArray(input.profiles) || input.profiles.length > 16) throw new TypeError('invalid vault')
  const profiles = input.profiles.map(normalizeProfile)
  const ids = profiles.map(value => value.id)
  unique(ids)
  let defaultId = input.global.default_profile_id
  if (defaultId === null && profiles.length) defaultId = profiles[0].id
  if (!profiles.length && (defaultId !== null || input.global.fallback_profile_ids.length)) throw new TypeError('invalid empty vault')
  const byId = new Map(profiles.map(value => [value.id, value]))
  if (profiles.length && (!byId.has(defaultId) || !byId.get(defaultId).enabled)) throw new TypeError('invalid default')
  const fallbacks = input.global.fallback_profile_ids.map(id)
  unique(fallbacks)
  if (fallbacks.some(value => value === defaultId || !byId.has(value))) throw new TypeError('invalid fallback')
  return { version: 2, global: { default_profile_id: defaultId, auto_failover: input.global.auto_failover, fallback_profile_ids: fallbacks }, profiles }
}

function normalizeProfile(input) {
  plain(input, PROFILE_FIELDS)
  const provider = text(input.provider, 1, 16)
  if (!['openai', 'anthropic'].includes(provider) || typeof input.enabled !== 'boolean' || !Array.isArray(input.models) || !input.models.length || input.models.length > 64) throw new TypeError('invalid profile')
  const models = input.models.map(normalizeModel)
  unique(models.map(value => value.id))
  const defaultModelId = id(input.default_model_id, 128, true)
  if (!models.some(value => value.id === defaultModelId)) throw new TypeError('invalid default model')
  const timeout = Number(input.request_timeout_seconds)
  if (!Number.isFinite(timeout) || timeout < 5 || timeout > 300) throw new TypeError('invalid timeout')
  return { id: id(input.id, 64), label: text(input.label, 1, 64), enabled: input.enabled, provider, base_url: text(input.base_url, 8, 512), api_key: text(input.api_key, 1, 512), anthropic_version: text(input.anthropic_version, 1, 32), request_timeout_seconds: timeout, default_model_id: defaultModelId, models }
}

function normalizeModel(input) {
  plain(input, MODEL_FIELDS)
  if (!Array.isArray(input.supported_reasoning_efforts) || !input.supported_reasoning_efforts.includes('auto')) throw new TypeError('invalid efforts')
  const efforts = input.supported_reasoning_efforts.map(value => { if (!EFFORTS.has(value)) throw new TypeError('invalid effort'); return value })
  unique(efforts)
  if (!ADAPTERS.has(input.reasoning_adapter)) throw new TypeError('invalid adapter')
  const maxTokens = Number(input.max_output_tokens)
  if (!Number.isInteger(maxTokens) || maxTokens < 512 || maxTokens > 32768) throw new TypeError('invalid tokens')
  return { id: id(input.id, 128, true), provider_model_name: text(input.provider_model_name, 1, 128), label: text(input.label, 1, 128), max_output_tokens: maxTokens, supported_reasoning_efforts: efforts, reasoning_adapter: input.reasoning_adapter }
}

function plain(value, fields) {
  if (value === null || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !fields.has(key))) throw new TypeError('unsupported field')
}
function text(value, min, max) { if (typeof value !== 'string') throw new TypeError('invalid string'); const result = value.trim(); if (result.length < min || result.length > max || /[\0\r\n]/.test(result)) throw new TypeError('invalid string'); return result }
function id(value, max, model = false) { const result = text(value, 1, max); const pattern = model ? /^[A-Za-z0-9._:-]+$/ : /^[A-Za-z0-9_-]+$/; if (!pattern.test(result)) throw new TypeError('invalid id'); return result }
function unique(values) { if (new Set(values).size !== values.length) throw new TypeError('duplicate id') }
function decodeBase64(value) { if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) throw new TypeError('invalid base64'); return Buffer.from(value, 'base64') }
function vaultError() { return Object.assign(new Error('模型凭据存储内容无效。'), { code: 'MODEL_CREDENTIAL_STORE_INVALID' }) }
