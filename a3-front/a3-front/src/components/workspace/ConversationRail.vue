<template>
  <aside class="conversation-rail" data-test="conversation-rail">
    <div class="rail-heading">
      <div>
        <span class="rail-kicker">学习空间</span>
        <strong>对话</strong>
      </div>
      <el-button text circle :icon="Plus" aria-label="新学习会话" @click="$emit('new-session')" />
    </div>

    <div class="session-card">
      <div class="session-avatar"><el-icon><ChatDotRound /></el-icon></div>
      <div class="session-copy">
        <strong>{{ sessionLabel || '还没有学习对话' }}</strong>
        <span>{{ sessionState || '从一句想学的话开始' }}</span>
      </div>
      <span class="session-dot" :class="{ online: sessionState }" />
    </div>
    <div class="session-switcher">
      <input v-model="sessionDraft" maxlength="64" aria-label="会话 ID" />
      <button type="button" aria-label="切换会话" @click="$emit('switch-session', sessionDraft)">↻</button>
    </div>

    <nav class="rail-nav" aria-label="学习空间导航">
      <RouterLink v-for="item in spaces" :key="item.path" :to="item.path" class="rail-item" :class="{ active: activePath === item.path }">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="rail-section-label">最近访问</div>
    <div class="rail-hint"><el-icon><Clock /></el-icon><span>你的学习轨迹会留在这里</span></div>

    <div class="rail-footer">
      <button class="account-slot" type="button" disabled aria-label="账号功能预留">
        <span class="account-avatar"><el-icon><UserFilled /></el-icon></span>
        <span><strong>学习者</strong><small>账号功能预留</small></span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChatDotRound, Clock, Collection, FolderOpened, Notebook, Plus, Setting, UserFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  sessionLabel?: string
  sessionState?: string
  sessionId?: string
  activePath?: string
}>()

defineEmits<{
  (event: 'new-session'): void
  (event: 'switch-session', sessionId: string): void
}>()

const sessionDraft = ref(props.sessionId || '')
watch(() => props.sessionId, value => { sessionDraft.value = value || '' })

const spaces = [
  { path: '/tutor', label: '学习助手', icon: ChatDotRound },
  { path: '/dashboard', label: '我的进度', icon: Collection },
  { path: '/learning-path', label: '学习路径', icon: FolderOpened },
  { path: '/assessment', label: '练习与复习', icon: Notebook },
  { path: '/knowledge', label: '本地知识库', icon: Collection },
  { path: '/model-settings', label: '模型设置', icon: Setting },
]
</script>

<style scoped lang="scss">
.conversation-rail { display: flex; flex-direction: column; min-width: 0; height: 100%; padding: 24px 16px 16px; background: rgba(249, 245, 238, .82); border-right: 1px solid var(--line); }
.rail-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 8px 18px; }
.rail-heading strong, .rail-kicker { display: block; }
.rail-kicker { margin-bottom: 3px; color: var(--muted); font-size: 11px; letter-spacing: .12em; }
.rail-heading strong { font-size: 19px; font-weight: 650; }
.rail-heading .el-button { color: var(--muted); }
.session-card { display: flex; align-items: center; gap: 9px; min-height: 58px; padding: 10px; background: rgba(255, 252, 246, .82); border: 1px solid #e9dfd2; border-radius: 13px; box-shadow: 0 8px 18px rgba(102, 78, 45, .04); }
.session-avatar { width: 30px; height: 30px; display: grid; place-items: center; flex: 0 0 auto; color: #507c82; background: #e6f0ed; border-radius: 50%; }
.session-copy { min-width: 0; flex: 1; }
.session-copy strong, .session-copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-copy strong { color: var(--ink); font-size: 12px; }
.session-copy span { margin-top: 3px; color: var(--muted); font-size: 10px; }
.session-dot { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: #d9cec0; }
.session-dot.online { background: #83aaa0; }
.session-switcher { display: grid; grid-template-columns: minmax(0, 1fr) 30px; gap: 6px; margin-top: 7px; }
.session-switcher input { min-width: 0; height: 30px; padding: 0 9px; color: #75695d; background: rgba(255, 252, 246, .6); border: 1px solid #e8ddd0; border-radius: 9px; outline: 0; font-size: 10px; }
.session-switcher input:focus { border-color: #9db6b5; box-shadow: 0 0 0 2px rgba(107, 151, 155, .08); }
.session-switcher button { color: #729292; background: #edf4f1; border: 1px solid #dce9e4; border-radius: 9px; cursor: pointer; }
.rail-nav { display: grid; gap: 4px; margin-top: 20px; }
.rail-item { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 0 11px; color: #7c7063; text-decoration: none; border-radius: 11px; transition: color .18s, background .18s, transform .18s; }
.rail-item:hover { color: var(--ink); background: rgba(255, 252, 246, .75); transform: translateX(1px); }
.rail-item.active { color: #4f7f85; background: #e5efec; font-weight: 600; }
.rail-item .el-icon { font-size: 16px; }
.rail-section-label { margin: 27px 10px 8px; color: #a09284; font-size: 10px; letter-spacing: .12em; }
.rail-hint { display: flex; align-items: flex-start; gap: 8px; padding: 10px; color: #a09284; font-size: 11px; line-height: 1.5; }
.rail-footer { margin-top: auto; padding-top: 14px; border-top: 1px solid #eadfd3; }
.account-slot { display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px; color: var(--muted); text-align: left; background: transparent; border: 0; border-radius: 10px; opacity: .72; }
.account-avatar { width: 28px; height: 28px; display: grid; place-items: center; color: #8e8172; background: #eee5da; border-radius: 50%; }
.account-slot strong, .account-slot small { display: block; }
.account-slot strong { color: #776b5f; font-size: 11px; }
.account-slot small { margin-top: 2px; color: #a39587; font-size: 10px; }
</style>
