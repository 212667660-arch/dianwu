<template>
  <section class="page tutor-page">
    <div class="tutor-statusbar">
      <button type="button" class="knowledge-space-button" data-testid="knowledge-space-button" @click="openKnowledgeSpace"><span>▤</span> 本空间资料 · {{ backend.boundKnowledgeCollectionIds.length }}</button>
      <span class="status-pill" :class="backend.ready ? 'good' : 'bad'">{{ backend.ready ? '模型就绪' : '模型未就绪' }}</span>
      <span class="status-pill">{{ phaseLabel }}</span>
    </div>

    <article class="chat-panel">
      <div ref="messageList" class="message-list">
        <div v-if="failoverNotice" class="connection-notice" data-testid="failover-notice">↝ {{ failoverNotice }}，这次回答仍保持同一条清晰的上下文。</div>
        <div v-if="!displayMessages.length && !historicalBundles.length && !pendingUser" class="welcome" :data-companion-id="companionId">
          <div class="companion-portrait" aria-hidden="true"><span>学</span></div>
          <h1>今天想一起学点什么？</h1>
          <p>不用急着把目标说得很完整。先告诉我你最近在困惑什么，我们慢慢把它变成一条清晰的路。</p>
          <div class="companion-choice">
            <button type="button" class="active"><span class="mini-avatar">学</span>学习伙伴</button>
            <button type="button" disabled><span class="mini-avatar muted-avatar">＋</span>未来伙伴</button>
          </div>
          <div class="workspace-memory"><span>▢ 工作空间：{{ backend.sessionId }}</span><span>◷ 学习记忆已连接</span></div>
          <div class="starter-list">
            <button v-for="starter in starters" :key="starter" type="button" @click="editor = starter">{{ starter }}</button>
          </div>
        </div>

        <div v-for="message in displayMessages" :key="message.seq" class="message" :class="message.role">
          <div class="message-meta">{{ message.role === 'user' ? '你' : '学习伙伴' }}</div>
          <pre>{{ message.content }}</pre>
        </div>
        <div v-if="resourceProgress" class="resource-progress" role="status">
          <span>资源生成进度</span>
          <strong>{{ resourceProgress.completed }} / {{ resourceProgress.total }}</strong>
          <span>{{ resourceProgress.currentType }}</span>
        </div>
        <ResourceBundle
          v-for="bundle in historicalBundles"
          :key="bundle.bundle_id"
          :bundle="bundle"
          :retrying-types="retryingTypesFor(bundle.bundle_id)"
          @retry-artifact="artifactType => retryArtifact(bundle.bundle_id, artifactType)"
        />
        <ResourceBundle
          v-if="visibleActiveBundle"
          :bundle="visibleActiveBundle"
          :retrying-types="retryingTypesFor(visibleActiveBundle.bundle_id)"
          @retry-artifact="artifactType => retryArtifact(visibleActiveBundle?.bundle_id || '', artifactType)"
        />
        <div v-for="item in retainedInterruptions" :key="item.id" class="message assistant retained-interruption">
          <div class="message-meta">学习伙伴 · 中断前保留</div><pre>{{ item.content }}</pre>
        </div>
        <div v-if="pendingUser" class="message user transient"><div class="message-meta">你</div><pre>{{ pendingUser }}</pre></div>
        <div v-if="generating || streamText" class="message assistant transient">
          <div class="message-meta">{{ activePhase }} Agent <span v-if="generating" class="typing">正在组织思绪…</span></div>
          <pre>{{ streamText || '让我想一想…' }}</pre>
        </div>
        <div v-if="streamError" class="stream-error" role="alert">
          <div><strong>本次请求未完成</strong><p>{{ streamError }}</p></div>
          <el-button text type="primary" @click="restoreFailedMessage">重新编辑</el-button>
        </div>
        <div v-if="streamInterrupted" class="stream-interruption" role="status">
          <div><strong>连接在回答途中轻轻断开了</strong><p>已经出现的文字会留在这里，不会与另一个模型的内容静默拼接。</p></div>
          <el-button v-if="canContinueWithBackup" text type="primary" data-testid="continue-with-backup" @click="continueWithBackup">使用备用配置继续</el-button>
        </div>
        <div v-if="sources.length" class="inline-sources">
          <span>这次参考了</span>
          <a v-for="source in sources" :key="source.url" :href="source.url" target="_blank" rel="noreferrer">{{ source.title }}</a>
        </div>
        <KnowledgeSourceList v-if="knowledgeSources.length" :sources="knowledgeSources" @open="openKnowledgeSource" />
      </div>

      <div class="composer-wrap">
        <div class="composer">
          <el-input v-model="editor" type="textarea" :rows="3" maxlength="8000" show-word-limit resize="none" placeholder="说点什么…" @keydown.ctrl.enter.prevent="send" />
          <div class="composer-actions">
            <div class="composer-left">
              <ModelSelectionPopover
                :profiles="backend.modelProfiles"
                :policy="backend.modelPolicy"
                :preference="backend.sessionModelPreference"
                :busy="backend.modelProfileBusy"
                :effective-profile-id="effectiveProfileId"
                :effective-model-id="effectiveModelId"
                :effective-reasoning-effort="effectiveReasoningEffort"
                @save="saveModelPreference"
              />
              <ResourceMenu v-if="canGenerateResources" v-model="resourceSelection" />
              <span class="gentle-tip">写下目标、问题，或此刻的困惑</span><span class="stream-toggle">流式 <el-switch v-model="useStream" /></span>
            </div>
            <div class="toolbar">
              <el-button v-if="generating" type="danger" plain :icon="Close" @click="cancel">取消</el-button>
              <el-button data-testid="send" type="primary" :icon="Promotion" :loading="generating" :disabled="!editor.trim() || !backend.modelConfigured" @click="send">发送</el-button>
            </div>
          </div>
        </div>
      </div>
    </article>
    <div v-if="knowledgeSpaceOpen" class="knowledge-space-modal" role="dialog" aria-modal="true" aria-label="本空间资料">
      <div class="knowledge-space-card"><header><div><span>LEARNING SPACE</span><h2>让哪些资料陪你学习？</h2></div><button type="button" aria-label="关闭本空间资料" @click="knowledgeSpaceOpen=false">×</button></header>
        <p class="privacy-notice">选择“允许模型参考”时，命中的少量资料片段会发送给当前模型服务；原文件始终留在本机。</p>
        <div class="binding-collections"><label v-for="collection in backend.knowledgeCollections" :key="collection.id"><input v-model="bindingIds" type="checkbox" :value="collection.id" :data-testid="`collection-check-${collection.id}`"><span><strong>{{ collection.name }}</strong><small>{{ collection.document_count || 0 }} 份资料</small></span></label><p v-if="!backend.knowledgeCollections.length">还没有资料集合，可以先去知识库建一座小书房。</p></div>
        <fieldset><legend>隐私方式</legend><label><input v-model="bindingPrivacy" type="radio" value="allow_model_context" data-testid="privacy-allow-model">允许模型参考相关片段</label><label><input v-model="bindingPrivacy" type="radio" value="local_search_only" data-testid="privacy-local-only">仅本机检索，不发送片段</label></fieldset>
        <footer><span>账号同步功能预留，当前只保存到这台设备。</span><button type="button" data-testid="save-knowledge-binding" @click="saveKnowledgeBinding">保存到本空间</button></footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Close, Promotion } from '@element-plus/icons-vue'
