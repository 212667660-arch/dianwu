const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
const GENERATION_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/
const QUESTION_ID_PATTERN = /^[1-9]\d*$/
const FORBIDDEN_TRANSPORT_FIELDS = ['headers', 'url', 'baseUrl', 'token']
const REQUEST_FIELDS = new Set(['method', 'path', 'query', 'body'])
const MAX_JSON_BODY_BYTES = 65_536
const MAX_ENCODED_QUERY_BYTES = 65_536
const VALIDATED_REQUEST = Symbol('validatedDesktopRequest')
const MODEL_CONFIG_FIELDS = new Set([
  'provider',
  'api_key',
  'base_url',
  'model_name',
  'anthropic_version',
  'request_timeout_seconds',
])
const KNOWLEDGE_DROPPED_FIELDS = new Set(['collectionId', 'paths'])
const KNOWLEDGE_LOCATOR_FIELDS = new Set(['type', 'start', 'end', 'sheet_name'])
const KNOWLEDGE_LOCATOR_TYPES = new Set(['page', 'slide', 'sheet_rows', 'paragraph'])

export function desktopError(code, message, retryable = false, requestId) {
  return {
    code,
    message,
    retryable: Boolean(retryable),
    ...(requestId === undefined ? {} : { requestId }),
  }
}

export function validateModelConfigInput(input) {
  if (!isPlainObject(input)) return invalid('Model config must be an object.')
  for (const field of Object.keys(input)) {
    if (!MODEL_CONFIG_FIELDS.has(field)) {
      return denied('Model config contains an unsupported field.')
    }
  }

  const provider = normalizedString(input.provider, 1, 16)
  const apiKey = normalizedString(input.api_key, 0, 512)
  const baseUrl = normalizedString(input.base_url, 8, 512)
  const modelName = normalizedString(input.model_name, 1, 128)
  const anthropicVersion = normalizedString(input.anthropic_version, 1, 32)
  const timeout = input.request_timeout_seconds
  if (
    (provider !== 'openai' && provider !== 'anthropic')
    || apiKey === null
    || baseUrl === null
    || modelName === null
    || anthropicVersion === null
    || typeof timeout !== 'number'
    || !Number.isFinite(timeout)
    || timeout < 5
    || timeout > 300
  ) {
    return invalid('Model config is invalid.')
  }
  try {
    const parsed = new URL(baseUrl)
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
      return invalid('Model base URL is invalid.')
    }
  } catch {
    return invalid('Model base URL is invalid.')
  }

  return {
    ok: true,
    value: {
      provider,
      api_key: apiKey,
      base_url: baseUrl,
      model_name: modelName,
      anthropic_version: anthropicVersion,
      request_timeout_seconds: timeout,
    },
  }
}

export function validateKnowledgeCollectionId(value) {
  if (!Number.isSafeInteger(value) || value < 1) {
    return invalid('Knowledge collection ID is invalid.')
  }
  return { ok: true, value }
}

export function validateKnowledgeDroppedPaths(input) {
  if (!isPlainObject(input)) return invalid('Knowledge drop input must be an object.')
  for (const field of Object.keys(input)) {
    if (!KNOWLEDGE_DROPPED_FIELDS.has(field)) {
      return denied('Knowledge drop input contains an unsupported field.')
    }
  }
  const collection = validateKnowledgeCollectionId(input.collectionId)
  if (!collection.ok) return collection
  if (!Array.isArray(input.paths) || input.paths.length < 1 || input.paths.length > 50) {
    return invalid('Knowledge drop paths must contain 1 to 50 files.')
  }
  const paths = []
  for (const value of input.paths) {
    if (typeof value !== 'string' || value.length < 1 || value.length > 32_767 || /[\0\r\n]/.test(value)) {
      return invalid('Knowledge drop path is invalid.')
    }
    paths.push(value)
  }
  return { ok: true, value: { collectionId: collection.value, paths } }
}

