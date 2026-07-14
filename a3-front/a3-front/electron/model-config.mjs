import fs from 'node:fs/promises'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

export const MODEL_CONFIG_VERSION = 1

const CONFIG_FIELDS = new Set([
  'provider',
  'api_key',
  'base_url',
  'model_name',
  'anthropic_version',
  'request_timeout_seconds',
])

export function createModelConfigStore({ safeStorage, filePath, fsImpl = fs }) {
  if (!safeStorage || typeof filePath !== 'string' || !filePath) {
    throw new TypeError('Model config store requires safeStorage and filePath.')
  }

  return { load, snapshot, save, restore }

  async function load() {
    let bytes
    try {
      bytes = await fsImpl.readFile(filePath)
    } catch (error) {
      if (error?.code === 'ENOENT') return null
      throw credentialError('MODEL_CREDENTIAL_STORE_INVALID', '模型凭据存储无法读取。')
    }

    try {
      const envelope = JSON.parse(bytes.toString('utf8'))
      if (envelope?.version !== MODEL_CONFIG_VERSION || typeof envelope.payload !== 'string') {
        throw new Error('invalid envelope')
      }
      const encrypted = decodeBase64(envelope.payload)
      const decrypted = safeStorage.decryptString(encrypted)
      return normalizeModelConfig(JSON.parse(decrypted))
    } catch {
      throw credentialError('MODEL_CREDENTIAL_STORE_INVALID', '模型凭据存储内容无效。')
    }
  }

  async function snapshot() {
    try {
      return await fsImpl.readFile(filePath)
    } catch (error) {
      if (error?.code === 'ENOENT') return null
      throw credentialError('MODEL_CREDENTIAL_STORE_INVALID', '模型凭据存储无法读取。')
    }
  }

  async function save(input) {
    if (safeStorage.isEncryptionAvailable?.() !== true) {
      throw credentialError('MODEL_CREDENTIAL_STORE_UNAVAILABLE', '当前系统无法安全保存模型凭据。')
    }
    const value = normalizeModelConfig(input)
    let encrypted
    try {
      encrypted = safeStorage.encryptString(JSON.stringify(value))
    } catch {
      throw credentialError('MODEL_CREDENTIAL_STORE_UNAVAILABLE', '当前系统无法安全保存模型凭据。')
    }
    const envelope = Buffer.from(JSON.stringify({
      version: MODEL_CONFIG_VERSION,
      payload: Buffer.from(encrypted).toString('base64'),
    }), 'utf8')
    await writeAtomic(envelope)
    return value
  }

  async function restore(bytes) {
    if (bytes === null) {
      await fsImpl.rm(filePath, { force: true })
      return
    }
    if (!Buffer.isBuffer(bytes) && !(bytes instanceof Uint8Array)) {
      throw new TypeError('Model config snapshot must be bytes or null.')
    }
    await writeAtomic(Buffer.from(bytes))
  }

  async function writeAtomic(bytes) {
    await fsImpl.mkdir(path.dirname(filePath), { recursive: true })
    const temporaryPath = `${filePath}.${randomUUID()}.tmp`
    try {
      await fsImpl.writeFile(temporaryPath, bytes, { flag: 'wx' })
      await fsImpl.rename(temporaryPath, filePath)
    } finally {
      await fsImpl.rm(temporaryPath, { force: true }).catch(() => {})
    }
  }
}

export function modelEnvironment(input) {
  const value = normalizeModelConfig(input)
  return {
    MODEL_PROVIDER: value.provider,
    MODEL_API_KEY: value.api_key,
    MODEL_BASE_URL: value.base_url,
    MODEL_NAME: value.model_name,
    ANTHROPIC_VERSION: value.anthropic_version,
    REQUEST_TIMEOUT_SECONDS: String(value.request_timeout_seconds),
  }
}

function normalizeModelConfig(input) {
  if (!isPlainObject(input)) throw new TypeError('Model config must be an object.')
  for (const key of Object.keys(input)) {
    if (!CONFIG_FIELDS.has(key)) throw new TypeError('Model config contains an unsupported field.')
  }
  const provider = normalizeString(input.provider, 1, 16)
  if (provider !== 'openai' && provider !== 'anthropic') {
    throw new TypeError('Model provider is unsupported.')
  }
  const timeout = Number(input.request_timeout_seconds)
  if (!Number.isFinite(timeout) || timeout < 5 || timeout > 300) {
    throw new TypeError('Model request timeout is invalid.')
  }
  return {
    provider,
    api_key: normalizeString(input.api_key, 1, 512),
    base_url: normalizeString(input.base_url, 8, 512),
    model_name: normalizeString(input.model_name, 1, 128),
    anthropic_version: normalizeString(input.anthropic_version, 1, 32),
    request_timeout_seconds: timeout,
  }
}

function normalizeString(value, minLength, maxLength) {
  if (typeof value !== 'string') throw new TypeError('Model config string is invalid.')
  const normalized = value.trim()
  if (normalized.length < minLength || normalized.length > maxLength || /[\0\r\n]/.test(normalized)) {
    throw new TypeError('Model config string is invalid.')
  }
  return normalized
}

function decodeBase64(value) {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 !== 0) {
    throw new Error('invalid base64')
  }
  return Buffer.from(value, 'base64')
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function credentialError(code, message) {
  return Object.assign(new Error(message), { code })
}