import { backendApi, DesktopApiError, errorMessage, type ArtifactType, type KnowledgeSource, type ReasoningEffort, type ResourceArtifact, type ResourceBundle as ResourceBundleType, type ResourceSelection, type SessionModelPreferenceInput, type SourceItem, type StreamEvent } from '@/api'
import { useBackendStore } from '@/stores/backend'
import KnowledgeSourceList from '@/components/knowledge/KnowledgeSourceList.vue'
import ModelSelectionPopover from '@/components/model/ModelSelectionPopover.vue'
import ResourceBundle from '@/components/learning/ResourceBundle.vue'
import ResourceMenu from '@/components/learning/ResourceMenu.vue'
import { petTaskState, type PetTaskTicket } from '@/pet/task-state'

const backend = useBackendStore()
const route = useRoute()
const router = useRouter()
const companionId = 'study-companion'
const editor = ref('')
const useStream = ref(true)
const generating = ref(false)
const generationId = ref('')
const activeSessionId = ref('')
const activePhase = ref('诊断')
const streamText = ref('')
const pendingUser = ref('')
const streamError = ref('')
const failedMessage = ref('')
const failoverNotice = ref('')
const streamInterrupted = ref(false)
const canContinueWithBackup = ref(false)
const effectiveProfileId = ref('')
const effectiveModelId = ref('')
const effectiveReasoningEffort = ref<ReasoningEffort>()
const retainedInterruptions = ref<Array<{ id: number; content: string }>>([])
const sources = ref<SourceItem[]>([])
const knowledgeSources = ref<KnowledgeSource[]>([])
const resourceSelection = ref<ResourceSelection>({ mode: 'bundle' })
const activeBundle = ref<ResourceBundleType | null>(null)
const resourceProgress = ref<{ completed: number; total: number; currentType: string } | null>(null)
const retryingArtifacts = ref<Set<string>>(new Set())
const knowledgeSpaceOpen = ref(false)
const bindingIds = ref<number[]>([])
const bindingPrivacy = ref<'allow_model_context' | 'local_search_only'>('allow_model_context')
const messageList = ref<HTMLElement>()
let controller: AbortController | null = null
let interruptionId = 0
let activePetTask: PetTaskTicket | null = null