export function validateKnowledgeLocator(input) {
  if (!isPlainObject(input)) return invalid('Knowledge locator must be an object.')
  for (const field of Object.keys(input)) {
    if (!KNOWLEDGE_LOCATOR_FIELDS.has(field)) {
      return denied('Knowledge locator contains an unsupported field.')
    }
  }
  if (
    !KNOWLEDGE_LOCATOR_TYPES.has(input.type)
    || !Number.isSafeInteger(input.start)
    || !Number.isSafeInteger(input.end)
    || input.start < 1
    || input.end < input.start
  ) {
    return invalid('Knowledge locator range is invalid.')
  }
  const value = { type: input.type, start: input.start, end: input.end }
  if (input.type === 'sheet_rows') {
    const sheetName = normalizedString(input.sheet_name, 1, 128)
    if (sheetName === null) return invalid('Sheet row locator requires a sheet name.')
    value.sheet_name = sheetName
  } else if (input.sheet_name !== undefined) {
    return invalid('Only sheet row locators accept a sheet name.')
  }
  return { ok: true, value }
}

export function validateDesktopRequest(input, { stream = false } = {}) {
  if (!isPlainObject(input)) {
    return invalid('Request must be an object.')
  }

  for (const field of FORBIDDEN_TRANSPORT_FIELDS) {
    if (Object.hasOwn(input, field)) {
      return denied('Request contains a forbidden transport field.')
    }
  }
  for (const field of Object.keys(input)) {
    if (!REQUEST_FIELDS.has(field)) {
      return denied('Request contains an unsupported field.')
    }
  }

  if (typeof input.method !== 'string' || typeof input.path !== 'string') {
    return invalid('Request method and path are required.')
  }
  if (hasUnsafePathSyntax(input.path)) {
    return denied('Request path is unsafe.')
  }

  const queryResult = normalizeQuery(input.query)
  if (!queryResult.ok) return queryResult
  if (Buffer.byteLength(new URLSearchParams(queryResult.value).toString(), 'utf8') > MAX_ENCODED_QUERY_BYTES) {
    return invalid('Request query exceeds the size limit.')
  }

  const bodyResult = validateBody(input.body)
  if (!bodyResult.ok) return bodyResult

  const isStream = stream === true
  const method = input.method
  const path = input.path
  const route = matchAllowedRoute(method, path, isStream)
  if (!route.ok) return route

  if (route.kind === 'generation-cancel') {
    const queryKeys = Object.keys(queryResult.value)
    if (queryKeys.length === 0 || !Object.hasOwn(queryResult.value, 'session_id')) {
      return invalid('Generation cancellation requires session_id.')
    }
    if (queryKeys.length !== 1) {
      return denied('Generation cancellation only permits session_id.')
    }
    if (!SESSION_ID_PATTERN.test(queryResult.value.session_id)) {
      return invalid('Generation cancellation session_id is invalid.')
    }
  }

  const value = {
    method,
    path,
    query: queryResult.value,
    body: input.body,
    stream: isStream,
  }
  Object.defineProperty(value, VALIDATED_REQUEST, { value: true })
  return { ok: true, value }
}

export function isTrustedDesktopSender(event, mainWebContents, indexUrl) {
  const sender = event?.sender
  if (!sender || sender !== mainWebContents || typeof sender.isDestroyed !== 'function') return false
  try {
    if (sender.isDestroyed() !== false) return false
    const senderUrl = normalizeUrlWithoutHash(event?.senderFrame?.url)
    const trustedUrl = normalizeUrlWithoutHash(indexUrl)
    return senderUrl !== null && senderUrl === trustedUrl
  } catch {
    return false
  }
}

export function buildBackendUrl(baseUrl, request) {
  if (request?.[VALIDATED_REQUEST] !== true) {
    throw new TypeError('Backend URL requires a validated desktop request.')
  }
  const validated = validateDesktopRequest({
    method: request?.method,
    path: request?.path,
    query: request?.query,
    body: request?.body,
  }, { stream: request?.stream === true })
  if (!validated.ok) {
    throw new TypeError('Backend URL requires a validated desktop request.')
  }

  const backendUrl = new URL(baseUrl)
  const { path, query } = validated.value
  const queryString = new URLSearchParams(query).toString()
  const url = new URL(path, backendUrl)
  url.search = queryString
  return url.toString()
}

