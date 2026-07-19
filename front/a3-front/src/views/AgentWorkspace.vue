<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>{{ t('views.agents.title') }}</h1><p>{{ t('views.agents.agentStatusOverview') }}</p></div>
      <el-button type="primary" :icon="Plus" @click="generate">{{ t('views.agents.startLearningTask') }}</el-button>
    </div>

    <div class="agent-strip">
      <article v-for="agent in agents" :key="agent.name" class="agent-unit panel">
        <div class="agent-icon"><el-icon><component :is="agent.icon" /></el-icon></div>
        <div class="agent-copy"><span>{{ agent.role }}</span><h2>{{ agent.name }}</h2><p>{{ agent.description }}</p></div>
        <span class="status-pill" :class="agent.tone">{{ agent.status }}</span>
      </article>
    </div>

    <article v-if="backend.demoSnapshot" class="panel demo-agent-panel" data-testid="demo-agent-panel">
      <div class="panel-header"><h2>{{ t('views.agents.statusAgent') }}</h2><span class="status-pill" :class="backend.demoSnapshot.mode === 'offline' ? 'warn' : 'good'">{{ backend.demoSnapshot.mode === 'offline' ? t('views.agents.offline') : t('views.agents.online') }}</span></div>
      <div class="panel-body demo-agent-list"><div v-for="step in backend.demoSnapshot.agent_steps" :key="step.agent"><span>COMPLETED</span><strong>{{ step.agent }}</strong><p>{{ step.detail }}</p></div></div>
      <p v-if="backend.demoSnapshot.degradation_message" class="demo-agent-degradation">{{ backend.demoSnapshot.degradation_message }}</p>
    </article>

    <div class="grid-2 main-grid">
      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.agents.workflowTitle') }}</h2><span class="muted">{{ t('views.agents.sessionLabel') }} {{ backend.sessionId }}</span></div>
        <div class="panel-body workflow">
          <div v-for="(step, index) in workflow" :key="step.title" class="workflow-step" :class="step.state">
            <div class="step-index">{{ index + 1 }}</div>
            <div><strong>{{ step.title }}</strong><p>{{ step.description }}</p></div>
            <el-icon v-if="step.state === 'done'" color="#0b756d"><CircleCheck /></el-icon>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.agents.latestResourceDelivery') }}</h2><span v-if="latest" class="status-pill good">{{ t('views.agents.quality') }} {{ latest.quality_score }}</span></div>
        <div v-if="latest" class="panel-body latest-resource">
          <span>{{ t('views.agents.topicLabel') }}</span><h2>{{ latest.topic }}</h2>
          <p>{{ latest.questions.length }} {{ t('views.agents.structuredPracticeCountSuffix') }} {{ latest.sources.length }} {{ t('views.agents.reference') }}</p>
          <div class="quality-issues">
            <el-tag v-for="issue in latest.quality_issues" :key="issue" type="warning" effect="plain">{{ issue }}</el-tag>
            <el-tag v-if="!latest.quality_issues.length" type="success" effect="plain">{{ t('views.agents.qualityCheck') }}</el-tag>
          </div>
          <el-button @click="router.push('/assessment')">{{ t('views.agents.practice') }}</el-button>
        </div>
        <div v-else class="empty-block"><p>{{ t('views.agents.resourceNotGenerated') }}</p></div>
      </article>
    </div>

    <article class="panel event-panel">
      <div class="panel-header"><h2>{{ t('views.agents.session') }}</h2><span class="muted">{{ t('views.agents.resourceMessage') }}</span></div>
      <div class="panel-body event-list">
        <div v-for="message in recentMessages" :key="message.seq" class="event-row">
          <span class="event-seq">#{{ message.seq }}</span>
          <span class="status-pill" :class="message.role === 'assistant' ? 'good' : ''">{{ message.role === 'assistant' ? 'Agent' : t('views.agents.learner') }}</span>
          <p>{{ compact(message.content) }}</p>
        </div>
        <div v-if="!recentMessages.length" class="empty-block"><p>{{ t('views.agents.noCollaborationEvents') }}</p></div>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, Document, Plus, User } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'

const { t } = useI18n()

const backend = useBackendStore()
const router = useRouter()
const latest = computed(() => backend.resources.length ? backend.resources[backend.resources.length - 1] : null)
const recentMessages = computed(() => (backend.session?.messages || []).slice(-8).reverse())
const profileDone = computed(() => Boolean(backend.session?.profile_text))
const resourceDone = computed(() => backend.resources.length > 0)