const messages = computed(() => backend.session?.messages || [])
const displayMessages = computed(() => messages.value.filter(message => !isBundleMessage(message.content)))
const historicalBundles = computed(() => backend.resourceBundles || [])
const visibleActiveBundle = computed(() => {
  if (!activeBundle.value) return null
  return historicalBundles.value.some(bundle => bundle.bundle_id === activeBundle.value?.bundle_id)
    ? null
    : activeBundle.value
})
const canGenerateResources = computed(() => ['PROFILED', 'GENERATING'].includes(backend.session?.state || ''))
const phaseLabel = computed(() => generating.value ? `${activePhase.value}中` : backend.session?.state || '等待开始')
const starters = ['我想学习一次函数，请先了解我的基础。', '我正在准备英语考试，希望制定复习计划。', '根据我的薄弱点生成一份笔记和分层练习。']

async function scrollBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

function handleEvent(event: StreamEvent) {
  if (event.generation_id) generationId.value = event.generation_id
  if (event.phase) {
    activePhase.value = event.phase === 'profile' ? '画像' : event.phase === 'resource' ? '资源' : '诊断'
    activePetTask?.update('running')
  }
  if (event.event === 'validation') activePetTask?.update('review')
  if (event.event === 'delta' && event.content) streamText.value += event.content
  if (event.event === 'replace' && event.content) streamText.value = event.content
  if (event.event === 'meta') {
    effectiveProfileId.value = event.profile_id || ''
    effectiveModelId.value = event.model_id || ''
    effectiveReasoningEffort.value = event.effective_reasoning_effort
    failoverNotice.value = event.failover_used ? '已自动切换到备用连接' : ''
  }
  if (event.event === 'sources') sources.value = (event.sources || []).filter((item): item is SourceItem => 'url' in item)
  if (event.event === 'knowledge_sources') knowledgeSources.value = (event.sources || []).filter((item): item is KnowledgeSource => 'reference_id' in item)
  if (event.event === 'resource_plan' && event.bundle_id) {
    activeBundle.value = provisionalBundle(
      event.bundle_id,
      event.topic || '正在生成资源',
      event.requested_types || [],
    )
    resourceProgress.value = {
      completed: 0,
      total: event.requested_types?.length || 0,
      currentType: '',
    }
  }
  if (event.event === 'resource_progress') {
    resourceProgress.value = {
      completed: event.completed_count || 0,
      total: event.total_count || 0,
      currentType: event.current_type || '',
    }
  }
  if (event.event === 'resource_artifact') {
    const artifact = artifactFromEvent(event)
    if (artifact) {
      if (!activeBundle.value) {
        activeBundle.value = provisionalBundle(
          `pending-${generationId.value || Date.now()}`,
          '正在生成资源',
          [artifact.type],
        )
      }
      const artifacts = activeBundle.value.artifacts.filter(item => item.type !== artifact.type)
      activeBundle.value = { ...activeBundle.value, artifacts: [...artifacts, artifact] }
    }
  }
  if (event.event === 'resource_bundle') {
    const bundle = bundleFromEvent(event)
    if (bundle) activeBundle.value = bundle
  }
  if (event.event === 'error') {
    streamError.value = event.message || event.code || '生成失败，请检查后重试。'
    ElMessage.error(streamError.value)
  }
  if (event.event === 'interrupted') {
    generating.value = false
    streamInterrupted.value = true
    canContinueWithBackup.value = event.can_continue_with_backup === true
  }
  scrollBottom()
}

