<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <el-button class="mobile-menu" text :icon="Menu" aria-label="打开导航" @click="drawerOpen = true" />
        <div class="brand-mark"><el-icon><Reading /></el-icon></div>
        <div><strong>智学协作台</strong><span>给学习留一点温度</span></div>
      </div>
      <div class="topbar-space"><span>当前空间</span><strong>{{ sessionLabel }}</strong></div>
      <div class="topbar-actions">
        <el-button class="desk-toggle" text :icon="Notebook" aria-label="打开书桌" data-test="desk-toggle" @click="deskDrawerOpen = true" />
        <div class="service-state" :class="{ online: backend.live }"><i />{{ backend.live ? (backend.ready ? '模型就绪' : '后端在线') : '服务离线' }}</div>
        <el-input v-model="sessionDraft" class="session-input" size="small" maxlength="64" aria-label="会话 ID"><template #prepend>会话</template></el-input>
        <el-tooltip content="切换并同步会话" placement="bottom"><el-button :icon="Refresh" size="small" aria-label="切换并同步会话" :loading="backend.loading" @click="applySession" /></el-tooltip>
      </div>
    </header>
    <div class="workspace">
      <ConversationRail :session-label="sessionLabel" :session-state="stateLabel" :active-path="route.path" @new-session="startNewSession" />
      <main class="main-content"><RouterView /></main>
      <DeskPanel :next-action="backend.nextAction" :mastery="mastery" :resource-count="backend.resources.length" :sources="deskSources" @use-suggestion="useSuggestion" />
    </div>
    <el-drawer v-model="drawerOpen" direction="ltr" size="280px" :with-header="false"><ConversationRail :session-label="sessionLabel" :session-state="stateLabel" :active-path="route.path" @new-session="startNewSession" /></el-drawer>
    <el-drawer v-model="deskDrawerOpen" direction="rtl" size="310px" :with-header="false"><DeskPanel :next-action="backend.nextAction" :mastery="mastery" :resource-count="backend.resources.length" :sources="deskSources" @use-suggestion="useSuggestion" /></el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Menu, Notebook, Reading, Refresh } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import ConversationRail from '@/components/workspace/ConversationRail.vue'
import DeskPanel from '@/components/workspace/DeskPanel.vue'
import { useBackendStore } from '@/stores/backend'
const backend = useBackendStore()
const router = useRouter()
const route = useRoute()
const drawerOpen = ref(false)
const deskDrawerOpen = ref(false)
const sessionDraft = ref(backend.sessionId)
const stateLabel = computed(() => backend.session?.state || '尚未开始')
const sessionLabel = computed(() => {
  const firstUserMessage = backend.session?.messages.find(message => message.role === 'user')?.content?.trim()
  if (!firstUserMessage) return '新的学习空间'
  return firstUserMessage.length > 22 ? `${firstUserMessage.slice(0, 22)}…` : firstUserMessage
})
const mastery = computed(() => {
  const points = backend.progress?.knowledge_points || []
  if (!points.length) return 0
  return points.reduce((sum, point) => sum + point.mastery_score, 0) / points.length
})
const deskSources = computed(() => backend.resources.at(-1)?.sources || [])
let disposeBackendExit: (() => void) | undefined
async function applySession() { backend.setSessionId(sessionDraft.value); sessionDraft.value = backend.sessionId; await backend.refreshAll() }
async function startNewSession() { backend.setSessionId(`student_${Date.now().toString(36)}`); sessionDraft.value = backend.sessionId; drawerOpen.value = false; await backend.refreshAll(); await router.push('/tutor') }
function useSuggestion(prompt: string) { drawerOpen.value = false; deskDrawerOpen.value = false; router.push({ path: '/tutor', query: { prompt } }) }
onMounted(async () => {
  disposeBackendExit = window.a3Desktop?.onBackendExit?.(() => { backend.live = false; backend.ready = false; backend.lastError = '本地学习服务已停止，请重启桌面应用。' })
  await backend.refreshAll()
  if (backend.live && !backend.modelConfigured && route.path !== '/model-settings') await router.replace('/model-settings')
})
onBeforeUnmount(() => disposeBackendExit?.())
</script>
