import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { backendApi, errorMessage } from '@/api'
import type {
  MistakeItem,
  ModelConfigInput,
  ModelSettings,
  NextAction,
  ProgressSnapshot,
  ReviewTask,
  SessionHistory,
} from '@/api'

const initialSessionId = localStorage.getItem('a3-session-id') || `student_${Date.now().toString(36)}`

export const useBackendStore = defineStore('backend', () => {
  const sessionId = ref(initialSessionId)
  const live = ref(false)
  const ready = ref(false)
  const model = ref<ModelSettings | null>(null)
  const session = ref<SessionHistory | null>(null)
  const progress = ref<ProgressSnapshot | null>(null)
  const nextAction = ref<NextAction | null>(null)
  const reviews = ref<ReviewTask[]>([])
  const mistakes = ref<MistakeItem[]>([])
  const loading = ref(false)
  const modelConfigBusy = ref(false)
  const lastError = ref('')

  const resources = computed(() => session.value?.resources || [])
  const questions = computed(() => resources.value.flatMap(resource => resource.questions))
  const profileReady = computed(() => Boolean(session.value?.profile_text))
  const modelConfigured = computed(() => model.value?.api_key_configured === true)

  function setSessionId(value: string) {
    const normalized = value.trim().replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64)
    if (!normalized) return
    sessionId.value = normalized
    localStorage.setItem('a3-session-id', normalized)
  }

  async function refreshHealth() {
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

  return {
    sessionId, live, ready, model, session, progress, nextAction, reviews, mistakes,
    resources, questions, profileReady, modelConfigured, loading, modelConfigBusy, lastError,
    setSessionId, refreshHealth, refreshSession, refreshAll, submitAnswer,
    testModelSettings, saveModelSettings,
  }
})
