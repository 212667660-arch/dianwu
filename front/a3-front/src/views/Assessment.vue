<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>{{ t('views.assessment.title') }}</h1><p>{{ t('views.assessment.answerSubmissionEffects') }}</p></div>
      <div class="toolbar"><el-button :icon="Refresh" @click="backend.refreshSession()">{{ t('views.assessment.sync') }}</el-button><el-button type="primary" @click="router.push('/tutor')">{{ t('views.assessment.practiceGenerate') }}</el-button></div>
    </div>

    <div class="assessment-layout">
      <article class="panel question-panel">
        <div class="panel-header"><h2>{{ t('views.assessment.practiceCurrent') }}</h2><span class="muted">{{ questionRows.length }} {{ t('views.assessment.questionUnit') }}</span></div>
        <div class="panel-body">
          <div v-for="row in questionRows" :key="row.question.id" class="question-row">
            <div class="question-heading">
              <div><span>{{ t('views.assessment.questionTitle') }} {{ row.question.ordinal }}</span><h3>{{ row.question.prompt }}</h3></div>
              <div class="toolbar"><el-tag effect="plain">{{ row.question.difficulty }}</el-tag><span class="quality-label">{{ t('views.assessment.resourceQuality') }} {{ row.quality }}</span></div>
            </div>
            <div class="answer-row">
              <el-input v-model="answers[row.question.id]" :data-testid="`assessment-answer-${row.question.id}`" :placeholder="t('views.assessment.answer')" @keyup.enter="submit(row.question.id)" />
              <el-button :data-testid="`assessment-submit-${row.question.id}`" type="primary" :loading="submitting === row.question.id" @click="submit(row.question.id)">{{ t('views.assessment.submitTitle') }}</el-button>
            </div>
            <div v-if="results[row.question.id]" class="result-box" :class="results[row.question.id].correct ? 'correct' : 'incorrect'">
              <div><strong>{{ results[row.question.id].correct ? t('views.assessment.correct') : t('views.assessment.needsReinforcement') }}</strong><span>{{ t('views.assessment.masteryLabel') }} {{ formatPercent(results[row.question.id].mastery_score, { maximumFractionDigits: 0 }) }}</span></div>
              <p>{{ results[row.question.id].feedback }}</p>
              <dl><dt>{{ t('views.assessment.expected') }}</dt><dd>{{ results[row.question.id].expected_answer }}</dd><dt>{{ t('views.assessment.explanation') }}</dt><dd>{{ results[row.question.id].explanation }}</dd></dl>
            </div>
          </div>
          <div v-if="!questionRows.length" class="empty-block"><div><p>{{ t('views.assessment.noQuestionsInCurrentSession') }}</p><el-button text type="primary" @click="router.push('/tutor')">{{ t('views.assessment.resourceGenerate') }}</el-button></div></div>
        </div>
      </article>

      <aside class="side-stack">
        <article class="panel">
          <div class="panel-header"><h2>{{ t('views.assessment.review') }}</h2><span class="muted">{{ backend.reviews.length }}</span></div>
          <div class="panel-body compact-list">
            <div v-for="review in backend.reviews" :key="review.id" class="list-row"><strong>{{ review.knowledge_point }}</strong><p>{{ review.reason === 'ANSWER_INCORRECT' ? t('views.assessment.reviewTitle') : formatReviewDate(review.due_at) }}</p></div>
            <p v-if="!backend.reviews.length" class="muted">{{ t('views.assessment.noReviewTasks') }}</p>
          </div>
        </article>
        <article class="panel">
          <div class="panel-header"><h2>{{ t('views.assessment.mistakeRecent') }}</h2><span class="muted">{{ backend.mistakes.length }}</span></div>
          <div class="panel-body compact-list">
            <div v-for="mistake in backend.mistakes.slice(0, 6)" :key="mistake.attempt_id" class="list-row"><strong>{{ mistake.prompt }}</strong><p>{{ t('views.assessment.answerTitle') }}{{ mistake.submitted_answer }}</p><span>{{ mistake.knowledge_point }}</span></div>
            <p v-if="!backend.mistakes.length" class="muted">{{ t('views.assessment.noMistakeRecords') }}</p>
          </div>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { errorMessage, type AttemptResponse } from '@/api'
import { useBackendStore } from '@/stores/backend'
import { formatDateTime, formatPercent } from '@/i18n/formatters'

const { t } = useI18n()

const backend = useBackendStore()
const router = useRouter()
const answers = reactive<Record<number, string>>({})
const results = reactive<Record<number, AttemptResponse>>({})
const submitting = ref<number | null>(null)
const questionRows = computed(() => backend.resources.flatMap(resource => resource.questions.map(question => ({ question, quality: resource.quality_score, topic: resource.topic }))).reverse())

async function submit(questionId: number) {
  const answer = (answers[questionId] || '').trim()
  if (!answer) return ElMessage.warning(t('views.assessment.answerDescription'))
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
function formatReviewDate(value: string) { return formatDateTime(value, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
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
