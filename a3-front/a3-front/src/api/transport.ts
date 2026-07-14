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

export type DesktopResponse =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: DesktopError }

export type DesktopStreamMessage =
  | { streamId: string; type: 'event'; event: StreamEvent }
  | { streamId: string; type: 'done' }
  | { streamId: string; type: 'error'; error: DesktopError }

export interface DesktopBridge {
  request(input: TransportRequest): Promise<DesktopResponse>
  modelConfigTest(input: ModelConfigInput): Promise<DesktopResponse>
  modelConfigSave(input: ModelConfigInput): Promise<DesktopResponse>
  startStream(streamId: string, input: TransportRequest): void
  cancelStream(streamId: string): void
  onStreamEvent(listener: (message: DesktopStreamMessage) => void): () => void
  onBackendExit(listener: (payload: { code: number | null }) => void): () => void
}

export class DesktopApiError extends Error {
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
    this.name = 'DesktopApiError'
    this.status = status
    this.code = code
    this.retryable = retryable
    this.requestId = requestId
  }
}

export interface BackendTransport {
  request<T>(input: TransportRequest): Promise<T>
  stream(input: TransportRequest, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<void>
}

export async function desktopEnvelope<T>(response: DesktopResponse): Promise<T> {
  if (response.ok) return response.data as T
  throw new DesktopApiError(
    response.status,
    response.error.code,
    response.error.message,
    response.error.retryable,
    response.error.requestId,
  )
}
