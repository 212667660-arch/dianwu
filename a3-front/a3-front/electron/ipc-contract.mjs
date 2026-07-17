const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
const GENERATION_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/
const BUNDLE_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
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
const MODEL_PROFILE_FIELDS = new Set(['id', 'label', 'enabled', 'provider', 'base_url', 'api_key', 'anthropic_version', 'request_timeout_seconds', 'default_model_id', 'models'])
const MODEL_DEFINITION_FIELDS = new Set(['id', 'provider_model_name', 'label', 'max_output_tokens', 'supported_reasoning_efforts', 'reasoning_adapter'])
const MODEL_PROFILE_POLICY_FIELDS = new Set(['default_profile_id', 'auto_failover', 'fallback_profile_ids'])
const MODEL_PROFILE_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/
const MODEL_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/
const REASONING_EFFORTS = new Set(['auto', 'off', 'low', 'medium', 'high', 'xhigh'])
const REASONING_ADAPTERS = new Set(['none', 'openai_reasoning_effort', 'anthropic_thinking'])
const KNOWLEDGE_DROPPED_FIELDS = new Set(['collectionId', 'paths'])
const KNOWLEDGE_BULK_FIELDS = new Set(['action', 'document_ids', 'collection_ids', 'tags', 'favorite'])
const KNOWLEDGE_BULK_ACTIONS = new Set([
  'move_to_trash',
  'restore',
  'purge',
  'add_to_collections',
  'remove_from_collections',
  'favorite',
  'set_tags',
])
const KNOWLEDGE_LOCATOR_FIELDS = new Set(['type', 'start', 'end', 'sheet_name'])
const KNOWLEDGE_LOCATOR_TYPES = new Set(['page', 'slide', 'sheet_rows', 'paragraph'])
const TEXTBOOK_OPEN_FIELDS = new Set(['sourceId'])
const TEXTBOOK_SOURCE_ID_PATTERN = /^[a-z0-9][a-z0-9-]{2,63}$/
const TEXTBOOK_OFFICIAL_URLS = Object.freeze({
  'pep-junior-math': 'https://jc.pep.com.cn/?filed=%E5%88%9D%E4%B8%AD&subject=%E6%95%B0%E5%AD%A6',
  'pep-high-math': 'https://jc.pep.com.cn/?filed=%E9%AB%98%E4%B8%AD&subject=%E6%95%B0%E5%AD%A6',
})
const PET_SETTINGS_FIELDS = new Set(['visible', 'alwaysOnTop', 'scale', 'speed', 'soundEnabled', 'soundVolume', 'voiceEnabled', 'voiceVolume'])
const PET_SCALE_VALUES = new Set([0.5, 0.75, 1, 1.25, 1.5])
const PET_SPEED_VALUES = new Set([0.5, 0.75, 1, 1.25, 1.5, 2])
const PET_VOLUME_VALUES = new Set([0, 0.25, 0.5, 0.75, 1])
const PET_TASK_STATES = new Set(['idle', 'running', 'waiting', 'review', 'failed'])
const CHAT_BODY_FIELDS = new Set(['session_id', 'message', 'resource_mode', 'resource_type'])
const RESOURCE_MODES = new Set(['bundle', 'single'])
const ARTIFACT_TYPES = new Set(['course_explanation', 'mind_map', 'question_bank', 'extended_reading', 'adaptive_practice'])
const RETRY_BODY_FIELDS = new Set(['session_id'])

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

export function validateModelProfileId(value) {
  if (typeof value !== 'string' || !MODEL_PROFILE_ID_PATTERN.test(value)) {
    return invalid('Model profile ID is invalid.')
  }
  return { ok: true, value }
}

