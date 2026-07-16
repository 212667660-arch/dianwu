<template>
  <div class="safe-markdown">
    <template v-for="(token, index) in tokens" :key="index">
      <component
        :is="`h${token.level}`"
        v-if="token.kind === 'heading'"
        class="markdown-heading"
      >{{ token.text }}</component>
      <ul v-else-if="token.kind === 'unordered-list'" class="markdown-list">
        <li v-for="(item, itemIndex) in token.items" :key="itemIndex">{{ item }}</li>
      </ul>
      <ol v-else-if="token.kind === 'ordered-list'" class="markdown-list">
        <li v-for="(item, itemIndex) in token.items" :key="itemIndex">{{ item }}</li>
      </ol>
      <pre v-else-if="token.kind === 'code'" class="markdown-code"><code>{{ token.text }}</code></pre>
      <p v-else class="markdown-paragraph">{{ tokenText(token) }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

type MarkdownToken =
  | { kind: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { kind: 'unordered-list' | 'ordered-list'; items: string[] }
  | { kind: 'code' | 'paragraph'; text: string }

function tokenText(token: MarkdownToken): string {
  return 'text' in token ? token.text : ''
}

const MAX_MARKDOWN_CHARACTERS = 50_000

const tokens = computed<MarkdownToken[]>(() => {
  const lines = props.content.slice(0, MAX_MARKDOWN_CHARACTERS).replace(/\r\n?/g, '\n').split('\n')
  const result: MarkdownToken[] = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }
    if (/^\s*```/.test(line)) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !/^\s*```/.test(lines[index])) {
        code.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      result.push({ kind: 'code', text: code.join('\n') })
      continue
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line.trim())
    if (heading) {
      result.push({
        kind: 'heading',
        level: heading[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        text: heading[2].trim(),
      })
      index += 1
      continue
    }
    const unordered = /^\s*[-*+]\s+(.+)$/.exec(line)
    if (unordered) {
      const items: string[] = []
      while (index < lines.length) {
        const match = /^\s*[-*+]\s+(.+)$/.exec(lines[index])
        if (!match) break
        items.push(match[1].trim())
        index += 1
      }
      result.push({ kind: 'unordered-list', items })
      continue
    }
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line)
    if (ordered) {
      const items: string[] = []
      while (index < lines.length) {
        const match = /^\s*\d+[.)]\s+(.+)$/.exec(lines[index])
        if (!match) break
        items.push(match[1].trim())
        index += 1
      }
      result.push({ kind: 'ordered-list', items })
      continue
    }
    const paragraph = [line.trim()]
    index += 1
    while (
      index < lines.length
      && lines[index].trim()
      && !/^\s*```/.test(lines[index])
      && !/^(#{1,6})\s+/.test(lines[index].trim())
      && !/^\s*[-*+]\s+/.test(lines[index])
      && !/^\s*\d+[.)]\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    result.push({ kind: 'paragraph', text: paragraph.join('\n') })
  }
  return result
})
</script>

<style scoped>
.safe-markdown { line-height: 1.65; overflow-wrap: anywhere; }
.markdown-heading { margin: 12px 0 6px; line-height: 1.35; }
.markdown-paragraph { margin: 6px 0; white-space: pre-wrap; }
.markdown-list { margin: 6px 0; padding-left: 22px; }
.markdown-code {
  margin: 8px 0;
  padding: 10px;
  overflow-x: auto;
  white-space: pre;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f8fafc;
}
</style>
