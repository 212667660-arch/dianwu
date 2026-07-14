<template>
  <section class="page tutor-page">
    <div class="page-heading">
      <div><h1>学习助手</h1><p>通过多轮对话完成诊断、画像与个性化资源生成</p></div>
      <div class="toolbar">
        <span class="status-pill" :class="backend.ready ? 'good' : 'bad'">{{ backend.ready ? '模型就绪' : '模型未就绪' }}</span>
        <span class="status-pill">{{ phaseLabel }}</span>
      </div>
    </div>

    <div class="tutor-layout">
      <article class="chat-panel panel">
        <div ref="messageList" class="message-list">
          <div v-if="!messages.length && !pendingUser" class="welcome">
            <div class="welcome-icon"><el-icon><ChatDotRound /></el-icon></div>
            <h2>从你的学习目标开始</h2>
            <p>画像 Agent 会先了解基础与薄弱点，随后资源 Agent 生成笔记和练习。</p>
            <div class="starter-list">
              <button v-for="starter in starters" :key="starter" @click="editor = starter">{{ starter }}</button>
            </div>
          </div>

          <div v-for="message in messages" :key="message.seq" class="message" :class="message.role">
            <div class="message-meta">{{ message.role === 'user' ? '你' : '学习 Agent' }}</div>
            <pre>{{ message.content }}</pre>
          </div>
          <div v-if="pendingUser" class="message user transient"><div class="message-meta">你</div><pre>{{ pendingUser }}</pre></div>
          <div v-if="generating || streamText" class="message assistant transient">
            <div class="message-meta">{{ activePhase }} Agent <span v-if="generating" class="typing">生成中</span></div>
            <pre>{{ streamText || '正在准备响应...' }}</pre>
          </div>
          <div v-if="streamError" class="stream-error" role="alert">
            <div><strong>本次请求未完成</strong><p>{{ streamError }}</p></div>
            <el-button text type="primary" @click="restoreFailedMessage">重新编辑</el-button>
          </div>
        </div>

        <div class="composer">
          <el-input v-model="editor" type="textarea" :rows="3" maxlength="8000" show-word-limit resize="none" placeholder="输入学习目标、回答诊断问题，或提出资源生成需求" @keydown.ctrl.enter.prevent="send" />
          <div class="composer-actions">
            <div class="stream-toggle"><span>流式输出</span><el-switch v-model="useStream" /></div>
            <div class="toolbar">
              <el-button v-if="generating" type="danger" plain :icon="Close" @click="cancel">取消</el-button>
              <el-button type="primary" :icon="Promotion" :loading="generating" :disabled="!editor.trim() || !backend.modelConfigured" @click="send">发送</el-button>
            </div>
          </div>
        </div>
      </article>

      <aside class="context-column">
        <article class="panel">
          <div class="panel-header"><h2>当前学习上下文</h2></div>
          <div class="panel-body context-list">
            <div><span>会话状态</span><strong>{{ backend.session?.state || '未开始' }}</strong></div>
            <div><span>画像版本</span><strong>v{{ backend.session?.profile_version || 0 }}</strong></div>
            <div><span>知识点</span><strong>{{ backend.progress?.knowledge_points.length || 0 }}</strong></div>
            <div><span>学习状态版本</span><strong>v{{ backend.session?.learning_state_version || 0 }}</strong></div>
          </div>
        </article>

        <article v-if="backend.nextAction" class="panel action-panel">
          <div class="panel-header"><h2>推荐下一步</h2></div>
          <div class="panel-body">
            <span class="status-pill good">{{ actionLabel(backend.nextAction.action) }}</span>
            <h3>{{ backend.nextAction.knowledge_point || '学习诊断' }}</h3>
            <p>{{ backend.nextAction.reason }}</p>
            <el-button text type="primary" @click="editor = backend.nextAction?.suggested_request || ''">填入建议任务</el-button>
          </div>
        </article>

        <article v-if="sources.length" class="panel">
          <div class="panel-header"><h2>参考来源</h2><span class="muted">{{ sources.length }}</span></div>
          <div class="panel-body source-list">
            <a v-for="source in sources" :key="source.url" :href="source.url" target="_blank" rel="noreferrer"><strong>{{ source.title }}</strong><span>{{ source.snippet }}</span></a>
          </div>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Promotion } from '@element-plus/icons-vue'
import { backendApi, DesktopApiError, errorMessage, type SourceItem, type StreamEvent } from '@/api'
import { useBackendStore } from '@/stores/backend'
import { actionLabel } from '@/utils/protocol'

const backend = useBackendStore()
const route = useRoute()
const editor = ref('')
const useStream = ref(true)
const generating = ref(false)
const generationId = ref('')
const activePhase = ref('诊断')
const streamText = ref('')
const pendingUser = ref('')
const streamError = ref('')
const failedMessage = ref('')
const sources = ref<SourceItem[]>([])
const messageList = ref<HTMLElement>()
let controller: AbortController | null = null

const messages = computed(() => backend.session?.messages || [])
const phaseLabel = computed(() => generating.value ? `${activePhase.value}中` : backend.session?.state || '等待开始')
const starters = ['我想学习一次函数，请先了解我的基础。', '我正在准备英语考试，希望制定复习计划。', '根据我的薄弱点生成一份笔记和分层练习。']

async function scrollBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

