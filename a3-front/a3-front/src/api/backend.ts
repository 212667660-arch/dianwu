import { createDesktopTransport } from './desktop-transport'
import { BackendApiError, desktopEnvelope, type BackendTransport } from './transport'
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
  ModelProfileInput,
  ModelProfileMutationResult,
  ModelProfilePolicy,
  ModelProfileVault,
  ModelRuntimeStatus,
  ModelSettings,
  NextAction,
  PetSettings,
  PetSnapshot,
  PetTaskState,
  ProgressSnapshot,
  ReviewTask,
  SessionHistory,
  SessionModelPreference,
  SessionModelPreferenceInput,
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
  async modelProfilesList(): Promise<ModelProfileVault> {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelProfilesList) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelProfileVault>(await bridge.modelProfilesList())
    }
    return legacyVault(await activeTransport().request<ModelSettings>({ method: 'GET', path: '/api/settings/model' }))
  },
  async testModelProfile(input: ModelProfileInput) {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelProfileTest) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelConnectionTest>(await bridge.modelProfileTest(input))
    }
    return activeTransport().request<ModelConnectionTest>({
      method: 'POST', path: '/api/settings/model/test', body: legacyConfig(input),
    })
  },
  async upsertModelProfile(input: ModelProfileInput): Promise<ModelProfileMutationResult> {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelProfileUpsert) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelProfileMutationResult>(await bridge.modelProfileUpsert(input))
    }
    const settings = await activeTransport().request<ModelSettings>({
      method: 'PUT', path: '/api/settings/model', body: legacyConfig(input),
    })
    return legacyMutation(settings)
  },
  async deleteModelProfile(profileId: string): Promise<ModelProfileMutationResult> {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelProfileDelete) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelProfileMutationResult>(await bridge.modelProfileDelete(profileId))
    }
    throw desktopOnlyError()
  },
  async saveModelProfilePolicy(input: ModelProfilePolicy): Promise<ModelProfileMutationResult> {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelProfilePolicySave) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelProfileMutationResult>(await bridge.modelProfilePolicySave(input))
    }
    throw desktopOnlyError()
  },
  async modelRuntimeStatus(): Promise<ModelRuntimeStatus> {
    const bridge = window.a3Desktop
    if (bridge) {
      if (!bridge.modelRuntimeStatus) throw desktopBridgeUnavailableError()
      return desktopEnvelope<ModelRuntimeStatus>(await bridge.modelRuntimeStatus())
    }
    const ready = await activeTransport().request<HealthStatus>({ method: 'GET', path: '/health/ready' })
    const vault = await backendApi.modelProfilesList()
    return legacyRuntime(vault, ready.status === 'ready')
  },
  async sessionModelPreference(sessionId: string) {
    return activeTransport().request<SessionModelPreference>({
      method: 'GET', path: `/api/sessions/${encodeURIComponent(sessionId)}/model-preference`,
    })
  },
  async saveSessionModelPreference(sessionId: string, input: SessionModelPreferenceInput) {
    return activeTransport().request<SessionModelPreference>({
      method: 'PUT', path: `/api/sessions/${encodeURIComponent(sessionId)}/model-preference`, body: input,
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
  async pet(): Promise<PetSnapshot> {
    const bridge = window.a3Desktop
    if (!bridge) return unavailablePetSnapshot()
    if (!bridge.petGet) throw desktopBridgeUnavailableError()
    return desktopEnvelope<PetSnapshot>(await bridge.petGet())
  },
  async updatePetSettings(input: Partial<PetSettings>): Promise<PetSnapshot> {
    const bridge = window.a3Desktop
    if (!bridge) throw desktopOnlyError()
    if (!bridge.petUpdateSettings) throw desktopBridgeUnavailableError()
    return desktopEnvelope<PetSnapshot>(await bridge.petUpdateSettings(input))
  },
  async setPetTaskState(state: PetTaskState): Promise<PetTaskState> {
    const bridge = window.a3Desktop
    if (!bridge) return state
    if (!bridge.petSetTaskState) throw desktopBridgeUnavailableError()
    return desktopEnvelope<PetTaskState>(await bridge.petSetTaskState(state))
  },
}

function legacyConfig(input: ModelProfileInput): ModelConfigInput {
  const model = input.models.find(value => value.id === input.default_model_id)
  if (!model) throw new BackendApiError(400, 'MODEL_PROFILE_DEFAULT_MODEL_INVALID', '默认模型配置无效。')
  return {
    provider: input.provider,
    api_key: input.api_key,
    base_url: input.base_url,
    model_name: model.provider_model_name,
    anthropic_version: input.anthropic_version,
    request_timeout_seconds: input.request_timeout_seconds,
  }
}

function legacyVault(settings: ModelSettings): ModelProfileVault {
  if (!settings.api_key_configured) {
    return { version: 2, global: { default_profile_id: null, auto_failover: false, fallback_profile_ids: [] }, profiles: [] }
  }
  return {
    version: 2,
    global: { default_profile_id: 'web-default', auto_failover: false, fallback_profile_ids: [] },
    profiles: [{
      id: 'web-default', label: '默认模型', enabled: true, provider: settings.provider,
      base_url: settings.base_url, api_key_configured: true,
      anthropic_version: settings.anthropic_version,
      request_timeout_seconds: settings.request_timeout_seconds,
      default_model_id: 'web-model',
      models: [{
        id: 'web-model', provider_model_name: settings.model_name, label: settings.model_name,
        max_output_tokens: 4096, supported_reasoning_efforts: ['auto', 'off'], reasoning_adapter: 'none',
      }],
    }],
  }
}

function legacyRuntime(vault: ModelProfileVault, ready: boolean): ModelRuntimeStatus {
  return {
    ready,
    default_profile_id: vault.global.default_profile_id,
    auto_failover: false,
    fallback_profile_ids: [],
    profiles: vault.profiles.map(profile => ({
      profile_id: profile.id, enabled: profile.enabled, needs_attention: false,
      circuit_state: 'closed', cooldown_until: 0, consecutive_failures: 0,
    })),
  }
}

function legacyMutation(settings: ModelSettings): ModelProfileMutationResult {
  const vault = legacyVault(settings)
  return { vault, runtime: legacyRuntime(vault, settings.api_key_configured) }
}

function desktopOnlyError() {
  return new BackendApiError(400, 'DESKTOP_ONLY', '多模型配置管理仅桌面版可用。')
}

function desktopBridgeUnavailableError() {
  return new BackendApiError(503, 'DESKTOP_BRIDGE_UNAVAILABLE', '桌面模型配置桥接尚未就绪，请重启应用。', true)
}

function unavailablePetSnapshot(): PetSnapshot {
  return {
    available: false,
    pet: null,
    settings: { visible: false, scale: 1, speed: 1 },
    state: 'idle',
  }
}
