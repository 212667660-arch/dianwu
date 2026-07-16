<template>
  <div class="safe-mermaid">
    <div v-if="canRender" class="mermaid-container">
      <div ref="mermaidEl" class="mermaid-render"></div>
    </div>
    <div v-else class="outline-fallback">
      <div class="fallback-notice">⚠ Mermaid 渲染不可用，显示文本大纲</div>
      <pre class="outline-text">{{ outlineText }}</pre>
    </div>
    <div class="outline-section">
      <details>
        <summary>📋 文本大纲</summary>
        <pre class="outline-text">{{ outlineText }}</pre>
      </details>
    </div>
  </div>
</template>

<script lang="ts">
let safeMermaidSequence = 0;
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  content: string;
  outline?: string;
}>();

const componentId = `safe-mermaid-${++safeMermaidSequence}`;
const mermaidEl = ref<HTMLElement | null>(null);
const renderFailed = ref(false);
let renderVersion = 0;

const MAX_SOURCE_CHARACTERS = 20_000;
const MAX_SOURCE_LINES = 250;
const SAFE_PREFIX = /^(flowchart|graph)(?:\s|$)/;
const UNSAFE_PATTERNS = [
  /%%\s*\{/i,
  /\bclick\b/i,
  /\bhref\b/i,
  /javascript:/i,
  /htmlLabels/i,
  /securityLevel/i,
  /<\/?(?:script|iframe|object|embed|foreignObject)/i,
  /on(?:error|load|click)\s*=/i,
];

const mermaidCode = computed(() => {
  const lines = props.content.replace(/\r\n?/g, "\n").split("\n");
  const startIndex = lines.findIndex(
    line => line.trim().startsWith("flowchart") || line.trim().startsWith("graph"),
  );
  if (startIndex < 0) return "";
  const endIndex = lines.findIndex((line, index) => index > startIndex && /^##\s/.test(line));
  return lines.slice(startIndex, endIndex > startIndex ? endIndex : undefined).join("\n").trim();
});

const safeToRender = computed(() => {
  const normalized = props.content.replace(/\r\n?/g, "\n");
  if (!mermaidCode.value || normalized.length > MAX_SOURCE_CHARACTERS) return false;
  if (normalized.split("\n").length > MAX_SOURCE_LINES) return false;
  if (!SAFE_PREFIX.test(mermaidCode.value)) return false;
  return !UNSAFE_PATTERNS.some(pattern => pattern.test(normalized));
});

const canRender = computed(() => safeToRender.value && !renderFailed.value);

const outlineText = computed(() => {
  if (props.outline) return props.outline;
  const match = props.content.match(/##\s*大纲\n([\s\S]*?)(?=\n##|$)/);
  return match ? match[1].trim() : "大纲不可用";
});

async function renderDiagram() {
  const version = ++renderVersion;
  renderFailed.value = false;
  if (!safeToRender.value) return;
  await nextTick();
  if (!mermaidEl.value || version !== renderVersion) return;
  mermaidEl.value.textContent = "";
  try {
    const mermaid = await import("mermaid");
    mermaid.default.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default",
    });
    const { svg } = await mermaid.default.render(
      `${componentId}-${version}`,
      mermaidCode.value,
    );
    if (version !== renderVersion || !mermaidEl.value) return;
    mermaidEl.value.innerHTML = svg;
  } catch {
    if (version === renderVersion) {
      if (mermaidEl.value) mermaidEl.value.textContent = "";
      renderFailed.value = true;
    }
  }
}

watch([mermaidCode, safeToRender], renderDiagram, { immediate: true, flush: "post" });
onBeforeUnmount(() => { renderVersion += 1; });
</script>

<style scoped>
.safe-mermaid { margin: 8px 0; }
.mermaid-container {
  overflow-x: auto; padding: 8px;
  background: #f9fafb; border-radius: 6px;
  border: 1px solid #e5e7eb;
}
.outline-fallback {
  padding: 8px; background: #fef3c7;
  border-radius: 6px; border: 1px solid #fbbf24;
}
.fallback-notice { font-size: 13px; color: #92400e; margin-bottom: 4px; }
.outline-text {
  font-size: 13px; font-family: monospace;
  white-space: pre-wrap; margin: 4px 0;
}
.outline-section { margin-top: 8px; }
.outline-section summary { cursor: pointer; font-size: 13px; color: #6b7280; }
</style>