function handleEvent(event: StreamEvent) {
  if (event.generation_id) generationId.value = event.generation_id
  if (event.phase) activePhase.value = event.phase === 'profile' ? '画像' : event.phase === 'resource' ? '资源' : '诊断'
  if (event.event === 'delta' && event.content) streamText.value += event.content
  if (event.event === 'replace' && event.content) streamText.value = event.content
  if (event.event === 'sources') sources.value = event.sources || []
  if (event.event === 'error') {
    streamError.value = event.message || event.code || '生成失败，请检查后重试。'
    ElMessage.error(streamError.value)
  }
  scrollBottom()
}

function restoreFailedMessage() {
  editor.value = failedMessage.value
  streamError.value = ''
  streamText.value = ''
}

async function send() {
  const message = editor.value.trim()
  if (!message || generating.value || !backend.modelConfigured) return
  generating.value = true
  pendingUser.value = message
  editor.value = ''
  streamText.value = ''
  streamError.value = ''
  failedMessage.value = ''
  generationId.value = ''
  sources.value = []
  controller = new AbortController()
  await scrollBottom()
  try {
    if (useStream.value) {
      await backendApi.streamChat(backend.sessionId, message, handleEvent, controller.signal)
    } else {
      const response = await backendApi.chat(backend.sessionId, message)
      streamText.value = response.reply
      sources.value = response.sources
      activePhase.value = response.phase === 'profile' ? '画像' : response.phase === 'resource' ? '资源' : '诊断'
    }
    await backend.refreshSession()
    if (streamError.value) {
      failedMessage.value = message
      pendingUser.value = ''
    } else {
      pendingUser.value = ''
      streamText.value = ''
    }
  } catch (error) {
    if (!isCancellationError(error)) {
      streamError.value = errorMessage(error)
      failedMessage.value = message
      pendingUser.value = ''
      ElMessage.error(streamError.value)
    }
  } finally {
    generating.value = false
    controller = null
    generationId.value = ''
    await scrollBottom()
  }
}

function isCancellationError(error: unknown) {
  return (error as Error | undefined)?.name === 'AbortError'
    || (error instanceof DesktopApiError && error.code === 'DESKTOP_STREAM_CANCELLED')
}

async function cancel() {
  if (!generationId.value) {
    controller?.abort()
    return
  }
  try {
    await backendApi.cancelGeneration(generationId.value, backend.sessionId)
    ElMessage.info('已请求取消生成')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    controller?.abort()
  }
}

onMounted(() => {
  const prompt = typeof route.query.prompt === 'string' ? route.query.prompt : ''
  if (prompt) editor.value = prompt
})
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped lang="scss">
.tutor-layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
.chat-panel { min-height: calc(100vh - 130px); display: flex; flex-direction: column; }
.message-list { height: calc(100vh - 340px); min-height: 360px; overflow: auto; padding: 18px; }
.welcome { max-width: 620px; margin: 50px auto; text-align: center; }
.welcome-icon { width: 52px; height: 52px; display: grid; place-items: center; margin: 0 auto 12px; color: #fff; background: #32575b; border-radius: 6px; font-size: 23px; }
.welcome h2 { margin: 0 0 7px; font-size: 20px; }
.welcome p { margin: 0; color: var(--muted); line-height: 1.65; }
.starter-list { display: grid; gap: 7px; margin-top: 20px; }
.starter-list button { padding: 10px 12px; text-align: left; color: #42535d; background: #fff; border: 1px solid var(--line); border-radius: 5px; cursor: pointer; }
.starter-list button:hover { border-color: var(--accent); color: var(--accent); }
.message { max-width: 86%; margin-bottom: 16px; }
.message.user { margin-left: auto; }
.message-meta { margin-bottom: 4px; color: var(--muted); font-size: 11px; }
.message.user .message-meta { text-align: right; }
.message pre { margin: 0; padding: 12px 14px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; font-family: inherit; border: 1px solid var(--line); background: #fff; border-radius: 6px; }
.message.user pre { color: #fff; border-color: #32575b; background: #32575b; }
.message.transient pre { border-style: dashed; }
.typing { margin-left: 6px; color: var(--accent); }
.stream-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 0 18px 16px; padding: 12px 14px; color: #7d2734; background: #fff0f2; border-left: 4px solid var(--danger); }
.stream-error strong { font-size: 13px; }
.stream-error p { margin: 4px 0 0; font-size: 12px; line-height: 1.55; }
.composer { margin-top: auto; padding: 14px; border-top: 1px solid var(--line); background: var(--surface-soft); }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 9px; }
.stream-toggle { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
.context-column { display: grid; gap: 16px; }
.context-list { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.context-list div { padding: 10px; background: var(--surface-soft); }
.context-list span, .context-list strong { display: block; }
.context-list span { color: var(--muted); font-size: 10px; }
.context-list strong { margin-top: 3px; font-size: 13px; overflow-wrap: anywhere; }
.action-panel h3 { margin: 12px 0 5px; }
.action-panel p { margin: 0; color: var(--muted); line-height: 1.6; font-size: 12px; }
.source-list { display: grid; gap: 10px; }
.source-list a { color: inherit; text-decoration: none; }
.source-list strong, .source-list span { display: block; }
.source-list strong { color: var(--accent); font-size: 12px; }
.source-list span { margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.45; }
@media (max-width: 980px) { .tutor-layout { grid-template-columns: 1fr; } .context-column { grid-template-columns: repeat(2, minmax(0, 1fr)); } .chat-panel { min-height: 650px; } .message-list { height: 430px; } }
@media (max-width: 620px) { .context-column { grid-template-columns: 1fr; } .message { max-width: 96%; } .composer-actions { align-items: flex-end; } .stream-error { align-items: flex-start; flex-direction: column; } }
</style>