function restoreFailedMessage() { editor.value = failedMessage.value; streamError.value = ''; streamText.value = '' }

async function send() {
  const message = editor.value.trim()
  if (!message || generating.value || !backend.modelConfigured) return
  if (streamInterrupted.value) preserveInterruptedText()
  generating.value = true
  pendingUser.value = message
  editor.value = ''
  streamText.value = ''
  streamError.value = ''
  failoverNotice.value = ''
  streamInterrupted.value = false
  canContinueWithBackup.value = false
  failedMessage.value = ''
  generationId.value = ''
  const requestSessionId = backend.sessionId
  activeSessionId.value = requestSessionId
  sources.value = []
  knowledgeSources.value = []
  activeBundle.value = null
  resourceProgress.value = null
  controller = new AbortController()
  const petTask = petTaskState.begin('running')
  activePetTask = petTask
  await scrollBottom()
  try {
    if (useStream.value) {
      await backendApi.streamChat(
        requestSessionId,
        message,
        handleEvent,
        controller.signal,
        canGenerateResources.value ? resourceSelection.value : undefined,
      )
    } else {
      const response = await backendApi.chat(
        requestSessionId,
        message,
        canGenerateResources.value ? resourceSelection.value : undefined,
      )
      streamText.value = response.reply
      sources.value = response.sources
      knowledgeSources.value = response.knowledge_sources || []
      activePhase.value = response.phase === 'profile' ? '画像' : response.phase === 'resource' ? '资源' : '诊断'
      activeBundle.value = response.bundle || null
    }
    if (backend.sessionId === requestSessionId) await backend.refreshSession()
    if (streamInterrupted.value) { failedMessage.value = message; pendingUser.value = ''; petTask.complete('waiting') }
    else if (streamError.value) { failedMessage.value = message; pendingUser.value = ''; petTask.fail() }
    else { pendingUser.value = ''; streamText.value = ''; petTask.complete('waiting') }
  } catch (error) {
    if (isCancellationError(error)) petTask.complete('waiting')
    else {
      streamError.value = errorMessage(error)
      failedMessage.value = message
      pendingUser.value = ''
      ElMessage.error(streamError.value)
      petTask.fail()
    }
  } finally {
    generating.value = false
    controller = null
    generationId.value = ''
    activeSessionId.value = ''
    if (activePetTask === petTask) activePetTask = null
    await scrollBottom()
  }
}

function isBundleMessage(content: string): boolean {
  try {
    return JSON.parse(content)?.protocol_version === 'learning-resource-bundle/v2'
  } catch {
    return false
  }
}

