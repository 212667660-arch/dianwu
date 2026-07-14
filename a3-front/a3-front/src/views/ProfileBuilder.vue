<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>学习画像</h1><p>画像 Agent 根据诊断对话生成的结构化学习者信息</p></div>
      <div class="toolbar">
        <el-tag v-if="backend.profileReady" type="success" effect="plain">画像 v{{ backend.session?.profile_version }}</el-tag>
        <el-button :icon="Refresh" @click="backend.refreshSession()">同步</el-button>
        <el-button v-if="backend.session" type="danger" plain :icon="RefreshLeft" @click="restart">重新诊断</el-button>
      </div>
    </div>

    <template v-if="backend.profileReady">
      <div class="profile-grid">
        <article class="profile-main panel">
          <div class="profile-heading">
            <div class="profile-avatar"><el-icon><User /></el-icon></div>
            <div><span>{{ fields['年级'] || '年级未明确' }}</span><h2>{{ fields['学科'] || '学习画像' }}</h2><p>{{ fields['学习目标'] }}</p></div>
          </div>
          <div class="field-grid">
            <div v-for="item in primaryFields" :key="item.label" class="field-item">
              <span>{{ item.label }}</span><strong>{{ item.value || '未明确' }}</strong>
            </div>
          </div>
          <div class="profile-section"><span>薄弱知识点</span><div class="tags"><el-tag v-for="item in weaknesses" :key="item" type="warning" effect="plain">{{ item }}</el-tag></div></div>
          <div class="profile-section"><span>推荐难度</span><div class="tags"><el-tag v-for="item in difficulties" :key="item" effect="plain">{{ item }}</el-tag></div></div>
        </article>

        <article class="panel">
          <div class="panel-header"><h2>画像依据</h2></div>
          <div class="panel-body evidence-list">
            <div><span>学习风格证据</span><p>{{ fields['学习风格证据'] }}</p></div>
            <div><span>模型置信度</span><p>{{ confidence }}</p></div>
            <div><span>待确认问题</span><p>{{ fields['待确认问题'] || '无' }}</p></div>
          </div>
        </article>
      </div>

      <article class="panel dialogue-panel">
        <div class="panel-header"><h2>诊断对话记录</h2><span class="muted">{{ diagnosticMessages.length }} 条</span></div>
        <div class="panel-body dialogue-list">
          <div v-for="message in diagnosticMessages" :key="message.seq" class="dialogue-row" :class="message.role">
            <span>{{ message.role === 'user' ? '学习者' : '画像 Agent' }}</span>
            <p>{{ message.content }}</p>
          </div>
        </div>
      </article>
    </template>

    <div v-else class="panel empty-block">
      <div><el-icon :size="34"><User /></el-icon><p>当前会话尚未生成学习画像</p><el-button type="primary" @click="router.push('/tutor')">开始诊断</el-button></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, RefreshLeft, User } from '@element-plus/icons-vue'
import { backendApi } from '@/api'
import { useBackendStore } from '@/stores/backend'
import { protocolFields } from '@/utils/protocol'

const backend = useBackendStore()
const router = useRouter()
const fields = computed(() => protocolFields(backend.session?.profile_text))
const primaryFields = computed(() => [
  { label: '当前水平', value: fields.value['当前水平'] },
  { label: '学习风格', value: fields.value['学习风格偏好'] },
  { label: '认知层次', value: fields.value['认知层次'] },
  { label: '画像版本', value: fields.value['画像版本'] },
])
const weaknesses = computed(() => (fields.value['薄弱知识点'] || '').split('｜').filter(Boolean))
const difficulties = computed(() => (fields.value['推荐难度'] || '').split('｜').filter(Boolean))
const confidence = computed(() => `${Math.round(Number(fields.value['置信度'] || 0) * 100)}%`)
const diagnosticMessages = computed(() => {
  const history = backend.session?.messages || []
  const profileIndex = history.findIndex(message => (
    message.role === 'assistant' && message.content.startsWith('【协议:learner-profile/v1】')
  ))
  return (profileIndex >= 0 ? history.slice(0, profileIndex + 1) : history).slice(0, 8)
})

async function restart() {
  try {
    await ElMessageBox.confirm('将进入重新诊断状态，已有资源和答题记录仍会保留。', '重新诊断', { type: 'warning' })
    await backendApi.rediagnose(backend.sessionId)
    await backend.refreshSession()
    ElMessage.success('已进入重新诊断')
    router.push('/tutor')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('重新诊断失败')
  }
}
</script>

<style scoped lang="scss">
.profile-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, .6fr); gap: 16px; }
.profile-main { padding: 20px; }
.profile-heading { display: flex; align-items: center; gap: 15px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.profile-avatar { width: 54px; height: 54px; display: grid; place-items: center; border-radius: 6px; color: #fff; background: #32575b; font-size: 24px; }
.profile-heading span { color: var(--muted); font-size: 12px; }
.profile-heading h2 { margin: 1px 0 3px; font-size: 20px; }
.profile-heading p { margin: 0; color: var(--muted); }
.field-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 18px 0; }
.field-item { padding: 12px; background: var(--surface-soft); border: 1px solid var(--line); }
.field-item span, .profile-section > span, .evidence-list span { color: var(--muted); font-size: 11px; }
.field-item strong { display: block; margin-top: 4px; font-size: 14px; }
.profile-section { display: flex; align-items: flex-start; gap: 16px; margin-top: 12px; }
.profile-section > span { width: 76px; padding-top: 5px; }
.tags { display: flex; flex-wrap: wrap; gap: 7px; }
.evidence-list > div { padding: 0 0 14px; margin-bottom: 14px; border-bottom: 1px solid var(--line); }
.evidence-list > div:last-child { border: 0; margin: 0; padding: 0; }
.evidence-list p { margin: 4px 0 0; line-height: 1.65; }
.dialogue-panel { margin-top: 16px; }
.dialogue-row { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--line); }
.dialogue-row:last-child { border: 0; }
.dialogue-row span { color: var(--muted); font-size: 12px; }
.dialogue-row p { margin: 0; white-space: pre-wrap; line-height: 1.65; }
@media (max-width: 900px) { .profile-grid { grid-template-columns: 1fr; } .field-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 520px) { .field-grid { grid-template-columns: 1fr; } }
</style>
