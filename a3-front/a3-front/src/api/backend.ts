import { createDesktopTransport } from './desktop-transport'
import { desktopEnvelope, type BackendTransport } from './transport'
import { createWebTransport, parseSseBlock, readSseBody } from './web-transport'
import type {
  AttemptResponse,
  ChatResponse,
  HealthStatus,
  KnowledgeBinding,
  KnowledgeCollection,
  KnowledgeCollectionInput,
  KnowledgeDocument,
  KnowledgeImportBatch,
  KnowledgeImportJob,
  KnowledgeLocator,
  KnowledgeStatus,
  KnowledgeSearchResult,
  MistakeItem,
  ModelConfigInput,
  ModelConnectionTest,
  ModelSettings,
  NextAction,
  ProgressSnapshot,
  ReviewTask,
  SessionHistory,
  StreamEvent,
} from './types'

function activeTransport(): BackendTransport {
  if (window.a3Desktop) return createDesktopTransport(window.a3Desktop)
  return createWebTransport()
}

export { parseSseBlock, readSseBody }

export const backendApi = {
  async live() {
    return activeTransport().request<HealthStatus>({ method: 'GET', path: '/health/live' })
  },
  async ready() {
    return activeTransport().request<HealthStatus>({ method: 'GET', path: '/health/ready' })
  },
  async modelSettings() {
    return activeTransport().request<ModelSettings>({ method: 'GET', path: '/api/settings/model' })
  },
  async testModelSettings(input: ModelConfigInput) {
    if (window.a3Desktop) {
      return desktopEnvelope<ModelConnectionTest>(await window.a3Desktop.modelConfigTest(input))
    }
    return activeTransport().request<ModelConnectionTest>({
      method: 'POST', path: '/api/settings/model/test', body: input,
    })
  },
  async saveModelSettings(input: ModelConfigInput) {
    if (window.a3Desktop) {
      return desktopEnvelope<ModelSettings>(await window.a3Desktop.modelConfigSave(input))
    }
    return activeTransport().request<ModelSettings>({
      method: 'PUT', path: '/api/settings/model', body: input,
    })
  },
  async chat(sessionId: string, message: string) {
    return activeTransport().request<ChatResponse>({
      method: 'POST', path: '/api/chat', body: { session_id: sessionId, message },
    })
  },
  async streamChat(sessionId: string, message: string, onEvent: (event: StreamEvent) => void, signal?: AbortSignal) {
    return activeTransport().stream({
      method: 'POST',
      path: '/api/chat/stream',
      body: { session_id: sessionId, message },
    }, onEvent, signal)
  },
  async cancelGeneration(generationId: string, sessionId: string) {
    return activeTransport().request({
      method: 'DELETE',
      path: `/api/generations/${encodeURIComponent(generationId)}`,
      query: { session_id: sessionId },
    })
  },
  async session(sessionId: string) {
    return activeTransport().request<SessionHistory>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}`,
    })
  },
  async progress(sessionId: string) {
    return activeTransport().request<ProgressSnapshot>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/progress`,
    })
  },
  async nextAction(sessionId: string) {
    return activeTransport().request<NextAction>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/next-action`,
    })
  },
  async reviews(sessionId: string, dueOnly = false) {
    return activeTransport().request<ReviewTask[]>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/reviews`, query: { due_only: dueOnly },
    })
  },
  async mistakes(sessionId: string) {
    return activeTransport().request<MistakeItem[]>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/mistakes`,
    })
  },
  async submitAttempt(sessionId: string, questionId: number, answer: string, hintCount = 0) {
    return activeTransport().request<AttemptResponse>({
      method: 'POST',
      path: `/api/sessions/${encodeURIComponent(sessionId)}/questions/${questionId}/attempts`,
      body: { answer, hint_count: hintCount, idempotency_key: `web_${Date.now()}` },
    })
  },
  async rediagnose(sessionId: string) {
    return activeTransport().request({
      method: 'POST', path: `/api/sessions/${encodeURIComponent(sessionId)}/rediagnose`,
    })
  },
  async knowledgeStatus() { return activeTransport().request<KnowledgeStatus>({ method: 'GET', path: '/api/knowledge/status' }) },
  async knowledgeCollections() { return activeTransport().request<KnowledgeCollection[]>({ method: 'GET', path: '/api/knowledge/collections' }) },
  async createKnowledgeCollection(input: KnowledgeCollectionInput) { return activeTransport().request<KnowledgeCollection>({ method: 'POST', path: '/api/knowledge/collections', body: input }) },
  async updateKnowledgeCollection(collectionId: number, input: Partial<KnowledgeCollectionInput>) { return activeTransport().request<KnowledgeCollection>({ method: 'PUT', path: `/api/knowledge/collections/${collectionId}`, body: input }) },
  async deleteKnowledgeCollection(collectionId: number) { return activeTransport().request<void>({ method: 'DELETE', path: `/api/knowledge/collections/${collectionId}` }) },
  async knowledgeDocuments(collectionId?: number) { return activeTransport().request<KnowledgeDocument[]>({ method: 'GET', path: '/api/knowledge/documents', query: collectionId ? { collection_id: collectionId } : undefined }) },
  async knowledgeImports() { return activeTransport().request<KnowledgeImportJob[]>({ method: 'GET', path: '/api/knowledge/imports' }) },
  async searchKnowledge(sessionId: string, query: string, limit = 8) { return activeTransport().request<KnowledgeSearchResult>({ method: 'POST', path: '/api/knowledge/search', body: { session_id: sessionId, query, limit } }) },
  async sessionKnowledgeCollections(sessionId: string) { return activeTransport().request<KnowledgeBinding>({ method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/knowledge-collections` }) },
  async saveSessionKnowledgeCollections(sessionId: string, collectionIds: number[], privacyMode: KnowledgeBinding['privacy_mode'] = 'allow_model_context') { return activeTransport().request<KnowledgeBinding>({ method: 'PUT', path: `/api/sessions/${encodeURIComponent(sessionId)}/knowledge-collections`, body: { collection_ids: collectionIds, privacy_mode: privacyMode } }) },
  async chooseKnowledgeFiles(collectionId: number) {
    if (!window.a3Desktop?.knowledgeChooseFiles) throw new Error('文件导入仅桌面版可用。')
    return desktopEnvelope<KnowledgeImportBatch>(await window.a3Desktop.knowledgeChooseFiles(collectionId))
  },
  async importDroppedKnowledgeFiles(files: FileList | File[], collectionId: number) {
    if (!window.a3Desktop?.knowledgeImportDroppedFiles) throw new Error('文件导入仅桌面版可用。')
    return desktopEnvelope<KnowledgeImportBatch>(await window.a3Desktop.knowledgeImportDroppedFiles(files, collectionId))
  },
  async cancelKnowledgeImport(jobId: number) { return activeTransport().request<KnowledgeImportJob>({ method: 'DELETE', path: `/api/knowledge/imports/${jobId}` }) },
  async deleteKnowledgeDocument(documentId: number) { return activeTransport().request<void>({ method: 'DELETE', path: `/api/knowledge/documents/${documentId}` }) },
  async rebuildKnowledgeDocument(documentId: number) { return activeTransport().request<KnowledgeImportJob>({ method: 'POST', path: `/api/knowledge/documents/${documentId}/rebuild` }) },
  async revealKnowledgeSource(documentId: number) {
    if (!window.a3Desktop?.knowledgeRevealSource) throw new Error('来源定位仅桌面版可用。')
    return desktopEnvelope<{ mode: string }>(await window.a3Desktop.knowledgeRevealSource(documentId))
  },
  async openKnowledgeSource(documentId: number, locator: KnowledgeLocator) {
    if (!window.a3Desktop?.knowledgeOpenSource) throw new Error('来源预览仅桌面版可用。')
    return desktopEnvelope<{ mode: string; displayName: string }>(await window.a3Desktop.knowledgeOpenSource(documentId, locator))
  },
}
