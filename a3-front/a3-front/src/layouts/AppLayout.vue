<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <el-button class="mobile-menu" text :icon="Menu" aria-label="打开导航" @click="drawerOpen = true" />
        <div class="brand-mark"><el-icon><Reading /></el-icon></div>
        <div>
          <strong>智学协作台</strong>
          <span>学习伙伴 · 专注当下</span>
        </div>
      </div>

      <div class="topbar-actions">
        <span class="desktop-mode">学习工作台</span>
        <div class="service-state" :class="{ online: backend.live }">
          <i />{{ backend.live ? (backend.ready ? '模型就绪' : '后端在线') : '服务离线' }}
        </div>
        <el-input v-model="sessionDraft" class="session-input" size="small" maxlength="64" aria-label="会话 ID">
          <template #prepend>会话</template>
        </el-input>
        <el-tooltip content="切换并同步会话" placement="bottom">
          <el-button :icon="Refresh" size="small" aria-label="切换并同步会话" :loading="backend.loading" @click="applySession" />
        </el-tooltip>
      </div>
    </header>

    <div class="workspace">
      <aside class="sidebar">
        <div class="sidebar-heading">
          <span>学习空间</span>
          <el-button text size="small" :icon="ChatLineRound" aria-label="新学习会话" @click="router.push('/tutor')" />
        </div>
        <nav>
          <RouterLink v-for="item in menuRoutes" :key="item.path" :to="item.path" class="nav-item">
            <el-icon><component :is="item.meta?.icon" /></el-icon>
            <span>{{ item.meta?.title }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-foot">
          <span>当前状态</span>
          <strong>{{ stateLabel }}</strong>
        </div>
      </aside>

      <main class="main-content"><RouterView /></main>
    </div>

    <el-drawer v-model="drawerOpen" direction="ltr" size="260px" :with-header="false">
      <div class="drawer-brand">智学协作台</div>
      <nav @click="drawerOpen = false">
        <RouterLink v-for="item in menuRoutes" :key="item.path" :to="item.path" class="nav-item">
          <el-icon><component :is="item.meta?.icon" /></el-icon>
          <span>{{ item.meta?.title }}</span>
        </RouterLink>
      </nav>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChatLineRound, Menu, Reading, Refresh } from '@element-plus/icons-vue'
import { routes } from '@/router'
import { useBackendStore } from '@/stores/backend'
import { useRoute, useRouter } from 'vue-router'

const backend = useBackendStore()
const router = useRouter()
const route = useRoute()
const drawerOpen = ref(false)
const sessionDraft = ref(backend.sessionId)
const menuRoutes = computed(() => routes.find(item => item.path === '/')?.children || [])
const stateLabel = computed(() => backend.session?.state || '尚未开始')
let disposeBackendExit: (() => void) | undefined

async function applySession() {
  backend.setSessionId(sessionDraft.value)
  sessionDraft.value = backend.sessionId
  await backend.refreshAll()
}

onMounted(async () => {
  disposeBackendExit = window.a3Desktop?.onBackendExit?.(() => {
    backend.live = false
    backend.ready = false
    backend.lastError = '本地学习服务已停止，请重启桌面应用。'
  })
  await backend.refreshAll()
  if (backend.live && !backend.modelConfigured && route.path !== '/model-settings') {
    await router.replace('/model-settings')
  }
})
onBeforeUnmount(() => disposeBackendExit?.())
</script>
