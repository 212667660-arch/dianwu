import {
  buildBackendUrl,
  desktopError,
  isTrustedDesktopSender,
  validateDesktopRequest,
} from './ipc-contract.mjs'

const MAX_RESPONSE_BODY_BYTES = 5 * 1024 * 1024
const MAX_SSE_EVENT_BYTES = 256 * 1024
const MAX_SSE_BUFFER_BYTES = 512 * 1024
const MAX_STREAMS_PER_OWNER = 4
const STREAM_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/
const SAFE_ERROR_NAMES = new Set(['AbortError', 'TypeError', 'Error'])

export function createBackendProxy({
  getRuntime,
  getMainWebContents,
  fetchImpl = fetch,
  log = async () => {},
} = {}) {
  const streams = new Map()

  return {
    request,
    startStream,
    cancelStream,
    cleanupWebContents,
    cleanupAll,
    activeStreamCount: () => streams.size,
  }

  async function request(event, input) {
    const runtime = getCurrentRuntime(getRuntime)
    const mainWebContents = getCurrentMainWebContents(getMainWebContents)
    if (!runtime || !isTrustedDesktopSender(event, mainWebContents, runtime.indexUrl)) {
      return requestDenied()
    }

    const validation = validateDesktopRequest(input)
    if (!validation.ok) {
      return { ok: false, status: 400, error: validation.error }
    }

    let response
    try {
      response = await fetchImpl(buildBackendUrl(runtime.baseUrl, validation.value), {
        method: validation.value.method,
        headers: buildHeaders(runtime.token, validation.value.body),
        ...(validation.value.body === undefined ? {} : { body: JSON.stringify(validation.value.body) }),
      })
    } catch (error) {
      await logFetchFailure(log, error)
      return backendUnavailable()
    }

    let body
    try {
      body = await readResponseBody(response)
    } catch {
      return invalidBackendResponse()
    }
    if (body.tooLarge) {
      return responseTooLarge()
    }

    const status = normalizeStatus(response?.status)
    if (status < 200 || status >= 300) {
      if (!hasJsonContentType(response)) return mapBackendFailure(status, '')
      return mapBackendFailure(status, body.text)
    }

    if (!hasJsonContentType(response)) return invalidBackendResponse()
    if (body.text.length === 0) {
      return { ok: true, status, data: null }
    }
    try {
      return { ok: true, status, data: JSON.parse(body.text) }
    } catch {
      return invalidBackendResponse()
    }
  }

  async function startStream(event, streamId, input) {
    const runtime = getCurrentRuntime(getRuntime)
    const mainWebContents = getCurrentMainWebContents(getMainWebContents)
    if (!runtime || !isTrustedDesktopSender(event, mainWebContents, runtime.indexUrl)) return

    if (typeof streamId !== 'string' || !STREAM_ID_PATTERN.test(streamId)) {
      sendStreamMessage(event.sender, streamId, streamInvalidId())
      return
    }
    const validation = validateDesktopRequest(input, { stream: true })
    if (!validation.ok) {
      sendStreamMessage(event.sender, streamId, streamError(validation.error))
      return
    }
    if (validation.value.method !== 'POST' || validation.value.path !== '/api/chat/stream') {
      sendStreamMessage(event.sender, streamId, streamError(desktopError(
        'DESKTOP_REQUEST_DENIED',
        '流式请求仅允许聊天流接口。',
      )))
      return
    }

    const owner = event.sender
    const key = streamKey(owner, streamId)
    if (streams.has(key)) {
      sendStreamMessage(owner, streamId, streamInvalidId())
      return
    }
    if (activeStreamsForOwner(streams, owner) >= MAX_STREAMS_PER_OWNER) {
      sendStreamMessage(owner, streamId, streamLimited())
      return
    }

    const stream = {
      key,
      owner,
      streamId,
      controller: new AbortController(),
      reader: null,
      body: null,
      notifyCancellation: false,
    }
    streams.set(key, stream)
    try {
      const response = await fetchImpl(buildBackendUrl(runtime.baseUrl, validation.value), {
        method: validation.value.method,
        headers: buildStreamHeaders(runtime.token, validation.value.body),
        ...(validation.value.body === undefined ? {} : { body: JSON.stringify(validation.value.body) }),
        signal: stream.controller.signal,
      })
      stream.body = response?.body ?? null
      if (stream.controller.signal.aborted) throw streamCancelled()

      const status = normalizeStatus(response?.status)
      if (status < 200 || status >= 300) {
        const failure = await streamHttpFailure(response, status)
        throw new StreamProxyError(failure.error, failure.status)
      }
      if (!hasEventStreamContentType(response)) throw new StreamProxyError(invalidStreamResponse())
      if (!response?.body?.getReader) throw new StreamProxyError(invalidStreamResponse())

      await forwardSseResponse(response.body, stream, event => {
        if (typeof event.generation_id === 'string') stream.generationId = event.generation_id
        sendStreamMessage(owner, streamId, { streamId, type: 'event', event })
      })
      if (stream.controller.signal.aborted) throw streamCancelled()
      sendStreamMessage(owner, streamId, { streamId, type: 'done' })
    } catch (error) {
      const safeFailure = streamSafeFailure(error)
      if (!stream.controller.signal.aborted || stream.notifyCancellation) {
        sendStreamMessage(owner, streamId, streamError(safeFailure.error, safeFailure.status))
      }
      await logStreamFailure(log, safeFailure.error)
    } finally {
      streams.delete(key)
    }
  }

  function cancelStream(event, streamId) {
    const runtime = getCurrentRuntime(getRuntime)
    const mainWebContents = getCurrentMainWebContents(getMainWebContents)
    if (!runtime || !isTrustedDesktopSender(event, mainWebContents, runtime.indexUrl)) return
    if (typeof streamId !== 'string') return

    const stream = streams.get(streamKey(event.sender, streamId))
    if (!stream || stream.owner !== event.sender) return
    stream.notifyCancellation = true
    abortStream(stream)
  }

  function cleanupWebContents(webContents) {
    for (const stream of [...streams.values()]) {
      if (stream.owner !== webContents) continue
      streams.delete(stream.key)
      abortStream(stream)
    }
  }

  function cleanupAll() {
    for (const stream of [...streams.values()]) {
      streams.delete(stream.key)
      abortStream(stream)
    }
  }
}

