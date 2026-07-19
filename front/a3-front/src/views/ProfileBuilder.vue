<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>{{ t('views.profile.title') }}</h1><p>{{ t('views.profile.structuredProfileDescription') }}</p></div>
      <div class="toolbar">
        <el-tag v-if="backend.profileReady" type="success" effect="plain">{{ t('views.profile.profileVersionTag', { version: backend.session?.profile_version }) }}</el-tag>
        <el-button :icon="Refresh" @click="backend.refreshSession()">{{ t('views.profile.sync') }}</el-button>
        <el-button v-if="backend.session" type="danger" plain :icon="RefreshLeft" @click="restart">{{ t('views.profile.restart') }}</el-button>
      </div>
    </div>

    <template v-if="backend.profileReady">
      <div class="profile-grid">
        <article class="profile-main panel">
          <div class="profile-heading">
            <div class="profile-avatar"><el-icon><User /></el-icon></div>
            <div><span>{{ fields['\u5e74\u7ea7'] || t('views.profile.grade') }}</span><h2>{{ fields['\u5b66\u79d1'] || t('views.profile.title') }}</h2><p>{{ fields['\u5b66\u4e60\u76ee\u6807'] }}</p></div>
          </div>
          <div class="field-grid">
            <div v-for="item in primaryFields" :key="item.label" class="field-item">
              <span>{{ item.label }}</span><strong>{{ item.value || t('views.profile.unspecified') }}</strong>
            </div>
          </div>
          <div class="profile-section"><span>{{ t('views.profile.knowledgePointWeak') }}</span><div class="tags"><el-tag v-for="item in weaknesses" :key="item" type="warning" effect="plain">{{ item }}</el-tag></div></div>
          <div class="profile-section"><span>{{ t('views.profile.difficulty') }}</span><div class="tags"><el-tag v-for="item in difficulties" :key="item" effect="plain">{{ item }}</el-tag></div></div>
        </article>

        <article class="panel">
          <div class="panel-header"><h2>{{ t('views.profile.profile') }}</h2></div>
          <div class="panel-body evidence-list">
            <div><span>{{ t('views.profile.style') }}</span><p>{{ fields['\u5b66\u4e60\u98ce\u683c\u8bc1\u636e'] }}</p></div>
            <div><span>{{ t('views.profile.modelConfidence') }}</span><p>{{ confidence }}</p></div>
            <div><span>{{ t('views.profile.pendingQuestions') }}</span><p>{{ fields['\u5f85\u786e\u8ba4\u95ee\u9898'] || t('views.profile.noPendingQuestions') }}</p></div>
          </div>
        </article>
      </div>

      <article class="panel dialogue-panel">
        <div class="panel-header"><h2>{{ t('views.profile.diagnosisConversation') }}</h2><span class="muted">{{ t('views.profile.diagnosticMessageCount', { count: diagnosticMessages.length }) }}</span></div>
        <div class="panel-body dialogue-list">
          <div v-for="message in diagnosticMessages" :key="message.seq" class="dialogue-row" :class="message.role">
            <span>{{ message.role === 'user' ? t('views.profile.learner') : t('views.profile.profileAgent') }}</span>
            <p>{{ message.content }}</p>
          </div>
        </div>
      </article>
    </template>

    <div v-else class="panel empty-block">
      <div><el-icon :size="34"><User /></el-icon><p>{{ t('views.profile.profileNotGenerated') }}</p><el-button type="primary" @click="router.push('/tutor')">{{ t('views.profile.startDiagnosis') }}</el-button></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, RefreshLeft, User } from '@element-plus/icons-vue'
import { backendApi } from '@/api'
import { useBackendStore } from '@/stores/backend'
import { LEARNER_PROFILE_PROTOCOL_PREFIX, protocolFields } from '@/utils/protocol'
import { formatPercent } from '@/i18n/formatters'

const { t } = useI18n()

const backend = useBackendStore()
const router = useRouter()
const fields = computed(() => protocolFields(backend.session?.profile_text))
const primaryFields = computed(() => [
  { label: t('views.profile.current'), value: fields.value['\u5f53\u524d\u6c34\u5e73'] },
  { label: t('views.profile.styleTitle'), value: fields.value['\u5b66\u4e60\u98ce\u683c\u504f\u597d'] },
  { label: t('views.profile.level'), value: fields.value['\u8ba4\u77e5\u5c42\u6b21'] },
  { label: t('views.profile.profileVersion'), value: fields.value['\u753b\u50cf\u7248\u672c'] },
])
const weaknesses = computed(() => (fields.value['\u8584\u5f31\u77e5\u8bc6\u70b9'] || '').split('｜').filter(Boolean))
const difficulties = computed(() => (fields.value['\u63a8\u8350\u96be\u5ea6'] || '').split('｜').filter(Boolean))
const confidence = computed(() => formatPercent(Number(fields.value['\u7f6e\u4fe1\u5ea6'] || 0), { maximumFractionDigits: 0 }))
const diagnosticMessages = computed(() => {
  const history = backend.session?.messages || []
  const profileIndex = history.findIndex(message => (
    message.role === 'assistant' && message.content.startsWith(LEARNER_PROFILE_PROTOCOL_PREFIX)
  ))
  return (profileIndex >= 0 ? history.slice(0, profileIndex + 1) : history).slice(0, 8)
})

async function restart() {
  try {
    await ElMessageBox.confirm(t('views.profile.restartPreservesLearningData'), t('views.profile.restart'), { type: 'warning' })
    await backendApi.rediagnose(backend.sessionId)
    await backend.refreshSession()
    ElMessage.success(t('views.profile.diagnosisRestarted'))
    router.push('/tutor')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(t('views.profile.diagnosisRestartFailure'))
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
