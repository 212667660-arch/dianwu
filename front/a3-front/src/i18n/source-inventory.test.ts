import { describe, expect, it } from 'vitest'

import {
  extractSourceCandidates,
  shouldScanSource,
  validateInventory,
  type InventoryEntry,
  type SourceCandidate,
} from './source-inventory'

describe('source inventory extraction', () => {
  it('extracts only real TS and JS string nodes without crossing syntax boundaries', () => {
    const source = [
      "import value from '包名中文不采集'",
      "// '注释中文不采集'",
      "const matcher = /'正则中文不采集'/g",
      "const object = { '对象键中文不采集': 1, label: '真实文案' }",
      "function 内部标识符() { return `进度 ${current}/${total}` }",
      "const plain = `静态模板`",
    ].join('\n')

    const candidates = extractSourceCandidates('src/example.ts', source)
    expect(candidates.map(candidate => candidate.raw)).toEqual([
      '真实文案',
      '进度 ${current}/${total}',
      '静态模板',
    ])
    expect(candidates[1].expressions).toEqual(['current', 'total'])
    expect(candidates.map(candidate => candidate.kind)).toEqual([
      'string_literal',
      'template_expression',
      'no_substitution_template_literal',
    ])
  })

  it('extracts Vue text, selected static attributes, and strings inside expressions', () => {
    const source = `<template>
      <section title="静态标题" class="样式中文不采集">
        可见正文
        <input aria-label="辅助标签" placeholder="输入提示" :title="\`第 \${page} 页\`" />
        <button @click="notify('点击提示')">{{ \`当前 \${current}/\${total}\` }}</button>
      </section>
    </template>
    <script setup lang="ts">const label = '脚本文案'</script>`

    const candidates = extractSourceCandidates('src/Example.vue', source)
    expect(candidates.map(candidate => candidate.raw)).toEqual([
      '静态标题',
      '可见正文',
      '辅助标签',
      '输入提示',
      '第 ${page} 页',
      '点击提示',
      '当前 ${current}/${total}',
      '脚本文案',
    ])
    expect(candidates[4].expressions).toEqual(['page'])
    expect(candidates[6].expressions).toEqual(['current', 'total'])
  })

  it('produces stable location-sensitive ids and source coordinates', () => {
    const first = extractSourceCandidates('src/a.ts', "const a = '甲文案'\nconst b = '乙文案'")
    const repeated = extractSourceCandidates('src/a.ts', "const a = '甲文案'\nconst b = '乙文案'")
    const moved = extractSourceCandidates('src/a.ts', "\nconst a = '甲文案'\nconst b = '乙文案'")
    expect(first).toEqual(repeated)
    expect(first[0]).toMatchObject({ source: 'src/a.ts', line: 1, column: 11 })
    expect(first[0].id).not.toBe(moved[0].id)
  })

  it('filters tests, generated output, and locale catalogs', () => {
    expect(shouldScanSource('src/App.vue')).toBe(true)
    for (const path of ['src/App.test.ts', 'dist/app.js', 'generated/messages.ts', 'src/i18n/locales/zh-CN/a.json']) {
      expect(shouldScanSource(path), path).toBe(false)
    }
  })
})

describe('source inventory validation', () => {
  const candidate = (overrides: Partial<SourceCandidate> = {}): SourceCandidate => ({
    id: 'candidate-1', source: 'src/a.ts', kind: 'template_expression', raw: '进度 ${current}/${total}',
    expressions: ['current', 'total'], line: 1, column: 1, ...overrides,
  })

  it('reports both missing candidates and extra entries', () => {
    const result = validateInventory([candidate()], [{ id: 'stale', mode: 'classified', reason: 'not_user_visible' }], {})
    expect(result.missing.map(item => item.id)).toEqual(['candidate-1'])
    expect(result.extra.map(item => item.id)).toEqual(['stale'])
  })

  it('validates mapped templates without folding duplicate or reordered expressions', () => {
    const entry: InventoryEntry = {
      id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {current}/{total}',
      expression_placeholders: ['current', 'total'],
    }
    expect(validateInventory([candidate()], [entry], { progress: '进度 {current}/{total}' }).issues).toEqual([])
    expect(validateInventory([candidate()], [{ ...entry, expression_placeholders: ['total', 'current'] }], { progress: '进度 {current}/{total}' }).issues).toContainEqual(expect.objectContaining({ code: 'expression_mismatch' }))
    const duplicate = candidate({ raw: '${current}/${current}', expressions: ['current', 'current'] })
    expect(validateInventory([duplicate], [{ ...entry, template: '{current}/{current}', expression_placeholders: ['current'] }], { progress: '{current}/{current}' }).issues).toContainEqual(expect.objectContaining({ code: 'expression_mismatch' }))
  })

  it('rejects unknown classification reasons and catalog placeholder mismatch', () => {
    const mapped: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {current}/{total}', expression_placeholders: ['current', 'total'] }
    expect(validateInventory([candidate()], [mapped], { progress: '进度 {value}/{total}' }).issues).toContainEqual(expect.objectContaining({ code: 'catalog_placeholder_mismatch' }))
    expect(validateInventory([candidate()], [{ id: 'candidate-1', mode: 'classified', reason: 'anything' as never }], {}).issues).toContainEqual(expect.objectContaining({ code: 'invalid_reason' }))
  })
})