export function validateModelProfileInput(input) {
  if (!isPlainObject(input)) return invalid('Model profile must be an object.')
  for (const field of Object.keys(input)) {
    if (!MODEL_PROFILE_FIELDS.has(field)) return denied('Model profile contains an unsupported field.')
  }

  const profileId = validateModelProfileId(input.id)
  if (!profileId.ok) return profileId
  const label = normalizedString(input.label, 1, 64)
  const apiKey = normalizedString(input.api_key, 0, 512)
  const baseUrl = normalizedHttpUrl(input.base_url)
  const anthropicVersion = normalizedString(input.anthropic_version, 1, 32)
  const timeout = input.request_timeout_seconds
  if (
    label === null
    || typeof input.enabled !== 'boolean'
    || !['openai', 'anthropic'].includes(input.provider)
    || baseUrl === null
    || apiKey === null
    || anthropicVersion === null
    || typeof timeout !== 'number'
    || !Number.isFinite(timeout)
    || timeout < 5
    || timeout > 300
    || !MODEL_ID_PATTERN.test(input.default_model_id ?? '')
    || !Array.isArray(input.models)
    || input.models.length < 1
    || input.models.length > 64
  ) return invalid('Model profile is invalid.')

  const models = []
  for (const model of input.models) {
    const result = validateModelDefinition(model)
    if (!result.ok) return result
    models.push(result.value)
  }
  const modelIds = models.map(model => model.id)
  if (new Set(modelIds).size !== modelIds.length || !modelIds.includes(input.default_model_id)) {
    return invalid('Model profile default model is invalid.')
  }

  return {
    ok: true,
    value: {
      id: profileId.value,
      label,
      enabled: input.enabled,
      provider: input.provider,
      base_url: baseUrl,
      api_key: apiKey,
      anthropic_version: anthropicVersion,
      request_timeout_seconds: timeout,
      default_model_id: input.default_model_id,
      models,
    },
  }
}

