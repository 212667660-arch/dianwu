<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>练习评估</h1><p>提交答案后更新掌握度、错题与复习计划</p></div>
      <div class="toolbar"><el-button :icon="Refresh" @click="backend.refreshSession()">同步题目</el-button><el-button type="primary" @click="router.push('/tutor')">生成新练习</el-button></div>
    </div>

    <div class="assessment-layout">
      <article class="panel question-panel">
        <div class="panel-header"><h2>当前练习</h2><span class="muted">{{ questionRows.length }} 题</span></div>
        <div class="panel-body">
          <div v-for="row in questionRows" :key="row.question.id" class="question-row">
            <div class="question-heading">
              <div><span>题目 {{ row.question.ordinal }}</span><h3>{{ row.question.prompt }}</h3></div>
              <div class="toolbar"><el-tag effect="plain">{{ row.question.difficulty }}</el-tag><span class="quality-label">资源质量 {{ row.quality }}</span></div>
            </div>
            <div class="answer-row">
              <el-input v-model="answers[row.question.id]" :data-testid="`assessment-answer-${row.question.id}`" placeholder="输入你的答案" @keyup.enter="submit(row.question.id)" />
              <el-button :data-testid="`assessment-submit-${row.question.id}`" type="primary" :loading="submitting === row.question.id" @click="submit(row.question.id)">提交</el-button>
            </div>
            <div v-if="results[row.question.id]" class="result-box" :class="results[row.question.id].correct ? 'correct' : 'incorrect'">
              <div><strong>{{ results[row.question.id].correct ? '回答正确' : '需要巩固' }}</strong><span>掌握度 {{ Math.round(results[row.question.id].mastery_score * 100) }}%</span></div>
              <p>{{ results[row.question.id].feedback }}</p>
              <dl><dt>参考答案</dt><dd>{{ results[row.question.id].expected_answer }}</dd><dt>解析</dt><dd>{{ results[row.question.id].explanation }}</dd></dl>
            </div>
          </div>
          <div v-if="!questionRows.length" class="empty-block"><div><p>当前会话还没有可作答的练习题</p><el-button text type="primary" @click="router.push('/tutor')">生成学习资源</el-button></div></div>
        </div>
      </article>

      <aside class="side-stack">
        <article class="panel">
          <div class="panel-header"><h2>待复习</h2><span class="muted">{{ backend.reviews.length }}</span></div>
          <div class="panel-body compact-list">
            <div v-for="review in backend.reviews" :key="review.id" class="list-row"><strong>{{ review.knowledge_point }}</strong><p>{{ review.reason === 'ANSWER_INCORRECT' ? '答错后立即复习' : formatDate(review.due_at) }}</p></div>
            <p v-if="!backend.reviews.length" class="muted">暂无待复习任务</p>
          </div>
        </article>
        <article class="panel">
          <div class="panel-header"><h2>最近错题</h2><span class="muted">{{ backend.mistakes.length }}</span></div>
          <div class="panel-body compact-list">
            <div v-for="mistake in backend.mistakes.slice(0, 6)" :key="mistake.attempt_id" class="list-row"><strong>{{ mistake.prompt }}</strong><p>你的答案：{{ mistake.submitted_answer }}</p><span>{{ mistake.knowledge_point }}</span></div>
            <p v-if="!backend.mistakes.length" class="muted">暂无错题记录</p>
          </div>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { errorMessage, type AttemptResponse } from '@/api'
import { useBackendStore } from '@/stores/backend'

const backend = useBackendStore()
const router = useRouter()
const answers = reactive<Record<number, string>>({})
const results = reactive<Record<number, AttemptResponse>>({})
const submitting = ref<number | null>(null)
const questionRows = computed(() => backend.resources.flatMap(resource => resource.questions.map(question => ({ question, quality: resource.quality_score, topic: resource.topic }))).reverse())

async function submit(questionId: number) {
  const answer = (answers[questionId] || '').trim()
  if (!answer) return ElMessage.warning('请输入答案')
  submitting.value = questionId
  try {
    results[questionId] = await backend.submitAnswer(questionId, answer, 0)
    ElMessage[results[questionId].correct ? 'success' : 'warning'](results[questionId].feedback)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = null
  }
}
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
</script>

<style scoped lang="scss">
.assessment-layout { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 16px; align-items: start; }
.question-row { padding: 18px 0; border-bottom: 1px solid var(--line); }
.question-row:first-child { padding-top: 0; }
.question-row:last-child { border-bottom: 0; }
.question-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; }
.question-heading span { color: var(--muted); font-size: 11px; }
.question-heading h3 { margin: 4px 0 0; font-size: 15px; line-height: 1.6; }
.quality-label { white-space: nowrap; }
.answer-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; margin-top: 13px; }
.answer-row :deep(.el-button) { min-width: 82px; }
.result-box { margin-top: 12px; padding: 13px; border-left: 4px solid; background: var(--surface-soft); }
.result-box.correct { border-color: var(--accent); }
.result-box.incorrect { border-color: var(--danger); }
.result-box > div { display: flex; justify-content: space-between; gap: 12px; }
.result-box > div span, .result-box p { color: var(--muted); font-size: 12px; }
.result-box p { margin: 5px 0 10px; }
.result-box dl { display: grid; grid-template-columns: 66px minmax(0, 1fr); gap: 5px 10px; margin: 0; font-size: 12px; }
.result-box dt { color: var(--muted); }
.result-box dd { margin: 0; }
.side-stack { display: grid; gap: 16px; }
.compact-list .list-row strong, .compact-list .list-row p, .compact-list .list-row span { display: block; }
.compact-list .list-row strong { font-size: 12px; line-height: 1.5; }
.compact-list .list-row p, .compact-list .list-row span { margin: 3px 0 0; color: var(--muted); font-size: 11px; }
@media (max-width: 980px) { .assessment-layout { grid-template-columns: 1fr; } .side-stack { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 620px) { .answer-row { grid-template-columns: 1fr; } .side-stack { grid-template-columns: 1fr; } .question-heading { flex-direction: column; } }
</style>
