import type { ModelConfigInput, StreamEvent } from './types'

export interface TransportRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  path: string
  query?: Record<string, string | number | boolean>
  body?: unknown
}

export interface DesktopError {
  code: string
  message: string
  retryable: boolean
  requestId?: string
}

export interface BackendErrorEnvelope {
  code: string
  message: string
  retryable: boolean
  request_id?: string
}

export type DesktopResponse =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: DesktopError }

export type DesktopStreamMessage =
  | { streamId: string; type: 'event'; event: StreamEvent }
  | { streamId: string; type: 'done' }
  | { streamId: string; type: 'error'; status?: number; error: DesktopError }

export interface DesktopBridge {
  request(input: TransportRequest): Promise<DesktopResponse>
  modelConfigTest(input: ModelConfigInput): Promise<DesktopResponse>
  modelConfigSave(input: ModelConfigInput): Promise<DesktopResponse>
  startStream(streamId: string, input: TransportRequest): void
  cancelStream(streamId: string): void
  onStreamEvent(listener: (message: DesktopStreamMessage) => void): () => void
  onBackendExit(listener: (payload: { code: number | null }) => void): () => void
}

export class BackendApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryable: boolean
  readonly requestId?: string

  constructor(
    status: number,
    code: string,
    message: string,
    retryable = false,
    requestId?: string,
  ) {
    super(message)
    this.name = 'BackendApiError'
    this.status = status
    this.code = code
    this.retryable = retryable
    this.requestId = requestId
  }
}

export { BackendApiError as DesktopApiError }

export function backendApiErrorFromEnvelope(status: number, value: unknown): BackendApiError {
  if (isBackendErrorEnvelope(value)) {
    return new BackendApiError(status, value.code, value.message, value.retryable, value.request_id)
  }
  return new BackendApiError(
    status,
    'BACKEND_HTTP_ERROR',
    '服务请求未成功，请稍后重试。',
    status >= 500,
  )
}

export function backendUnavailableError(): BackendApiError {
  return new BackendApiError(
    503,
    'BACKEND_UNAVAILABLE',
    '服务暂时不可用，请稍后重试。',
    true,
  )
}

export interface BackendTransport {
  request<T>(input: TransportRequest): Promise<T>
  stream(input: TransportRequest, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<void>
}

export async function desktopEnvelope<T>(response: DesktopResponse): Promise<T> {
  if (response.ok) return response.data as T
  throw new BackendApiError(
    response.status,
    response.error.code,
    response.error.message,
    response.error.retryable,
    response.error.requestId,
  )
}

function isBackendErrorEnvelope(value: unknown): value is BackendErrorEnvelope {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const candidate = value as Partial<BackendErrorEnvelope>
  return (
    typeof candidate.code === 'string'
    && candidate.code.length > 0
    && typeof candidate.message === 'string'
    && candidate.message.length > 0
    && typeof candidate.retryable === 'boolean'
    && (candidate.request_id === undefined || typeof candidate.request_id === 'string')
  )
}