export function validateModelProfilePolicyInput(input) {
  if (!isPlainObject(input)) return invalid('Model profile policy must be an object.')
  for (const field of Object.keys(input)) {
    if (!MODEL_PROFILE_POLICY_FIELDS.has(field)) return denied('Model profile policy contains an unsupported field.')
  }
  if (
    !Object.hasOwn(input, 'default_profile_id')
    || !Object.hasOwn(input, 'auto_failover')
    || !Object.hasOwn(input, 'fallback_profile_ids')
    || typeof input.auto_failover !== 'boolean'
    || !Array.isArray(input.fallback_profile_ids)
    || input.fallback_profile_ids.length > 16
  ) return invalid('Model profile policy is invalid.')

  let defaultProfileId = null
  if (input.default_profile_id !== null) {
    const result = validateModelProfileId(input.default_profile_id)
    if (!result.ok) return result
    defaultProfileId = result.value
  }
  const fallbackProfileIds = []
  for (const value of input.fallback_profile_ids) {
    const result = validateModelProfileId(value)
    if (!result.ok) return result
    fallbackProfileIds.push(result.value)
  }
  if (
    new Set(fallbackProfileIds).size !== fallbackProfileIds.length
    || (defaultProfileId !== null && fallbackProfileIds.includes(defaultProfileId))
  ) return invalid('Model profile fallback order is invalid.')

  return {
    ok: true,
    value: {
      default_profile_id: defaultProfileId,
      auto_failover: input.auto_failover,
      fallback_profile_ids: fallbackProfileIds,
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

export function validateKnowledgeBulkInput(input) {
  if (!isPlainObject(input)) return invalid('Knowledge bulk input must be an object.')
  for (const field of Object.keys(input)) {
    if (!KNOWLEDGE_BULK_FIELDS.has(field)) {
      return denied('Knowledge bulk input contains an unsupported field.')
    }
  }
  if (!KNOWLEDGE_BULK_ACTIONS.has(input.action)) {
    return denied('Knowledge bulk action is not allowed.')
  }

  const documentIds = validateSortedUniquePositiveIds(input.document_ids, 1, 200)
  if (documentIds === null) return denied('Knowledge document IDs are invalid.')
  const collectionIds = input.collection_ids === undefined
    ? []
    : validateSortedUniquePositiveIds(input.collection_ids, 0, 50)
  if (collectionIds === null) return denied('Knowledge collection IDs are invalid.')

  const tags = input.tags === undefined ? [] : validateKnowledgeTags(input.tags)
  if (tags === null) return denied('Knowledge tags are invalid.')

  const needsCollections = input.action === 'add_to_collections' || input.action === 'remove_from_collections'
  if ((needsCollections && collectionIds.length === 0) || (!needsCollections && collectionIds.length > 0)) {
    return denied('Knowledge bulk collections do not match the action.')
  }
  if (input.action === 'favorite') {
    if (typeof input.favorite !== 'boolean') return denied('Knowledge favorite value is required.')
  } else if (input.favorite !== undefined) {
    return denied('Knowledge favorite value is not accepted for this action.')
  }
  if (input.action !== 'set_tags' && tags.length > 0) {
    return denied('Knowledge tags are not accepted for this action.')
  }

  return {
    ok: true,
    value: {
      action: input.action,
      document_ids: documentIds,
      collection_ids: collectionIds,
      tags,
      ...(input.action === 'favorite' ? { favorite: input.favorite } : {}),
    },
  }
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

export function validateTextbookOpen(input) {
  if (!isPlainObject(input)) return invalid('Textbook open input must be an object.')
  for (const field of Object.keys(input)) {
    if (!TEXTBOOK_OPEN_FIELDS.has(field)) return denied('Textbook open input contains an unsupported field.')
  }
  if (!TEXTBOOK_SOURCE_ID_PATTERN.test(input.sourceId || '')) {
    return invalid('Textbook source ID is invalid.')
  }
  const url = TEXTBOOK_OFFICIAL_URLS[input.sourceId]
  if (!url) return denied('Textbook source ID is not approved.')
  return { ok: true, value: { sourceId: input.sourceId, url } }
}

export function validatePetSettingsInput(input) {
  if (!isPlainObject(input) || Object.keys(input).length === 0) {
    return invalid('Pet settings must be a non-empty object.')
  }
  for (const field of Object.keys(input)) {
    if (!PET_SETTINGS_FIELDS.has(field)) return denied('Pet settings contain an unsupported field.')
  }
  const value = {}
  if (Object.hasOwn(input, 'visible')) {
    if (typeof input.visible !== 'boolean') return invalid('Pet visibility is invalid.')
    value.visible = input.visible
  }
  if (Object.hasOwn(input, 'alwaysOnTop')) {
    if (typeof input.alwaysOnTop !== 'boolean') return invalid('Pet always-on-top setting is invalid.')
    value.alwaysOnTop = input.alwaysOnTop
  }
  if (Object.hasOwn(input, 'scale')) {
    if (!PET_SCALE_VALUES.has(input.scale)) return invalid('Pet scale is invalid.')
    value.scale = input.scale
  }
  if (Object.hasOwn(input, 'speed')) {
    if (!PET_SPEED_VALUES.has(input.speed)) return invalid('Pet speed is invalid.')
    value.speed = input.speed
  }
  for (const field of ['soundEnabled', 'voiceEnabled']) {
    if (Object.hasOwn(input, field)) {
      if (typeof input[field] !== 'boolean') return invalid(`Pet ${field} is invalid.`)
      value[field] = input[field]
    }
  }
  for (const field of ['soundVolume', 'voiceVolume']) {
    if (Object.hasOwn(input, field)) {
      if (!PET_VOLUME_VALUES.has(input[field])) return invalid(`Pet ${field} is invalid.`)
      value[field] = input[field]
    }
  }
  return { ok: true, value }
}

export function validatePetTaskStateInput(input) {
  return PET_TASK_STATES.has(input)
    ? { ok: true, value: input }
    : invalid('Pet task state is invalid.')
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

  let normalizedBody = input.body
  if (route.kind === 'chat' || route.kind === 'chat-stream') {
    const chatBody = validateChatBody(input.body)
    if (!chatBody.ok) return chatBody
    normalizedBody = chatBody.value
  } else if (route.kind === 'artifact-retry') {
    const retryBody = validateRetryBody(input.body)
    if (!retryBody.ok) return retryBody
    normalizedBody = retryBody.value
  } else if (route.kind === 'knowledge-import-retry' && input.body !== undefined) {
    return denied('Knowledge OCR retry does not accept a request body.')
  } else if (route.kind === 'knowledge-bulk') {
    const knowledgeBulkBody = validateKnowledgeBulkInput(input.body)
    if (!knowledgeBulkBody.ok) return knowledgeBulkBody
    normalizedBody = knowledgeBulkBody.value
  }

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
    body: normalizedBody,
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
  if (
    (method === 'GET' && (
      path === '/api/knowledge/status'
      || path === '/api/knowledge/textbooks'
      || path === '/api/knowledge/collections'
      || path === '/api/knowledge/documents'
      || path === '/api/knowledge/imports'
    ))
    || (method === 'POST' && (
      path === '/api/knowledge/collections'
      || path === '/api/knowledge/imports'
      || path === '/api/knowledge/search'
    ))
  ) {
    return { ok: true, kind: 'knowledge-static' }
  }
  if (method === 'POST' && path === '/api/knowledge/documents/bulk') {
    return { ok: true, kind: 'knowledge-bulk' }
  }

  const knowledgeCollectionMatch = /^\/api\/knowledge\/collections\/([1-9]\d*)$/.exec(path)
  if (knowledgeCollectionMatch && ['GET', 'PUT', 'DELETE'].includes(method)) {
    return { ok: true, kind: 'knowledge-collection' }
  }
  const knowledgeDocumentMatch = /^\/api\/knowledge\/documents\/([1-9]\d*)$/.exec(path)
  if (knowledgeDocumentMatch && ['GET', 'DELETE'].includes(method)) {
    return { ok: true, kind: 'knowledge-document' }
  }
  const knowledgeRebuildMatch = /^\/api\/knowledge\/documents\/([1-9]\d*)\/rebuild$/.exec(path)
  if (method === 'POST' && knowledgeRebuildMatch) {
    return { ok: true, kind: 'knowledge-rebuild' }
  }
  const knowledgeImportMatch = /^\/api\/knowledge\/imports\/([1-9]\d*)$/.exec(path)
  if (knowledgeImportMatch && ['GET', 'DELETE'].includes(method)) {
    return { ok: true, kind: 'knowledge-import' }
  }
  const knowledgeImportRetryMatch = /^\/api\/knowledge\/imports\/([1-9]\d*)\/retry$/.exec(path)
  if (knowledgeImportRetryMatch && method === 'POST') {
    return { ok: true, kind: 'knowledge-import-retry' }
  }

  const sessionMatch = /^\/api\/sessions\/([^/]+)(?:\/(progress|next-action|reviews|mistakes))?$/.exec(path)
  if (method === 'GET' && sessionMatch && SESSION_ID_PATTERN.test(sessionMatch[1])) {
    return { ok: true, kind: 'session-read' }
  }

  const rediagnoseMatch = /^\/api\/sessions\/([^/]+)\/rediagnose$/.exec(path)
  if (method === 'POST' && rediagnoseMatch && SESSION_ID_PATTERN.test(rediagnoseMatch[1])) {
    return { ok: true, kind: 'rediagnose' }
  }

  const knowledgeBindingMatch = /^\/api\/sessions\/([^/]+)\/knowledge-collections$/.exec(path)
  if (
    knowledgeBindingMatch
    && SESSION_ID_PATTERN.test(knowledgeBindingMatch[1])
    && ['GET', 'PUT'].includes(method)
  ) {
    return { ok: true, kind: 'knowledge-binding' }
  }

  const modelPreferenceMatch = /^\/api\/sessions\/([^/]+)\/model-preference$/.exec(path)
  if (
    modelPreferenceMatch
    && SESSION_ID_PATTERN.test(modelPreferenceMatch[1])
    && ['GET', 'PUT'].includes(method)
  ) {
    return { ok: true, kind: 'model-preference' }
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

  const artifactRetryMatch = /^\/api\/resource-bundles\/([^/]+)\/artifacts\/([^/]+)\/retry$/.exec(path)
  if (
    method === 'POST'
    && artifactRetryMatch
    && BUNDLE_ID_PATTERN.test(artifactRetryMatch[1])
    && ARTIFACT_TYPES.has(artifactRetryMatch[2])
  ) {
    return { ok: true, kind: 'artifact-retry' }
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

function validateSortedUniquePositiveIds(value, minimum, maximum) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) return null
  if (value.some(item => !Number.isSafeInteger(item) || item < 1)) return null
  if (value.some((item, index) => index > 0 && value[index - 1] >= item)) return null
  return [...value]
}

function validateKnowledgeTags(value) {
  if (!Array.isArray(value) || value.length > 20) return null
  const tags = []
  for (const item of value) {
    if (typeof item !== 'string' || item.length < 1 || item.length > 40 || item.trim() !== item) return null
    tags.push(item)
  }
  const keys = tags.map(item => item.toLocaleLowerCase('en-US'))
  if (new Set(keys).size !== keys.length || keys.some((item, index) => index > 0 && keys[index - 1] >= item)) {
    return null
  }
  return tags
}

function validateChatBody(body) {
  if (!isPlainObject(body)) return invalid('Chat body must be an object.')
  for (const field of Object.keys(body)) {
    if (!CHAT_BODY_FIELDS.has(field)) return denied('Chat body contains an unsupported field.')
  }
  const sessionId = normalizedString(body.session_id, 1, 64)
  const message = normalizedString(body.message, 1, 8_000)
  if (sessionId === null || !SESSION_ID_PATTERN.test(sessionId) || message === null) {
    return invalid('Chat body is invalid.')
  }
  const mode = body.resource_mode
  const type = body.resource_type
  if (mode === undefined && type === undefined) {
    return { ok: true, value: { session_id: sessionId, message } }
  }
  if (!RESOURCE_MODES.has(mode)) return invalid('Chat resource mode is invalid.')
  if (mode === 'bundle') {
    if (type !== undefined) return invalid('Bundle mode does not accept resource_type.')
    return { ok: true, value: { session_id: sessionId, message, resource_mode: mode } }
  }
  if (!ARTIFACT_TYPES.has(type)) return invalid('Single mode resource_type is invalid.')
  return {
    ok: true,
    value: { session_id: sessionId, message, resource_mode: mode, resource_type: type },
  }
}

function validateRetryBody(body) {
  if (!isPlainObject(body)) return invalid('Artifact retry body must be an object.')
  for (const field of Object.keys(body)) {
    if (!RETRY_BODY_FIELDS.has(field)) return denied('Artifact retry body contains an unsupported field.')
  }
  const sessionId = normalizedString(body.session_id, 1, 64)
  if (sessionId === null || !SESSION_ID_PATTERN.test(sessionId)) {
    return invalid('Artifact retry session_id is invalid.')
  }
  return { ok: true, value: { session_id: sessionId } }
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

function normalizedHttpUrl(value) {
  const normalized = normalizedString(value, 8, 512)
  if (normalized === null) return null
  try {
    const parsed = new URL(normalized)
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password
      ? normalized
      : null
  } catch {
    return null
  }
}

function validateModelDefinition(input) {
  if (!isPlainObject(input)) return invalid('Model definition must be an object.')
  for (const field of Object.keys(input)) {
    if (!MODEL_DEFINITION_FIELDS.has(field)) return denied('Model definition contains an unsupported field.')
  }
  const providerModelName = normalizedString(input.provider_model_name, 1, 128)
  const label = normalizedString(input.label, 1, 128)
  const efforts = input.supported_reasoning_efforts
  if (
    !MODEL_ID_PATTERN.test(input.id ?? '')
    || providerModelName === null
    || label === null
    || !Number.isInteger(input.max_output_tokens)
    || input.max_output_tokens < 512
    || input.max_output_tokens > 32_768
    || !Array.isArray(efforts)
    || efforts.length < 1
    || efforts.length > REASONING_EFFORTS.size
    || !efforts.includes('auto')
    || efforts.some(value => !REASONING_EFFORTS.has(value))
    || new Set(efforts).size !== efforts.length
    || !REASONING_ADAPTERS.has(input.reasoning_adapter)
  ) return invalid('Model definition is invalid.')
  return {
    ok: true,
    value: {
      id: input.id,
      provider_model_name: providerModelName,
      label,
      max_output_tokens: input.max_output_tokens,
      supported_reasoning_efforts: [...efforts],
      reasoning_adapter: input.reasoning_adapter,
    },
  }
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