function provisionalBundle(bundleId: string, topic: string, requestedTypes: ArtifactType[]): ResourceBundleType {
  return {
    bundle_id: bundleId,
    protocol_version: 'learning-resource-bundle/v2',
    topic,
    profile_version: backend.session?.profile_version || 0,
    learning_state_version: String(backend.session?.learning_state_version || 0),
    mode: resourceSelection.value.mode,
    status: 'PARTIAL',
    requested_types: requestedTypes,
    artifacts: [],
    aggregate_quality: 0,
    created_at: new Date().toISOString(),
    knowledge_sources: [],
    public_sources: [],
  }
}

function artifactFromEvent(event: StreamEvent): ResourceArtifact | null {
  if (!event.artifact_id || !event.type || !event.title || !event.status) return null
  if (!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(event.status)) return null
  return {
    artifact_id: event.artifact_id,
    type: event.type,
    title: event.title,
    status: event.status as ResourceArtifact['status'],
    body: event.body || '',
    type_specific_data: event.type_specific_data || {},
    quality_score: event.quality_score || 0,
    quality_issues: event.quality_issues || [],
    error_code: event.error_code || null,
    retryable: event.retryable === true,
  }
}

function bundleFromEvent(event: StreamEvent): ResourceBundleType | null {
  if (
    !event.bundle_id
    || event.protocol_version !== 'learning-resource-bundle/v2'
    || !event.topic
    || !event.mode
    || !event.status
    || !event.requested_types
    || !event.artifacts
    || !event.created_at
  ) return null
  if (!['COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED'].includes(event.status)) return null
  return {
    bundle_id: event.bundle_id,
    protocol_version: event.protocol_version,
    topic: event.topic,
    profile_version: event.profile_version || 0,
    learning_state_version: event.learning_state_version || '0',
    mode: event.mode,
    status: event.status as ResourceBundleType['status'],
    requested_types: event.requested_types,
    artifacts: event.artifacts,
    aggregate_quality: event.aggregate_quality || 0,
    created_at: event.created_at,
    knowledge_sources: event.knowledge_sources || [],
    public_sources: event.public_sources || [],
  }
}

async function retryArtifact(bundleId: string, artifactType: ArtifactType) {
  if (!bundleId) return
  const key = `${bundleId}:${artifactType}`
  retryingArtifacts.value = new Set(retryingArtifacts.value).add(key)
  try {
    const updated = await backend.retryResourceArtifact(bundleId, artifactType)
    if (activeBundle.value?.bundle_id === bundleId) activeBundle.value = updated
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    const next = new Set(retryingArtifacts.value)
    next.delete(key)
    retryingArtifacts.value = next
  }
}

function retryingTypesFor(bundleId: string): ArtifactType[] {
  return [...retryingArtifacts.value]
    .filter(key => key.startsWith(`${bundleId}:`))
    .map(key => key.slice(bundleId.length + 1) as ArtifactType)
}

function preserveInterruptedText() {
  const content = streamText.value.trim()
  if (content) retainedInterruptions.value.push({ id: ++interruptionId, content })
  streamText.value = ''
  streamInterrupted.value = false
  canContinueWithBackup.value = false
}

async function continueWithBackup() {
  const original = failedMessage.value || pendingUser.value || '刚才的问题'
  const partial = streamText.value.trim().slice(-1200)
  preserveInterruptedText()
  editor.value = `刚才的回答因连接中断而停止。请继续完成对“${original}”的解答，避免重复已经给出的内容。\n已给出的内容：${partial}`
  await send()
}

async function saveModelPreference(input: SessionModelPreferenceInput) {
  try { await backend.saveSessionModelPreference(input); ElMessage.success('本空间模型偏好已保存') }
  catch (error) { ElMessage.error(errorMessage(error)) }
}