function matchAllowedRoute(method, path, stream) {
  if (method === 'GET' && (
    path === '/health/live'
    || path === '/health/ready'
    || path === '/api/settings/model'
  )) {
    return { ok: true, kind: 'static' }
  }
  if (method === 'POST' && path === '/api/chat') {
    return { ok: true, kind: 'chat' }
  }
  if (method === 'POST' && path === '/api/chat/stream') {
    return stream ? { ok: true, kind: 'chat-stream' } : denied('Streaming chat requires stream mode.')
  }

  const sessionMatch = /^\/api\/sessions\/([^/]+)(?:\/(progress|next-action|reviews|mistakes))?$/.exec(path)
  if (method === 'GET' && sessionMatch && SESSION_ID_PATTERN.test(sessionMatch[1])) {
    return { ok: true, kind: 'session-read' }
  }

  const rediagnoseMatch = /^\/api\/sessions\/([^/]+)\/rediagnose$/.exec(path)
  if (method === 'POST' && rediagnoseMatch && SESSION_ID_PATTERN.test(rediagnoseMatch[1])) {
    return { ok: true, kind: 'rediagnose' }
  }

  const attemptMatch = /^\/api\/sessions\/([^/]+)\/questions\/([^/]+)\/attempts$/.exec(path)
  if (
    method === 'POST'
    && attemptMatch
    && SESSION_ID_PATTERN.test(attemptMatch[1])
    && QUESTION_ID_PATTERN.test(attemptMatch[2])
  ) {
    return { ok: true, kind: 'attempt' }
  }

  const cancellationMatch = /^\/api\/generations\/([^/]+)$/.exec(path)
  if (method === 'DELETE' && cancellationMatch && GENERATION_ID_PATTERN.test(cancellationMatch[1])) {
    return { ok: true, kind: 'generation-cancel' }
  }

  return denied('Request method or route is not allowed.')
}

function normalizeQuery(query) {
  if (query === undefined) return { ok: true, value: {} }
  if (!isPlainObject(query)) return invalid('Request query must be an object.')

  const normalized = {}
  for (const [key, value] of Object.entries(query)) {
    if (
      typeof value !== 'string'
      && typeof value !== 'boolean'
      && !(typeof value === 'number' && Number.isFinite(value))
    ) {
      return invalid('Request query values must be strings, booleans, or finite numbers.')
    }
    Object.defineProperty(normalized, key, {
      configurable: true,
      enumerable: true,
      value: String(value),
      writable: true,
    })
  }
  return { ok: true, value: normalized }
}

function validateBody(body) {
  if (body === undefined) return { ok: true }
  if (typeof body === 'function' || typeof body === 'symbol' || typeof body === 'bigint') {
    return invalid('Request body must be JSON serializable.')
  }
  try {
    const json = JSON.stringify(body)
    if (json !== undefined && Buffer.byteLength(json, 'utf8') <= MAX_JSON_BODY_BYTES) {
      return { ok: true }
    }
  } catch {
    return invalid('Request body must be JSON serializable.')
  }
  return invalid('Request JSON body exceeds the size limit.')
}

function hasUnsafePathSyntax(path) {
  return (
    !path.startsWith('/')
    || path.includes('..')
    || path.includes('\\')
    || path.includes('#')
    || /%(?:2e|2f|5c)/i.test(path)
  )
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

function normalizedString(value, minLength, maxLength) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  if (
    normalized.length < minLength
    || normalized.length > maxLength
    || /[\0\r\n]/.test(normalized)
  ) return null
  return normalized
}

function normalizeUrlWithoutHash(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    url.hash = ''
    return url.href
  } catch {
    return null
  }
}

function denied(message) {
  return { ok: false, error: desktopError('DESKTOP_REQUEST_DENIED', message) }
}

function invalid(message) {
  return { ok: false, error: desktopError('DESKTOP_REQUEST_INVALID', message) }
}
