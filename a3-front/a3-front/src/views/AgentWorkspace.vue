<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>智能体协作</h1><p>画像 Agent 与资源 Agent 的真实工作状态</p></div>
      <el-button type="primary" :icon="Plus" @click="generate">发起学习任务</el-button>
    </div>

    <div class="agent-strip">
      <article v-for="agent in agents" :key="agent.name" class="agent-unit panel">
        <div class="agent-icon"><el-icon><component :is="agent.icon" /></el-icon></div>
        <div class="agent-copy"><span>{{ agent.role }}</span><h2>{{ agent.name }}</h2><p>{{ agent.description }}</p></div>
        <span class="status-pill" :class="agent.tone">{{ agent.status }}</span>
      </article>
    </div>

    <div class="grid-2 main-grid">
      <article class="panel">
        <div class="panel-header"><h2>协作流程</h2><span class="muted">会话 {{ backend.sessionId }}</span></div>
        <div class="panel-body workflow">
          <div v-for="(step, index) in workflow" :key="step.title" class="workflow-step" :class="step.state">
            <div class="step-index">{{ index + 1 }}</div>
            <div><strong>{{ step.title }}</strong><p>{{ step.description }}</p></div>
            <el-icon v-if="step.state === 'done'" color="#0b756d"><CircleCheck /></el-icon>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>最近一次资源交付</h2><span v-if="latest" class="status-pill good">质量 {{ latest.quality_score }}</span></div>
        <div v-if="latest" class="panel-body latest-resource">
          <span>主题</span><h2>{{ latest.topic }}</h2>
          <p>{{ latest.questions.length }} 道结构化练习 · {{ latest.sources.length }} 个参考来源</p>
          <div class="quality-issues">
            <el-tag v-for="issue in latest.quality_issues" :key="issue" type="warning" effect="plain">{{ issue }}</el-tag>
            <el-tag v-if="!latest.quality_issues.length" type="success" effect="plain">质量检查通过</el-tag>
          </div>
          <el-button @click="router.push('/assessment')">进入练习</el-button>
        </div>
        <div v-else class="empty-block"><p>资源 Agent 尚未生成内容</p></div>
      </article>
    </div>

    <article class="panel event-panel">
      <div class="panel-header"><h2>会话事件</h2><span class="muted">消息与持久化资源</span></div>
      <div class="panel-body event-list">
        <div v-for="message in recentMessages" :key="message.seq" class="event-row">
          <span class="event-seq">#{{ message.seq }}</span>
          <span class="status-pill" :class="message.role === 'assistant' ? 'good' : ''">{{ message.role === 'assistant' ? 'Agent' : '学习者' }}</span>
          <p>{{ compact(message.content) }}</p>
        </div>
        <div v-if="!recentMessages.length" class="empty-block"><p>暂无协作事件</p></div>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, Document, Plus, User } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'

const backend = useBackendStore()
const router = useRouter()
const latest = computed(() => backend.resources.length ? backend.resources[backend.resources.length - 1] : null)
const recentMessages = computed(() => (backend.session?.messages || []).slice(-8).reverse())
const profileDone = computed(() => Boolean(backend.session?.profile_text))
const resourceDone = computed(() => backend.resources.length > 0)

const agents = computed(() => [
  {
    name: '画像 Agent', role: '诊断与画像', icon: User,
    description: '通过多轮对话识别目标、水平、风格和薄弱知识点。',
    status: profileDone.value ? '已完成画像' : backend.session?.state === 'DIAGNOSING' ? '诊断中' : '等待任务',
    tone: profileDone.value ? 'good' : backend.session?.state === 'DIAGNOSING' ? 'warn' : '',
  },
  {
    name: '资源 Agent', role: '内容与练习', icon: Document,
    description: '结合画像、掌握度和来源生成笔记、分层练习与解析。',
    status: resourceDone.value ? `已交付 ${backend.resources.length} 项` : profileDone.value ? '可以生成' : '等待画像',
    tone: resourceDone.value ? 'good' : profileDone.value ? 'warn' : '',
  },
])

const workflow = computed(() => [
  { title: '诊断对话', description: '收集学习目标与薄弱点', state: backend.session ? 'done' : 'current' },
  { title: '学习画像', description: '生成 learner-profile/v1', state: profileDone.value ? 'done' : backend.session ? 'current' : 'pending' },
  { title: '个性化资源', description: '生成笔记、分层练习和来源', state: resourceDone.value ? 'done' : profileDone.value ? 'current' : 'pending' },
  { title: '答题反馈', description: '更新掌握度与复习计划', state: (backend.progress?.total_attempts || 0) > 0 ? 'done' : resourceDone.value ? 'current' : 'pending' },
])

function compact(content: string) {
  return content.replace(/\s+/g, ' ').slice(0, 180)
}
function generate() {
  router.push({ path: '/tutor', query: { prompt: backend.nextAction?.suggested_request || '' } })
}
</script>

<style scoped lang="scss">
.agent-strip { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.agent-unit { display: grid; grid-template-columns: 50px minmax(0, 1fr) auto; align-items: center; gap: 14px; padding: 18px; }
.agent-icon { width: 50px; height: 50px; display: grid; place-items: center; color: #fff; background: #32575b; border-radius: 6px; font-size: 22px; }
.agent-copy span { color: var(--muted); font-size: 11px; }
.agent-copy h2 { margin: 2px 0 4px; font-size: 17px; }
.agent-copy p, .workflow-step p, .latest-resource p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.55; }
.main-grid { align-items: stretch; }
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
@media (max-width: 760px) { .agent-strip { grid-template-columns: 1fr; } .agent-unit { grid-template-columns: 44px minmax(0, 1fr); } .agent-unit > .status-pill { grid-column: 2; justify-self: start; } }
</style>