function getCurrentRuntime(getRuntime) {
  try {
    const runtime = getRuntime?.()
    if (
      !runtime
      || typeof runtime.baseUrl !== 'string'
      || typeof runtime.token !== 'string'
      || typeof runtime.indexUrl !== 'string'
    ) {
      return null
    }
    return runtime
  } catch {
    return null
  }
}

function getCurrentMainWebContents(getMainWebContents) {
  try {
    return getMainWebContents?.()
  } catch {
    return null
  }
}

function buildHeaders(token, body) {
  return {
    Accept: 'application/json',
    'X-A3-Desktop-Token': token,
    ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
  }
}

function buildStreamHeaders(token, body) {
  return {
    Accept: 'text/event-stream',
    'X-A3-Desktop-Token': token,
    ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
  }
}

function streamKey(webContents, streamId) {
  return `${webContents?.id ?? 'unknown'}:${streamId}`
}

function activeStreamsForOwner(streams, owner) {
  let count = 0
  for (const stream of streams.values()) {
    if (stream.owner === owner) count += 1
  }
  return count
}

function abortStream(stream) {
  try {
    stream.controller.abort()
  } catch {
    // The registry is still removed even when an upstream implementation rejects aborting.
  }
  void cancelReader(stream.reader)
  void cancelBody(stream.body)
}

function sendStreamMessage(webContents, streamId, message) {
  if (!isLiveWebContents(webContents)) return
  try {
    webContents.send('a3:stream-event', { ...message, streamId })
  } catch {
    // A destroyed renderer cannot receive a message and must not expose a main-process failure.
  }
}

