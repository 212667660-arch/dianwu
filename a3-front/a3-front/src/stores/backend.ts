import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { backendApi, errorMessage } from '@/api'
import type {
  MistakeItem,
  ModelConfigInput,
  ModelProfileInput,
  ModelProfilePolicy,
  ModelProfileSummary,
  ModelRuntimeStatus,
  ModelSettings,
  SessionModelPreference,
  SessionModelPreferenceInput,
  KnowledgeBinding,
  KnowledgeCollection,
  KnowledgeDocument,
  KnowledgeBulkRequest,
  KnowledgeImportJob,
  KnowledgeStatus,
  NextAction,
  ProgressSnapshot,
  ReviewTask,
  ArtifactType,
  ResourceBundle,
  SessionHistory,
} from '@/api'

const initialSessionId = localStorage.getItem('a3-session-id') || `student_${Date.now().toString(36)}`

export const useBackendStore = defineStore('backend', () => {
  const sessionId = ref(initialSessionId)
  const live = ref(false)
  const ready = ref(false)
  const model = ref<ModelSettings | null>(null)
  const modelLoaded = ref(false)
  const session = ref<SessionHistory | null>(null)
  const progress = ref<ProgressSnapshot | null>(null)
  const nextAction = ref<NextAction | null>(null)
  const reviews = ref<ReviewTask[]>([])
  const mistakes = ref<MistakeItem[]>([])
  const loading = ref(false)
  const modelConfigBusy = ref(false)
  const modelProfileBusy = ref(false)
  const modelProfiles = ref<ModelProfileSummary[]>([])
  const modelPolicy = ref<ModelProfilePolicy | null>(null)
  const modelRuntimeStatus = ref<ModelRuntimeStatus | null>(null)
  const sessionModelPreference = ref<SessionModelPreference | null>(null)
  const lastError = ref('')
  const knowledgeStatus = ref<KnowledgeStatus | null>(null)
  const knowledgeCollections = ref<KnowledgeCollection[]>([])
  const knowledgeDocuments = ref<KnowledgeDocument[]>([])
  const knowledgeJobs = ref<KnowledgeImportJob[]>([])
  const boundKnowledgeCollectionIds = ref<number[]>([])
  const knowledgePrivacyMode = ref<KnowledgeBinding['privacy_mode']>('allow_model_context')
  const knowledgeLoading = ref(false)
  const knowledgeError = ref('')
  let modelProfilePending = 0
  let profileStateTail = Promise.resolve<unknown>(undefined)
  let preferenceSaveTail = Promise.resolve<unknown>(undefined)
  let preferenceLoadVersion = 0
  let preferenceSaveVersion = 0
  let sessionRevision = 0
  let committedSessionModelPreference: SessionModelPreference | null = null

  const resources = computed(() => session.value?.resources || [])
  const resourceBundles = computed(() => session.value?.resource_bundles || [])
  const questions = computed(() => resources.value.flatMap(resource => resource.questions))
  const profileReady = computed(() => Boolean(session.value?.profile_text))
  const modelConfigured = computed(() => model.value?.api_key_configured === true)

  function setSessionId(value: string) {
    const normalized = value.trim().replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64)
    if (!normalized) return
    sessionRevision += 1
    sessionId.value = normalized
    localStorage.setItem('a3-session-id', normalized)
    sessionModelPreference.value = null
    committedSessionModelPreference = null
    void loadSessionModelPreference(normalized).catch(() => {})
  }

  async function refreshHealth() {
    modelLoaded.value = false
    try {
      live.value = (await backendApi.live()).status === 'live'
    } catch {
      live.value = false
    }
    try {
      ready.value = (await backendApi.ready()).status === 'ready'
    } catch {
      ready.value = false
    }
    try {
      model.value = await backendApi.modelSettings()
    } catch {
      model.value = null
    } finally {
      modelLoaded.value = true
    }
  }

  async function refreshSession() {
    try {
      session.value = await backendApi.session(sessionId.value)
    } catch {
      session.value = null
      progress.value = null
      nextAction.value = null
      reviews.value = []
      mistakes.value = []
      return
    }
    const results = await Promise.allSettled([
      backendApi.progress(sessionId.value),
      backendApi.nextAction(sessionId.value),
      backendApi.reviews(sessionId.value),
      backendApi.mistakes(sessionId.value),
    ])
    progress.value = results[0].status === 'fulfilled' ? results[0].value : null
    nextAction.value = results[1].status === 'fulfilled' ? results[1].value : null
    reviews.value = results[2].status === 'fulfilled' ? results[2].value : []
    mistakes.value = results[3].status === 'fulfilled' ? results[3].value : []
  }

  async function refreshAll() {
    loading.value = true
    lastError.value = ''
    try {
      await Promise.all([refreshHealth(), refreshSession()])
    } catch (error) {
      lastError.value = errorMessage(error)
    } finally {
      loading.value = false
    }
  }

  async function retryResourceArtifact(bundleId: string, artifactType: ArtifactType): Promise<ResourceBundle> {
    const result = await backendApi.retryResourceArtifact(bundleId, artifactType, sessionId.value)
    if (session.value) {
      const bundles = [...(session.value.resource_bundles || [])]
      const index = bundles.findIndex(bundle => bundle.bundle_id === result.bundle.bundle_id)
      if (index >= 0) bundles[index] = result.bundle
      else bundles.unshift(result.bundle)
      session.value = { ...session.value, resource_bundles: bundles }
    }
    return result.bundle
  }

  async function submitAnswer(questionId: number, answer: string, hintCount = 0) {
    const result = await backendApi.submitAttempt(sessionId.value, questionId, answer, hintCount)
    await refreshSession()
    return result
  }

  async function testModelSettings(input: ModelConfigInput) {
    modelConfigBusy.value = true
    try {
      return await backendApi.testModelSettings(input)
    } finally {
      modelConfigBusy.value = false
    }
  }

  async function saveModelSettings(input: ModelConfigInput) {
    modelConfigBusy.value = true
    try {
      const value = await backendApi.saveModelSettings(input)
      model.value = value
      await refreshHealth()
      return value
    } finally {
      modelConfigBusy.value = false
    }
  }

  async function refreshModelProfiles() {
    return enqueueProfileState(async () => {
      const results = await Promise.allSettled([
        backendApi.modelProfilesList(),
        backendApi.modelRuntimeStatus(),
      ])
      if (results[0].status === 'fulfilled') {
        modelProfiles.value = results[0].value.profiles
        modelPolicy.value = results[0].value.global
      }
      if (results[1].status === 'fulfilled') modelRuntimeStatus.value = results[1].value
      const failure = results.find(result => result.status === 'rejected')
      if (failure?.status === 'rejected') lastError.value = errorMessage(failure.reason)
    })
  }

  async function testModelProfile(input: ModelProfileInput) {
    beginModelProfileOperation()
    try { return await backendApi.testModelProfile(input) }
    finally { endModelProfileOperation() }
  }

  async function upsertModelProfile(input: ModelProfileInput) {
    return runProfileMutation(() => backendApi.upsertModelProfile(input))
  }

  async function deleteModelProfile(profileId: string) {
    return runProfileMutation(() => backendApi.deleteModelProfile(profileId))
  }

  async function saveModelPolicy(input: ModelProfilePolicy) {
    return runProfileMutation(() => backendApi.saveModelProfilePolicy(input))
  }

  async function runProfileMutation(operation: () => ReturnType<typeof backendApi.upsertModelProfile>) {
    return enqueueProfileState(async () => {
      const result = await operation()
      modelProfiles.value = result.vault.profiles
      modelPolicy.value = result.vault.global
      modelRuntimeStatus.value = result.runtime
      return result
    })
  }

  async function loadSessionModelPreference(targetSessionId = sessionId.value) {
    const targetRevision = sessionRevision
    const requestVersion = ++preferenceLoadVersion
    const value = await backendApi.sessionModelPreference(targetSessionId)
    if (
      sessionId.value === targetSessionId
      && sessionRevision === targetRevision
      && requestVersion === preferenceLoadVersion
    ) {
      committedSessionModelPreference = value
      sessionModelPreference.value = value
    }
    return value
  }

  function saveSessionModelPreference(input: SessionModelPreferenceInput) {
    const targetSessionId = sessionId.value
    const targetRevision = sessionRevision
    const requestVersion = ++preferenceSaveVersion
    preferenceLoadVersion += 1
    if (sessionRevision === targetRevision) sessionModelPreference.value = { session_id: targetSessionId, ...input }
    beginModelProfileOperation()
    const operation = async () => {
      try {
        const value = await backendApi.saveSessionModelPreference(targetSessionId, input)
        if (sessionRevision === targetRevision) {
          committedSessionModelPreference = value
          if (requestVersion === preferenceSaveVersion) sessionModelPreference.value = value
        }
        return value
      } catch (error) {
        if (sessionRevision === targetRevision && requestVersion === preferenceSaveVersion) {
          sessionModelPreference.value = committedSessionModelPreference
        }
        throw error
      } finally {
        endModelProfileOperation()
      }
    }
    const result = preferenceSaveTail.then(operation, operation)
    preferenceSaveTail = result.then(() => undefined, () => undefined)
    return result
  }

  function enqueueProfileState<T>(operation: () => Promise<T>) {
    beginModelProfileOperation()
    const result = profileStateTail.then(operation, operation)
    profileStateTail = result.then(() => undefined, () => undefined)
    return result.finally(endModelProfileOperation)
  }

  function beginModelProfileOperation() {
    modelProfilePending += 1
    modelProfileBusy.value = true
  }

  function endModelProfileOperation() {
    modelProfilePending = Math.max(0, modelProfilePending - 1)
    modelProfileBusy.value = modelProfilePending > 0
  }

  async function refreshKnowledge() {
    knowledgeLoading.value = true
    knowledgeError.value = ''
    const results = await Promise.allSettled([
      backendApi.knowledgeStatus(), backendApi.knowledgeCollections(),
      backendApi.knowledgeDocuments(), backendApi.knowledgeImports(),
      backendApi.sessionKnowledgeCollections(sessionId.value),
    ])
    knowledgeStatus.value = results[0].status === 'fulfilled' ? results[0].value : null
    if (results[1].status === 'fulfilled') knowledgeCollections.value = results[1].value
    if (results[2].status === 'fulfilled') knowledgeDocuments.value = results[2].value
    if (results[3].status === 'fulfilled') knowledgeJobs.value = results[3].value
    if (results[4].status === 'fulfilled') {
      boundKnowledgeCollectionIds.value = results[4].value.collection_ids
      knowledgePrivacyMode.value = results[4].value.privacy_mode
    }
    const failure = results.find(result => result.status === 'rejected')
    if (failure?.status === 'rejected') knowledgeError.value = errorMessage(failure.reason)
    knowledgeLoading.value = false
  }

  async function saveSessionKnowledgeCollections(collectionIds: number[], privacyMode = knowledgePrivacyMode.value) {
    const previousIds = [...boundKnowledgeCollectionIds.value]
    const previousMode = knowledgePrivacyMode.value
    boundKnowledgeCollectionIds.value = [...collectionIds]
    knowledgePrivacyMode.value = privacyMode
    try {
      const result = await backendApi.saveSessionKnowledgeCollections(sessionId.value, collectionIds, privacyMode)
      boundKnowledgeCollectionIds.value = result.collection_ids
      knowledgePrivacyMode.value = result.privacy_mode
      return result
    } catch (error) {
      boundKnowledgeCollectionIds.value = previousIds
      knowledgePrivacyMode.value = previousMode
      throw error
    }
  }

  async function chooseKnowledgeFiles(collectionId: number) { const result = await backendApi.chooseKnowledgeFiles(collectionId); await refreshKnowledge(); return result }
  async function importDroppedKnowledgeFiles(files: FileList | File[], collectionId: number) { const result = await backendApi.importDroppedKnowledgeFiles(files, collectionId); await refreshKnowledge(); return result }
  async function cancelKnowledgeJob(jobId: number) { const result = await backendApi.cancelKnowledgeImport(jobId); await refreshKnowledge(); return result }
  async function retryKnowledgeJob(jobId: number) { const result = await backendApi.retryKnowledgeImport(jobId); await refreshKnowledge(); return result }
  async function bulkKnowledgeDocuments(input: KnowledgeBulkRequest) { const result = await backendApi.bulkKnowledgeDocuments(input); await refreshKnowledge(); return result }
  async function deleteKnowledgeDocument(documentId: number) { await backendApi.deleteKnowledgeDocument(documentId); await refreshKnowledge() }
  async function rebuildKnowledgeDocument(documentId: number) { const result = await backendApi.rebuildKnowledgeDocument(documentId); await refreshKnowledge(); return result }

  return {
    sessionId, live, ready, model, session, progress, nextAction, reviews, mistakes,
    knowledgeStatus, knowledgeCollections, knowledgeDocuments, knowledgeJobs,
    boundKnowledgeCollectionIds, knowledgePrivacyMode, knowledgeLoading, knowledgeError,
    resources, resourceBundles, questions, profileReady, modelConfigured, modelLoaded, loading, modelConfigBusy, modelProfileBusy, lastError,
    modelProfiles, modelPolicy, modelRuntimeStatus, sessionModelPreference,
    setSessionId, refreshHealth, refreshSession, refreshAll, submitAnswer, retryResourceArtifact,
    testModelSettings, saveModelSettings,
    refreshModelProfiles, testModelProfile, upsertModelProfile, deleteModelProfile, saveModelPolicy,
    loadSessionModelPreference, saveSessionModelPreference,
    refreshKnowledge, saveSessionKnowledgeCollections, chooseKnowledgeFiles,
    importDroppedKnowledgeFiles, cancelKnowledgeJob, retryKnowledgeJob, bulkKnowledgeDocuments, deleteKnowledgeDocument, rebuildKnowledgeDocument,
  }
})
