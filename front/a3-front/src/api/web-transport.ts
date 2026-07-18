import axios, { type AxiosInstance } from 'axios'

import type { StreamEvent } from './types'
import {
  BackendApiError,
  backendApiErrorFromEnvelope,
  backendUnavailableError,
  type BackendTransport,
  type TransportRequest,
} from './transport'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

const http = axios.create({
  baseURL: apiBaseUrl,
  timeout: 65_000,
  headers: { 'Content-Type': 'application/json' },
  validateStatus: () => true,
})

interface WebTransportOptions {
  httpClient?: Pick<AxiosInstance, 'request'>
  fetchImpl?: typeof fetch
}

export function createWebTransport({ httpClient = http, fetchImpl = fetch }: WebTransportOptions = {}): BackendTransport {
  return {
    async request<T>(input: TransportRequest) {
      try {
        const response = await httpClient.request<T>({
          method: input.method,
          url: input.path,
          params: input.query,
          data: input.body,
        })
        if (response.status < 200 || response.status >= 300) {
          throw backendApiErrorFromEnvelope(response.status, response.data)
        }
        return response.data
      } catch (error) {
        if (error instanceof BackendApiError) throw error
        throw backendUnavailableError()
      }
    },
    async stream(input: TransportRequest, onEvent: (event: StreamEvent) => void, signal?: AbortSignal) {
      const query = input.query ? `?${new URLSearchParams(serializeQuery(input.query)).toString()}` : ''
      let response: Response
      try {
        response = await fetchImpl(`${apiBaseUrl}${input.path}${query}`, {
          method: input.method,
          headers: input.body === undefined ? undefined : { 'Content-Type': 'application/json' },
          body: input.body === undefined ? undefined : JSON.stringify(input.body),
          signal,
        })
      } catch (error) {
        if (isAbortError(error)) throw error
        throw backendUnavailableError()
      }
      if (!response.ok) throw await parseError(response)
      if (!response.body) throw new Error('浏览器不支持流式响应')
      await readSseBody(response.body, onEvent)
    },
  }
}

function serializeQuery(query: NonNullable<TransportRequest['query']>) {
  return Object.fromEntries(Object.entries(query).map(([key, value]) => [key, String(value)]))
}

async function parseError(response: Response): Promise<Error> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON error bodies are intentionally not exposed to the renderer.
  }
  return backendApiErrorFromEnvelope(response.status, body)
}

export function parseSseBlock(block: string): StreamEvent | null {
  let eventName = 'message'
  const data: string[] = []
  block.split(/\r?\n/).forEach(line => {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trim())
  })
  if (!data.length) return null

  try {
    const payload = JSON.parse(data.join('\n')) as unknown
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('invalid payload')
    return { event: eventName, ...(payload as Omit<StreamEvent, 'event'>) }
  } catch {
    throw new Error('流式响应数据格式错误，请重新发送请求。')
  }
}

export async function readSseBody(body: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() || ''
      blocks.forEach(block => {
        const event = parseSseBlock(block)
        if (event) onEvent(event)
      })
    }
    buffer += decoder.decode()
    if (buffer.trim()) {
      const event = parseSseBlock(buffer)
      if (event) onEvent(event)
    }
  } finally {
    reader.releaseLock()
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof BackendApiError) return error.message
  return '请求失败，请稍后重试'
}

function isAbortError(error: unknown): boolean {
  return (error as { name?: unknown } | undefined)?.name === 'AbortError'
}