function isLiveWebContents(webContents) {
  try {
    return Boolean(webContents && typeof webContents.isDestroyed === 'function' && webContents.isDestroyed() === false)
  } catch {
    return false
  }
}

async function forwardSseResponse(body, stream, onEvent) {
  const reader = body.getReader()
  stream.reader = reader
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  let bufferBytes = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (stream.controller.signal.aborted) throw streamCancelled()
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value)
      bufferBytes += chunk.byteLength
      if (bufferBytes > MAX_SSE_BUFFER_BYTES) {
        await cancelReader(reader)
        throw new StreamProxyError(invalidStreamResponse())
      }
      buffer += decoder.decode(chunk, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      bufferBytes = Buffer.byteLength(buffer, 'utf8')
      for (const block of blocks) {
        if (Buffer.byteLength(block, 'utf8') > MAX_SSE_EVENT_BYTES) {
          await cancelReader(reader)
          throw new StreamProxyError(invalidStreamResponse())
        }
        const event = parseSseBlock(block)
        if (event) onEvent(event)
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) {
      if (Buffer.byteLength(buffer, 'utf8') > MAX_SSE_EVENT_BYTES) throw new StreamProxyError(invalidStreamResponse())
      const event = parseSseBlock(buffer)
      if (event) onEvent(event)
    }
  } catch (error) {
    if (stream.controller.signal.aborted) throw streamCancelled()
    if (error instanceof StreamProxyError) throw error
    throw new StreamProxyError(invalidStreamResponse())
  } finally {
    stream.reader = null
    try {
      reader.releaseLock()
    } catch {
      // A reader may already have been released by a platform-specific stream implementation.
    }
  }
}

function parseSseBlock(block) {
  let eventName = 'message'
  const data = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }
  if (data.length === 0) return null
  try {
    const payload = JSON.parse(data.join('\n'))
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new TypeError('Invalid SSE payload')
    return { event: eventName, ...payload }
  } catch {
    throw new StreamProxyError(invalidStreamResponse())
  }
}

async function streamHttpFailure(response, status) {
  try {
    const body = await readResponseBody(response)
    if (body.tooLarge) return { status: 502, error: invalidStreamResponse() }
    const mapped = hasJsonContentType(response)
      ? mapBackendFailure(status, body.text)
      : mapBackendFailure(status, '')
    return { status: mapped.status, error: mapped.error }
  } catch {
    return { status: 502, error: invalidStreamResponse() }
  }
}

function hasEventStreamContentType(response) {
  try {
    const contentType = response?.headers?.get?.('content-type')
    return typeof contentType === 'string' && contentType.split(';', 1)[0].trim().toLowerCase() === 'text/event-stream'
  } catch {
    return false
  }
}

class StreamProxyError extends Error {
  constructor(error, status) {
    super(error.code)
    this.error = error
    this.status = status
  }
}

function streamSafeFailure(error) {
  if (error instanceof StreamProxyError) return { error: error.error, status: error.status }
  if (error instanceof DOMException && error.name === 'AbortError') return { error: streamCancelled() }
  return { error: backendUnavailable().error }
}

function streamError(error, status) {
  return {
    streamId: undefined,
    type: 'error',
    ...(status === undefined ? {} : { status }),
    error,
  }
}

function streamInvalidId() {
  return streamError(desktopError('DESKTOP_STREAM_INVALID', '流式请求标识无效。'))
}

function streamLimited() {
  return streamError(desktopError('DESKTOP_STREAM_LIMITED', '当前窗口的流式请求数量已达上限。', true))
}

function invalidStreamResponse() {
  return desktopError('DESKTOP_STREAM_INVALID', '流式响应数据无效。', true)
}

function streamCancelled() {
  return desktopError('DESKTOP_STREAM_CANCELLED', '生成已取消。')
}

