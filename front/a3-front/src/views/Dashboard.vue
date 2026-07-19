<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>{{ t('views.dashboard.title') }}</h1>
        <p>{{ t('views.dashboard.currentSessionLearningSummary') }}</p>
      </div>
      <div class="toolbar">
        <el-button data-testid="start-demo" :loading="demoBusy" @click="startDemo(false)">{{ t('views.dashboard.runDemo') }}</el-button>
        <el-button :icon="Refresh" :loading="backend.loading" @click="backend.refreshAll()">{{ t('views.dashboard.sync') }}</el-button>
        <el-button type="primary" :icon="ChatLineRound" @click="router.push('/tutor')">{{ t('views.dashboard.continueLearning') }}</el-button>
      </div>
    </div>

    <article v-if="backend.demoSnapshot" class="panel demo-showcase" data-testid="demo-showcase">
      <div class="demo-heading">
        <div><span class="eyebrow">COMPETITION DEMO</span><h2>{{ backend.demoSnapshot.dataset.title }}</h2><p>{{ backend.demoSnapshot.dataset.license }} · {{ backend.demoSnapshot.dataset.original ? t('views.dashboard.originalProjectData') : t('views.dashboard.externalData') }}</p></div>
        <span class="status-pill" :class="backend.demoSnapshot.mode === 'offline' ? 'warn' : 'good'">{{ backend.demoSnapshot.mode === 'offline' ? t('views.dashboard.offline') : t('views.dashboard.modelOnlineAvailable') }}</span>
      </div>
      <p v-if="backend.demoSnapshot.degradation_message" class="demo-degradation">{{ backend.demoSnapshot.degradation_message }}</p>
      <div class="demo-grid">
        <div class="demo-agents"><h3>{{ t('views.dashboard.multiAgent') }}</h3><div v-for="step in backend.demoSnapshot.agent_steps" :key="step.agent" class="demo-step"><span>✓</span><div><strong>{{ step.agent }}</strong><p>{{ step.detail }}</p></div></div></div>
        <div class="demo-mastery"><h3>{{ t('views.dashboard.masteryTitle') }}</h3><div v-for="item in masteryComparisons" :key="item.name"><strong>{{ item.name }}</strong><span>{{ displayPercent(item.before) }} → {{ displayPercent(item.after) }}</span><div class="mastery-track"><i :style="{ width: `${item.before * 100}%` }"></i><b :style="{ width: `${item.after * 100}%` }"></b></div></div></div>
      </div>
      <footer><el-button @click="startDemo(true)">{{ t('views.dashboard.resetDemo') }}</el-button><el-button @click="router.push('/agents')">{{ t('views.dashboard.statusAgent') }}</el-button><el-button type="primary" @click="router.push('/tutor')">{{ t('views.dashboard.tutorOpen') }}</el-button></footer>
    </article>

    <div class="metric-grid">
      <div class="metric"><span>{{ t('views.dashboard.sessionPhase') }}</span><strong>{{ stateLabel }}</strong></div>
      <div class="metric"><span>{{ t('views.dashboard.knowledgePoint') }}</span><strong>{{ backend.progress?.knowledge_points.length || 0 }}</strong></div>
      <div class="metric"><span>{{ t('views.dashboard.answer') }}</span><strong>{{ accuracyLabel }}</strong></div>
      <div class="metric"><span>{{ t('views.dashboard.resourceGenerate') }}</span><strong>{{ backend.resources.length }}</strong></div>
    </div>

    <div v-if="backend.nextAction" class="next-action">
      <div>
        <span class="eyebrow">{{ t('views.dashboard.recommendedNextStep') }}</span>
        <h2>{{ actionLabel(backend.nextAction.action) }}</h2>
        <p>{{ backend.nextAction.reason }}</p>
      </div>
      <div class="action-meta">
        <span>{{ backend.nextAction.knowledge_point || t('views.dashboard.diagnosisLabel') }}</span>
        <el-tag effect="plain">{{ backend.nextAction.recommended_difficulty }}</el-tag>
        <el-button type="primary" @click="startSuggested">{{ t('views.dashboard.start') }}</el-button>
      </div>
    </div>

    <div class="grid-2 content-grid">
      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.dashboard.knowledgePointMastery') }}</h2><span class="muted">{{ t('views.dashboard.sortWeak') }}</span></div>
        <div class="panel-body">
          <template v-if="knowledgePoints.length">
            <div v-for="point in knowledgePoints" :key="point.id" class="knowledge-row">
              <div class="knowledge-title">
                <strong>{{ point.name }}</strong>
                <span>{{ masteryLabel(point.mastery_label) }} · {{ point.correct_attempts }}/{{ point.attempts }}</span>
              </div>
              <el-progress :percentage="Math.round(point.mastery_score * 100)" :stroke-width="8" :show-text="false" />
            </div>
          </template>
          <div v-else class="empty-block">
            <div><p>{{ t('views.dashboard.masteryAvailableAfterDiagnosis') }}</p><el-button text type="primary" @click="router.push('/tutor')">{{ t('views.dashboard.diagnosisStart') }}</el-button></div>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.dashboard.resourceRecent') }}</h2><span class="muted">{{ t('views.dashboard.qualityResult') }}</span></div>
        <div class="panel-body resource-list">
          <template v-if="recentResources.length">
            <div v-for="resource in recentResources" :key="resource.id" class="list-row resource-row">
              <div>
                <strong>{{ resource.topic }}</strong>
                <p>{{ t('views.dashboard.recentResourceSummary', { profileVersion: resource.profile_version, questionCount: resource.questions.length }) }}</p>
              </div>
              <span class="quality" :class="resource.quality_score >= 80 ? 'good' : 'warn'">{{ t('views.dashboard.qualityScore', { score: resource.quality_score }) }}</span>
            </div>
          </template>
          <div v-else class="empty-block"><p>{{ t('views.dashboard.noGeneratedResources') }}</p></div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatLineRound, Refresh } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'
