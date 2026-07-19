import type { KnowledgeImportBatch, KnowledgeLocator, ModelConfigInput, ModelProfileInput, ModelProfilePolicy, PetSettings, PetTaskState, StreamEvent } from './types'
import { i18n } from '@/i18n'

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
  modelProfilesList?(): Promise<DesktopResponse>
  modelProfileTest?(input: ModelProfileInput): Promise<DesktopResponse>
  modelProfileUpsert?(input: ModelProfileInput): Promise<DesktopResponse>
  modelProfileDelete?(id: string): Promise<DesktopResponse>
  modelProfilePolicySave?(input: ModelProfilePolicy): Promise<DesktopResponse>
  modelRuntimeStatus?(): Promise<DesktopResponse>
  knowledgeChooseFiles?(collectionId: number): Promise<DesktopResponse>
  knowledgeImportDroppedFiles?(files: FileList | File[], collectionId: number): Promise<DesktopResponse>
  knowledgeRevealSource?(documentId: number): Promise<DesktopResponse>
  knowledgeOpenSource?(documentId: number, locator: KnowledgeLocator): Promise<DesktopResponse>
  knowledgeOpenOfficialTextbook?(sourceId: string): Promise<DesktopResponse>
  knowledgeOnImportProgress?(listener: (jobs: KnowledgeImportBatch['jobs']) => void): () => void
  petGet?(): Promise<DesktopResponse>
  petUpdateSettings?(input: Partial<PetSettings>): Promise<DesktopResponse>
  petSetTaskState?(state: PetTaskState): Promise<DesktopResponse>
  petChooseCharacter?(): Promise<DesktopResponse>
  petResetCharacter?(): Promise<DesktopResponse>
  desktopState?(): Promise<DesktopResponse>
  desktopCompleteOnboarding?(input: { offlineDemo: boolean }): Promise<DesktopResponse>
  desktopInfo?(): Promise<DesktopResponse>
  desktopDiagnostics?(): Promise<DesktopResponse>
  desktopExportDiagnostics?(): Promise<DesktopResponse>
  desktopCheckUpdates?(): Promise<DesktopResponse>
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
    i18n.global.t('errors.serviceRequestFailure'),
    status >= 500,
  )
}

export function backendUnavailableError(): BackendApiError {
  return new BackendApiError(
    503,
    'BACKEND_UNAVAILABLE',
    i18n.global.t('errors.serviceUnavailable'),
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