async function logStreamFailure(log, error) {
  try {
    await log({ event: 'desktop-backend-stream-failed', code: error.code })
  } catch {
    // Stream error reporting must not alter the renderer-facing error envelope.
  }
}

async function readResponseBody(response) {
  const contentLength = Number(response?.headers?.get?.('content-length'))
  if (Number.isFinite(contentLength) && contentLength > MAX_RESPONSE_BODY_BYTES) {
    await cancelBody(response?.body)
    return { tooLarge: true }
  }

  const reader = response?.body?.getReader?.()
  if (!reader) return { text: '' }

  const decoder = new TextDecoder('utf-8', { fatal: true })
  let text = ''
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value)
      size += chunk.byteLength
      if (size > MAX_RESPONSE_BODY_BYTES) {
        await cancelReader(reader)
        return { tooLarge: true }
      }
      text += decoder.decode(chunk, { stream: true })
    }
    text += decoder.decode()
    return { text }
  } finally {
    reader.releaseLock()
  }
}

function hasJsonContentType(response) {
  try {
    const contentType = response?.headers?.get?.('content-type')
    if (typeof contentType !== 'string') return false
    const mediaType = contentType.split(';', 1)[0].trim().toLowerCase()
    return mediaType === 'application/json' || /^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+\+json$/.test(mediaType)
  } catch {
    return false
  }
}

function mapBackendFailure(status, text) {
  const structuredError = parseStructuredBackendError(text)
  if (structuredError) {
    return { ok: false, status, error: structuredError }
  }
  return {
    ok: false,
    status,
    error: desktopError(
      'DESKTOP_BACKEND_HTTP_ERROR',
      '本地服务请求未成功。',
      status === 408 || status === 429 || status >= 500,
    ),
  }
}

function parseStructuredBackendError(text) {
  try {
    const value = JSON.parse(text)
    if (
      !value
      || typeof value !== 'object'
      || Array.isArray(value)
      || typeof value.code !== 'string'
      || value.code.length === 0
      || typeof value.message !== 'string'
      || value.message.length === 0
      || typeof value.retryable !== 'boolean'
      || (value.request_id !== undefined && typeof value.request_id !== 'string')
    ) {
      return null
    }
    return desktopError(
      value.code,
      value.message,
      value.retryable,
      typeof value.request_id === 'string' ? value.request_id : undefined,
    )
  } catch {
    return null
  }
}

function normalizeStatus(status) {
  return Number.isInteger(status) && status >= 100 && status <= 599 ? status : 502
}

function requestDenied() {
  return {
    ok: false,
    status: 403,
    error: desktopError('DESKTOP_REQUEST_DENIED', '桌面请求未获授权。'),
  }
}

function backendUnavailable() {
  return {
    ok: false,
    status: 503,
    error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地服务暂时不可用，请稍后重试。', true),
  }
}

function responseTooLarge() {
  return {
    ok: false,
    status: 502,
    error: desktopError('DESKTOP_RESPONSE_TOO_LARGE', '本地服务响应过大，无法处理。'),
  }
}

function invalidBackendResponse() {
  return {
    ok: false,
    status: 502,
    error: desktopError('DESKTOP_BACKEND_RESPONSE_INVALID', '本地服务响应格式无效。', true),
  }
}

async function cancelBody(body) {
  try {
    await body?.cancel?.()
  } catch {
    // The size-limit outcome remains safe even when the upstream stream cannot be cancelled.
  }
}

async function cancelReader(reader) {
  try {
    await reader.cancel()
  } catch {
    // The size-limit outcome remains safe even when the upstream stream cannot be cancelled.
  }
}

async function logFetchFailure(log, error) {
  try {
    await log({
      event: 'desktop-backend-fetch-failed',
      errorName: classifyErrorName(error),
    })
  } catch {
    // Logging failures must not alter the renderer's safe error envelope.
  }
}

function classifyErrorName(error) {
  const name = typeof error?.name === 'string' ? error.name : ''
  return SAFE_ERROR_NAMES.has(name) ? name : 'UnknownError'
}
