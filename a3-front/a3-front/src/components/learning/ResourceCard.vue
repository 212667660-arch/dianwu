<template>
  <div class="resource-card" :class="{ collapsed: !expanded, failed: artifact.status === 'FAILED' }">
    <div class="card-header" @click="toggle">
      <span class="card-type">{{ typeLabel }}</span>
      <span class="card-title">{{ artifact.title }}</span>
      <span class="card-status">
        {{ artifact.status === 'SUCCEEDED' ? '✅' : artifact.status === 'FAILED' ? '❌' : '⏹' }}
      </span>
      <span class="card-score">质量: {{ artifact.quality_score }}</span>
      <button class="card-toggle">{{ expanded ? '收起' : '展开' }}</button>
    </div>
    <div v-if="expanded" class="card-body">
      <div v-if="artifact.status === 'FAILED'" class="card-error">
        <p>错误码: {{ artifact.error_code }}</p>
        <p v-if="artifact.quality_issues.length">问题: {{ artifact.quality_issues.join(', ') }}</p>
        <button v-if="artifact.retryable" class="retry-btn" @click.stop="$emit('retry', artifact.artifact_id)">
          重试
        </button>
      </div>
      <div v-else class="card-content">
        <div class="markdown-body" v-html="renderedMarkdown" />
      </div>
      <div class="card-actions">
        <button @click.stop="copyContent" class="copy-btn">复制 Markdown</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

const props = defineProps<{
  artifact: {
    artifact_id: string;
    type: string;
    title: string;
    status: string;
    body: string;
    quality_score: number;
    quality_issues: string[];
    error_code?: string;
    retryable?: boolean;
    type_specific_data?: Record<string, any>;
  };
}>();

defineEmits<{ retry: [artifactId: string] }>();

const expanded = ref(false);

const typeLabels: Record<string, string> = {
  course_explanation: "📖 课程讲解",
  mind_map: "🧠 思维导图",
  question_bank: "📝 题库",
  extended_reading: "📚 延伸阅读",
  adaptive_practice: "🔬 自适应练习",
};

const typeLabel = computed(() => typeLabels[props.artifact.type] || props.artifact.type);

const renderedMarkdown = computed(() => {
  return props.artifact.body
    .replace(/## (.+)/g, "<h3>$1</h3>")
    .replace(/\n/g, "<br>");
});

function toggle() {
  expanded.value = !expanded.value;
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.artifact.body);
  } catch {
    // fallback silently
  }
}
</script>

<style scoped>
.resource-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}
.resource-card.failed {
  border-color: #fca5a5;
  background: #fef2f2;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  flex-wrap: wrap;
}
.card-type { font-size: 13px; color: #6b7280; }
.card-title { font-weight: 600; flex: 1; }
.card-status { font-size: 16px; }
.card-score { font-size: 12px; color: #9ca3af; }
.card-toggle {
  font-size: 12px; padding: 2px 8px;
  border: 1px solid #d1d5db; border-radius: 4px;
  background: #fff; cursor: pointer;
}
.card-body { padding: 0 12px 12px; }
.card-error { color: #dc2626; font-size: 13px; }
.card-actions { display: flex; gap: 8px; margin-top: 8px; }
.copy-btn, .retry-btn {
  font-size: 12px; padding: 4px 10px;
  border: 1px solid #d1d5db; border-radius: 4px;
  background: #f9fafb; cursor: pointer;
}
.retry-btn { background: #fef3c7; border-color: #fbbf24; }
.collapsed .card-body { display: none; }
@media (max-width: 640px) {
  .card-header { flex-direction: column; align-items: flex-start; }
  .card-actions { flex-direction: column; }
}
</style>