function isCancellationError(error: unknown) {
  return (error as Error | undefined)?.name === 'AbortError' || (error instanceof DesktopApiError && error.code === 'DESKTOP_STREAM_CANCELLED')
}

async function openKnowledgeSpace(){await backend.refreshKnowledge();bindingIds.value=[...backend.boundKnowledgeCollectionIds];bindingPrivacy.value=backend.knowledgePrivacyMode;knowledgeSpaceOpen.value=true}
async function saveKnowledgeBinding(){try{await backend.saveSessionKnowledgeCollections(bindingIds.value,bindingPrivacy.value);knowledgeSpaceOpen.value=false;ElMessage.success('本空间资料已保存')}catch(error){ElMessage.error(errorMessage(error))}}
async function openKnowledgeSource(source:KnowledgeSource){await router.push({path:'/knowledge',query:{document:String(source.document_id),type:source.locator.type,start:String(source.locator.start),end:String(source.locator.end),...(source.locator.sheet_name?{sheet:source.locator.sheet_name}:{})}})}

async function cancel() {
  const cancelGenerationId = generationId.value
  const cancelSessionId = activeSessionId.value || backend.sessionId
  controller?.abort()
  if (!cancelGenerationId) return
  try { await backendApi.cancelGeneration(cancelGenerationId, cancelSessionId); ElMessage.info('已请求取消生成') }
  catch (error) { ElMessage.error(errorMessage(error)) }
}

watch(() => route.fullPath, async () => {
  const rawPrompt = typeof route.query.prompt === 'string' ? route.query.prompt : ''
  const prompt = rawPrompt.slice(0, 1000)
  if (prompt) editor.value = prompt

  const rawCollectionId = typeof route.query.knowledge_collection === 'string'
    ? route.query.knowledge_collection
    : ''
  const collectionId = Number(rawCollectionId)
  if (Number.isSafeInteger(collectionId) && collectionId > 0) {
    try {
      await backend.saveSessionKnowledgeCollections([collectionId], 'allow_model_context')
    } catch (error) {
      ElMessage.error(errorMessage(error))
    }
  }

  if (rawPrompt || rawCollectionId) {
    const query = { ...route.query }
    delete query.prompt
    delete query.knowledge_collection
    await router.replace({ path: route.path, query })
  }
}, { immediate: true })
watch(() => backend.sessionId, currentSessionId => {
  const shouldCancel = generating.value && activeSessionId.value && currentSessionId !== activeSessionId.value
  pendingUser.value = ''
  streamText.value = ''
  sources.value = []
  knowledgeSources.value = []
  activeBundle.value = null
  resourceProgress.value = null
  retryingArtifacts.value = new Set()
  streamError.value = ''
  failedMessage.value = ''
  failoverNotice.value = ''
  streamInterrupted.value = false
  canContinueWithBackup.value = false
  retainedInterruptions.value = []
  effectiveProfileId.value = ''
  effectiveModelId.value = ''
  effectiveReasoningEffort.value = undefined
  if (shouldCancel) {
    generating.value = false
    void cancel()
  }
})
onMounted(async () => {
  await Promise.allSettled([backend.refreshModelProfiles(), backend.loadSessionModelPreference()])
})
onBeforeUnmount(() => { controller?.abort(); activePetTask?.complete('idle'); activePetTask = null })
</script>