const agents = computed(() => [
  {
    name: t('views.agents.diagnosis'), role: t('views.agents.profileDiagnosis'), icon: User,
    description: t('views.agents.profileAgentDescription'),
    status: profileDone.value ? t('views.agents.profileCompleted') : backend.session?.state === 'DIAGNOSING' ? t('statuses.sessionState.DIAGNOSING') : t('views.agents.waitingTask'),
    tone: profileDone.value ? 'good' : backend.session?.state === 'DIAGNOSING' ? 'warn' : '',
  },
  {
    name: t('views.agents.resourceAgent'), role: t('views.agents.practiceContent'), icon: Document,
    description: t('views.agents.resourceAgentDescription'),
    status: resourceDone.value ? t('views.agents.deliveredItemCount', { length: backend.resources.length }) : profileDone.value ? t('views.agents.generate') : t('views.agents.profileWaiting'),
    tone: resourceDone.value ? 'good' : profileDone.value ? 'warn' : '',
  },
])

const workflow = computed(() => [
  { title: t('views.agents.diagnosisConversation'), description: t('views.agents.collectGoalsAndWeaknesses'), state: backend.session ? 'done' : 'current' },
  { title: t('views.agents.profileTitle'), description: t('views.agents.generateProfileProtocol'), state: profileDone.value ? 'done' : backend.session ? 'current' : 'pending' },
  { title: t('views.agents.resource'), description: t('views.agents.generateNotesPracticeAndSources'), state: resourceDone.value ? 'done' : profileDone.value ? 'current' : 'pending' },
  { title: t('views.agents.answer'), description: t('views.agents.updateMasteryAndReviewPlan'), state: (backend.progress?.total_attempts || 0) > 0 ? 'done' : resourceDone.value ? 'current' : 'pending' },
])

function compact(content: string) {
  return content.replace(/\s+/g, ' ').slice(0, 180)
}
function generate() {
  router.push({ path: '/tutor', query: { prompt: backend.nextAction?.suggested_request || '' } })
}
onMounted(() => { if (!backend.demoSnapshot) void backend.loadDemoStatus().catch(() => {}) })
</script>

<style scoped lang="scss">
.agent-strip { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.agent-unit { display: grid; grid-template-columns: 50px minmax(0, 1fr) auto; align-items: center; gap: 14px; padding: 18px; }
.agent-icon { width: 50px; height: 50px; display: grid; place-items: center; color: #fff; background: #32575b; border-radius: 6px; font-size: 22px; }
.agent-copy span { color: var(--muted); font-size: 11px; }
.agent-copy h2 { margin: 2px 0 4px; font-size: 17px; }
.agent-copy p, .workflow-step p, .latest-resource p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.55; }
.main-grid { align-items: stretch; }
.demo-agent-panel{margin-bottom:16px}.demo-agent-list{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.demo-agent-list>div{padding:10px;background:#f6f2eb;border-radius:8px}.demo-agent-list span{display:block;color:var(--accent);font-size:9px}.demo-agent-list strong{display:block;margin:4px 0;font-size:12px}.demo-agent-list p,.demo-agent-degradation{margin:0;color:var(--muted);font-size:10px;line-height:1.5}.demo-agent-degradation{padding:0 16px 14px;color:#755f3d}
.workflow-step { display: grid; grid-template-columns: 28px minmax(0, 1fr) 20px; align-items: center; gap: 11px; padding: 12px 0; opacity: .48; border-bottom: 1px solid var(--line); }
.workflow-step:last-child { border: 0; }
.workflow-step.done, .workflow-step.current { opacity: 1; }
.step-index { width: 26px; height: 26px; display: grid; place-items: center; border: 1px solid var(--line); border-radius: 50%; font-size: 11px; }
.workflow-step.current .step-index { color: #fff; border-color: var(--warning); background: var(--warning); }
.workflow-step.done .step-index { color: #fff; border-color: var(--accent); background: var(--accent); }
.latest-resource > span { color: var(--muted); font-size: 11px; }
.latest-resource h2 { margin: 3px 0 5px; font-size: 19px; }
.quality-issues { display: flex; flex-wrap: wrap; gap: 6px; margin: 16px 0; }
.event-panel { margin-top: 16px; }
.event-row { display: grid; grid-template-columns: 40px 62px minmax(0, 1fr); align-items: start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.event-row:last-child { border: 0; }
.event-row p { margin: 0; line-height: 1.55; }
.event-seq { color: var(--muted); font-size: 11px; }
@media (max-width: 760px) { .agent-strip { grid-template-columns: 1fr; } .agent-unit { grid-template-columns: 44px minmax(0, 1fr); } .agent-unit > .status-pill { grid-column: 2; justify-self: start; }.demo-agent-list{grid-template-columns:1fr} }
</style>