import { actionLabel, masteryLabel } from '@/utils/protocol'
import { formatPercent } from '@/i18n/formatters'

const { t } = useI18n()

const backend = useBackendStore()
const router = useRouter()
const route = useRoute()
const demoBusy = ref(false)
const stateLabel = computed(() => backend.session?.state || (backend.live ? t('views.dashboard.waitingStart') : t('views.dashboard.serviceOffline')))
const displayPercent = (value: number) => formatPercent(value, { maximumFractionDigits: 0 })
const accuracyLabel = computed(() => backend.progress?.total_attempts ? displayPercent(backend.progress.accuracy) : '--')
const knowledgePoints = computed(() => backend.progress?.knowledge_points || [])
const recentResources = computed(() => [...backend.resources].slice(-4).reverse())
const masteryComparisons = computed(() => (backend.demoSnapshot?.mastery_before || []).map(before => ({
  name: before.name,
  before: before.score,
  after: backend.demoSnapshot?.mastery_after.find(item => item.name === before.name)?.score || before.score,
})))

function startSuggested() {
  router.push({ path: '/tutor', query: { prompt: backend.nextAction?.suggested_request || '', at: Date.now().toString(36) } })
}
async function startDemo(reset: boolean) {
  demoBusy.value = true
  try { await backend.startDemo(reset) }
  finally { demoBusy.value = false }
}
onMounted(async () => {
  if (route.query.demo === 'offline') await startDemo(false)
})
</script>

<style scoped lang="scss">
.next-action {
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  margin-bottom: 16px; padding: 18px; color: #fff; background: #2e4a4b; border-left: 5px solid #51b7a9;
  h2 { margin: 3px 0 5px; font-size: 20px; letter-spacing: 0; }
  p { margin: 0; color: #d4e0df; font-size: 13px; }
}
.eyebrow { color: #9ed7cf; font-size: 11px; }
.action-meta { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 9px; }
.content-grid { align-items: start; }
.demo-showcase{margin-bottom:16px;padding:18px}.demo-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.demo-heading h2{margin:3px 0 4px;font-size:20px}.demo-heading p,.demo-step p{margin:0;color:var(--muted);font-size:11px}.demo-degradation{padding:9px 11px;color:#755f3d;background:#fff6e7;border-radius:8px;font-size:11px}.demo-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:20px;margin-top:14px}.demo-grid h3{margin:0 0 10px;font-size:13px}.demo-step{display:flex;gap:9px;padding:8px 0;border-bottom:1px solid var(--line)}.demo-step>span{color:var(--accent)}.demo-mastery>div{margin-bottom:14px}.demo-mastery strong,.demo-mastery span{display:block}.demo-mastery span{margin:3px 0 6px;color:var(--muted);font-size:12px}.mastery-track{position:relative;height:8px;background:#eee8df;border-radius:99px;overflow:hidden}.mastery-track i,.mastery-track b{position:absolute;inset:0 auto 0 0;border-radius:99px}.mastery-track i{background:#d8b77e}.mastery-track b{height:4px;top:2px;background:#4f9990}.demo-showcase footer{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.knowledge-row { padding: 11px 0; border-bottom: 1px solid var(--line); }
.knowledge-row:last-child { border-bottom: 0; }
.knowledge-title { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 7px; }
.knowledge-title span, .resource-row p { color: var(--muted); font-size: 12px; }
.resource-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.resource-row p { margin: 3px 0 0; }
.quality { flex: 0 0 auto; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
.quality.good { color: var(--accent); background: var(--accent-soft); }
.quality.warn { color: var(--warning); background: #fff3df; }
@media (max-width: 760px) { .next-action { align-items: flex-start; flex-direction: column; } .action-meta { justify-content: flex-start; }.demo-grid{grid-template-columns:1fr}.demo-showcase footer{justify-content:flex-start;flex-wrap:wrap} }
</style>