<style scoped lang="scss">
.tutor-page { max-width: 940px; min-height: calc(100vh - 138px); }
.tutor-statusbar { display: flex; justify-content: flex-end; gap: 7px; min-height: 28px; }
.knowledge-space-button { margin-right: auto; min-height: 26px; padding: 3px 10px; color: #6e8f8e; background: #edf5f1; border: 1px solid #dbe9e3; border-radius: 999px; cursor: pointer; font-size: 10px; }
.chat-panel { min-height: calc(100vh - 166px); display: flex; flex-direction: column; }
.message-list { height: calc(100vh - 340px); min-height: 390px; overflow: auto; padding: 10px 28px 24px; scrollbar-width: thin; scrollbar-color: #ded5c9 transparent; }
.resource-progress { display: flex; align-items: center; gap: 10px; margin: 8px 0; padding: 8px 12px; color: #476d72; background: #edf5f1; border: 1px solid #d6e7df; border-radius: 8px; font-size: 12px; }
.resource-progress strong { font-size: 14px; }
.welcome { max-width: 650px; margin: 38px auto 20px; text-align: center; }
.companion-portrait { width: 78px; height: 78px; display: grid; place-items: center; margin: 0 auto 18px; color: #fff; background: radial-gradient(circle at 36% 30%, #98b9b7 0 18%, #527c84 19% 72%, #315760 73%); border: 5px double #d8c9b9; border-radius: 50%; box-shadow: 0 10px 24px rgba(68, 91, 90, .12); }
.companion-portrait span { font-family: Georgia, "Times New Roman", serif; font-size: 25px; }
.welcome h1 { margin: 0; color: #574f48; font-family: Georgia, "Songti SC", "STSong", serif; font-size: 25px; font-weight: 500; letter-spacing: .04em; }
.welcome > p { max-width: 520px; margin: 10px auto 0; color: #9a8d80; font-size: 12px; line-height: 1.8; }
.companion-choice { display: flex; justify-content: center; gap: 8px; margin-top: 18px; }
.companion-choice button { display: inline-flex; align-items: center; gap: 7px; min-height: 34px; padding: 0 13px; color: #9e9388; background: rgba(255,255,255,.56); border: 1px solid #e1d8ce; border-radius: 999px; }
.companion-choice button.active { color: #5e8589; background: #f8fbf9; border-color: #8fb0b2; box-shadow: inset 0 0 0 1px rgba(143,176,178,.2); }
.mini-avatar { width: 20px; height: 20px; display: grid; place-items: center; color: #fff; background: #668f93; border-radius: 50%; font-size: 10px; }
.muted-avatar { background: #c9c0b5; }
.workspace-memory { display: flex; justify-content: center; flex-wrap: wrap; gap: 16px; margin-top: 15px; color: #8ca4a2; font-size: 11px; }
.starter-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 24px; }
.starter-list button { min-height: 68px; padding: 10px 12px; color: #776b5f; text-align: left; line-height: 1.55; background: rgba(255, 253, 249, .75); border: 1px solid #e7ddd1; border-radius: 12px; cursor: pointer; transition: border-color .18s, transform .18s, box-shadow .18s; }
.starter-list button:hover { border-color: #9ab5b4; transform: translateY(-1px); box-shadow: 0 8px 18px rgba(96, 83, 63, .05); }
.message { max-width: 82%; margin-bottom: 16px; }
.message.user { margin-left: auto; }
.message-meta { margin-bottom: 5px; color: #a19487; font-size: 10px; }
.message.user .message-meta { text-align: right; }
.message pre { margin: 0; padding: 13px 15px; white-space: pre-wrap; overflow-wrap: anywhere; color: #514941; line-height: 1.75; font-family: inherit; border: 1px solid #e5dcd1; background: rgba(255, 254, 251, .9); border-radius: 14px 14px 14px 5px; box-shadow: 0 7px 18px rgba(93, 73, 48, .035); }
.message.user pre { color: #fff; border-color: #668f93; background: #668f93; border-radius: 14px 14px 5px 14px; }
.message.transient pre { border-style: dashed; }
.typing { margin-left: 6px; color: var(--accent); }
.stream-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 0 0 16px; padding: 12px 14px; color: #7d2734; background: #fff0f2; border-left: 4px solid var(--danger); border-radius: 8px; }
.stream-error strong { font-size: 13px; }
.stream-error p { margin: 4px 0 0; font-size: 12px; line-height: 1.55; }
.stream-interruption { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 0 0 16px; padding: 12px 14px; color: #755f3d; background: #fff6e7; border-left: 4px solid #d5a568; border-radius: 8px; }
.stream-interruption strong { font-size: 13px; }.stream-interruption p { margin: 4px 0 0; font-size: 11px; line-height: 1.55; }
.retained-interruption pre { border-style: dashed; background: #fffaf0; }
.connection-notice { margin: 2px auto 12px; padding: 8px 11px; border: 1px solid #ead7b6; border-radius: 999px; color: #7b623f; background: #fff6e6; text-align: center; font-size: 10px; }
.inline-sources { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: #9b8f82; font-size: 10px; }
.inline-sources a { color: #648c8d; text-decoration: none; }
.composer-wrap { margin-top: auto; padding: 0 16px 4px; }
.composer { padding: 13px 14px 11px; background: rgba(255, 254, 251, .94); border: 1px solid #e4dbd0; border-radius: 16px; box-shadow: 0 12px 28px rgba(82, 67, 49, .09); }
.composer :deep(.el-textarea__inner) { padding: 6px 4px; color: #51483f; background: transparent; border: 0; box-shadow: none; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 7px; }
.composer-left { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: #a09284; font-size: 10px; }
.stream-toggle { display: inline-flex; align-items: center; gap: 5px; }
.knowledge-space-modal { position: fixed; z-index: 3000; inset: 0; display: grid; place-items: center; padding: 18px; background: rgba(54, 46, 38, .28); backdrop-filter: blur(4px); }
.knowledge-space-card { width: min(520px, 100%); padding: 22px; background: #fffaf4; border: 1px solid #dfd2c4; border-radius: 18px; box-shadow: 0 24px 70px rgba(65, 49, 33, .18); }
.knowledge-space-card header { display: flex; justify-content: space-between; gap: 16px; }.knowledge-space-card header span { color: #719592; font-size: 9px; letter-spacing: .16em; }.knowledge-space-card h2 { margin: 5px 0 0; font-family: Georgia, "Songti SC", serif; font-size: 20px; font-weight: 500; }.knowledge-space-card header button { color: #9b8c7e; background: transparent; border: 0; cursor: pointer; font-size: 20px; }
.privacy-notice { padding: 10px 12px; color: #8b765e; background: #fff3df; border-radius: 9px; font-size: 10px; line-height: 1.7; }.binding-collections { display: grid; gap: 7px; max-height: 210px; margin: 14px 0; overflow: auto; }.binding-collections label { display: flex; align-items: center; gap: 9px; padding: 10px; border: 1px solid #e6dbce; border-radius: 10px; }.binding-collections strong,.binding-collections small { display: block; }.binding-collections strong { font-size: 11px; }.binding-collections small { margin-top: 3px; color: var(--muted); font-size: 9px; }.knowledge-space-card fieldset { display: grid; gap: 7px; padding: 12px; border: 1px solid #e5d9ca; border-radius: 10px; }.knowledge-space-card legend { color: #8c7f71; font-size: 10px; }.knowledge-space-card fieldset label { font-size: 10px; }.knowledge-space-card footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 15px; }.knowledge-space-card footer span { color: #a09284; font-size: 9px; }.knowledge-space-card footer button { min-height: 34px; padding: 0 14px; color: #fff; background: #668f93; border: 0; border-radius: 9px; cursor: pointer; }

@media (max-width: 760px) {
  .tutor-page { min-height: calc(100vh - 90px); }
  .tutor-statusbar { display: none; }
  .chat-panel { min-height: calc(100vh - 90px); }
  .message-list { height: calc(100vh - 285px); min-height: 360px; padding: 8px 4px 18px; }
  .welcome { margin-top: 25px; }
  .welcome h1 { font-size: 21px; }
  .starter-list { grid-template-columns: 1fr; }
  .starter-list button { min-height: 50px; }
  .message { max-width: 94%; }
  .composer-wrap { padding: 0; }
  .gentle-tip { display: none; }
  .stream-error { align-items: flex-start; flex-direction: column; }
}
</style>
