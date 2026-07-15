<template>
  <section class="page tutor-page">
    <div class="tutor-statusbar">
      <span class="status-pill" :class="backend.ready ? 'good' : 'bad'">{{ backend.ready ? '模型就绪' : '模型未就绪' }}</span>
      <span class="status-pill">{{ phaseLabel }}</span>
    </div>

    <article class="chat-panel">
      <div ref="messageList" class="message-list">
        <div v-if="!messages.length && !pendingUser" class="welcome" :data-companion-id="companionId">
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

        <div v-for="message in messages" :key="message.seq" class="message" :class="message.role">
          <div class="message-meta">{{ message.role === 'user' ? '你' : '学习伙伴' }}</div>
          <pre>{{ message.content }}</pre>
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
        <div v-if="sources.length" class="inline-sources">
          <span>这次参考了</span>
          <a v-for="source in sources" :key="source.url" :href="source.url" target="_blank" rel="noreferrer">{{ source.title }}</a>
        </div>
      </div>

      <div class="composer-wrap">
        <div class="composer">
          <el-input v-model="editor" type="textarea" :rows="3" maxlength="8000" show-word-limit resize="none" placeholder="说点什么…" @keydown.ctrl.enter.prevent="send" />
          <div class="composer-actions">
            <div class="composer-left"><span class="gentle-tip">写下目标、问题，或此刻的困惑</span><span class="stream-toggle">流式 <el-switch v-model="useStream" /></span></div>
            <div class="toolbar">
              <el-button v-if="generating" type="danger" plain :icon="Close" @click="cancel">取消</el-button>
              <el-button type="primary" :icon="Promotion" :loading="generating" :disabled="!editor.trim() || !backend.modelConfigured" @click="send">发送</el-button>
            </div>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Close, Promotion } from '@element-plus/icons-vue'
import { backendApi, DesktopApiError, errorMessage, type SourceItem, type StreamEvent } from '@/api'
import { useBackendStore } from '@/stores/backend'

const backend = useBackendStore()
const route = useRoute()
const companionId = 'study-companion'
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

function restoreFailedMessage() { editor.value = failedMessage.value; streamError.value = ''; streamText.value = '' }

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
    if (streamError.value) { failedMessage.value = message; pendingUser.value = '' }
    else { pendingUser.value = ''; streamText.value = '' }
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
  return (error as Error | undefined)?.name === 'AbortError' || (error instanceof DesktopApiError && error.code === 'DESKTOP_STREAM_CANCELLED')
}

async function cancel() {
  if (!generationId.value) { controller?.abort(); return }
  try { await backendApi.cancelGeneration(generationId.value, backend.sessionId); ElMessage.info('已请求取消生成') }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { controller?.abort() }
}

onMounted(() => { const prompt = typeof route.query.prompt === 'string' ? route.query.prompt : ''; if (prompt) editor.value = prompt })
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped lang="scss">
.tutor-page { max-width: 940px; min-height: calc(100vh - 138px); }
.tutor-statusbar { display: flex; justify-content: flex-end; gap: 7px; min-height: 28px; }
.chat-panel { min-height: calc(100vh - 166px); display: flex; flex-direction: column; }
.message-list { height: calc(100vh - 340px); min-height: 390px; overflow: auto; padding: 10px 28px 24px; scrollbar-width: thin; scrollbar-color: #ded5c9 transparent; }
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
.inline-sources { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: #9b8f82; font-size: 10px; }
.inline-sources a { color: #648c8d; text-decoration: none; }
.composer-wrap { margin-top: auto; padding: 0 16px 4px; }
.composer { padding: 13px 14px 11px; background: rgba(255, 254, 251, .94); border: 1px solid #e4dbd0; border-radius: 16px; box-shadow: 0 12px 28px rgba(82, 67, 49, .09); }
.composer :deep(.el-textarea__inner) { padding: 6px 4px; color: #51483f; background: transparent; border: 0; box-shadow: none; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 7px; }
.composer-left { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: #a09284; font-size: 10px; }
.stream-toggle { display: inline-flex; align-items: center; gap: 5px; }

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
