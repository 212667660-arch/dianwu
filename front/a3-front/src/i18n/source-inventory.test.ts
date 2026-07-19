import { readFileSync, readdirSync } from 'node:fs'
import { relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { BUILT_IN_MESSAGES, flattenMessages } from './catalog'

import {
  CLASSIFIED_REASONS,
  extractSourceCandidates,
  shouldScanSource,
  validateInventory,
  validateRepositoryInventory,
  type InventoryEntry,
  type SourceCandidate,
} from './source-inventory'

function productionCandidates(rootName: 'src' | 'electron'): SourceCandidate[] {
  const root = resolve(process.cwd(), rootName)
  const files: string[] = []
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name)
      if (entry.isDirectory()) walk(path)
      else files.push(path)
    }
  }
  walk(root)
  return files
    .map(path => relative(process.cwd(), path).replaceAll('\\', '/'))
    .filter(shouldScanSource)
    .sort()
    .flatMap(source => extractSourceCandidates(source, readFileSync(resolve(process.cwd(), source), 'utf8')))
}

const rendererProductionCandidates = (): SourceCandidate[] => productionCandidates('src')
const electronProductionCandidates = (): SourceCandidate[] => productionCandidates('electron')

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
    expect(candidates[1].static_parts).toEqual(['进度 ', '/', ''])
    expect(candidates[0].static_parts).toEqual(['真实文案'])
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
    expect(candidates[4].static_parts).toEqual(['第 ', ' 页'])
    expect(candidates[6].expressions).toEqual(['current', 'total'])
  })

  it('extracts visible text and static accessibility attributes from the allowlisted pet HTML without script or style text', () => {
    const source = `<!doctype html><html><head><title>伙伴标题</title><style>.x::after{content:'样式中文'}</style></head>
      <body><main aria-label="伙伴标签" title="操作提示"><span>可见说明</span><img alt="伙伴图片" /></main>
      <script>const hidden = '脚本中文'</script></body></html>`
    const candidates = extractSourceCandidates('electron/pet/index.html', source)
    expect(candidates.map(candidate => candidate.raw)).toEqual(['伙伴标题', '伙伴标签', '操作提示', '可见说明', '伙伴图片'])
    expect(candidates.map(candidate => candidate.kind)).toEqual([
      'html_text', 'html_static_attribute', 'html_static_attribute', 'html_text', 'html_static_attribute',
    ])
  })

  it('extracts Simplified Chinese JSON string leaves with stable JSON pointers', () => {
    const source = '{\n  "displayName": "墨团",\n  "description": "学习精灵",\n  "animations": { "idle": "internal-token" }\n}'
    const first = extractSourceCandidates('electron/pets/motuan/pet.json', source)
    const repeated = extractSourceCandidates('electron/pets/motuan/pet.json', source)
    expect(first).toEqual(repeated)
    expect(first.map(candidate => ({ raw: candidate.raw, kind: candidate.kind, pointer: candidate.json_pointer }))).toEqual([
      { raw: '墨团', kind: 'json_string', pointer: '/displayName' },
      { raw: '学习精灵', kind: 'json_string', pointer: '/description' },
    ])
    expect(first[0]).toMatchObject({ line: 2, column: 19 })
  })

  it('produces stable location-sensitive ids and source coordinates', () => {
    const first = extractSourceCandidates('src/a.ts', "const a = '甲文案'\nconst b = '乙文案'")
    const repeated = extractSourceCandidates('src/a.ts', "const a = '甲文案'\nconst b = '乙文案'")
    const moved = extractSourceCandidates('src/a.ts', "\nconst a = '甲文案'\nconst b = '乙文案'")
    expect(first).toEqual(repeated)
    expect(first[0]).toMatchObject({ source: 'src/a.ts', line: 1, column: 11 })
    expect(first[0].id).not.toBe(moved[0].id)
  })

  it('preserves source-file columns and stable ids for inline Vue blocks', () => {
    const source = `<template><p title="内联标题">内联正文</p></template>\n<script setup>const label = '内联脚本'</script>`
    const first = extractSourceCandidates('src/Inline.vue', source)
    const repeated = extractSourceCandidates('src/Inline.vue', source)
    const byRaw = new Map(first.map(candidate => [candidate.raw, candidate]))
    const sourceColumn = (raw: string) => source.split('\n')[raw === '内联脚本' ? 1 : 0].indexOf(raw) + 1
    expect(byRaw.get('内联标题')).toMatchObject({ line: 1, column: sourceColumn('内联标题') - 1 })
    expect(byRaw.get('内联正文')).toMatchObject({ line: 1, column: sourceColumn('内联正文') })
    expect(byRaw.get('内联脚本')).toMatchObject({ line: 2, column: sourceColumn('内联脚本') - 1 })
    expect(first.map(candidate => candidate.id)).toEqual(repeated.map(candidate => candidate.id))
  })

  it('filters tests, generated output, and locale catalogs', () => {
    expect(shouldScanSource('src/App.vue')).toBe(true)
    expect(shouldScanSource('electron/pet/index.html')).toBe(true)
    expect(shouldScanSource('electron/pets/motuan/pet.json')).toBe(true)
    for (const path of [
      'src/App.test.ts', 'dist/app.js', 'generated/messages.ts', 'src/i18n/locales/zh-CN/a.json',
      'package.json', 'electron/random.html', 'electron/pet/config.json', 'electron/pets/motuan/other.json',
    ]) {
      expect(shouldScanSource(path), path).toBe(false)
    }
  })
})

describe('source inventory validation', () => {
  it('uses the reviewed closed renderer classification reasons', () => {
    expect(CLASSIFIED_REASONS).toEqual([
      'canonical_enum',
      'protocol_token',
      'static_markup_template',
      'compatibility_fallback',
      'internal_log',
      'developer_diagnostic',
      'non_user_data',
    ])
  })
  const candidate = (overrides: Partial<SourceCandidate> = {}): SourceCandidate => ({
    id: 'candidate-1', source: 'src/a.ts', kind: 'template_expression', raw: '进度 ${current}/${total}',
    expressions: ['current', 'total'], static_parts: ['进度 ', '/', ''], line: 1, column: 1, ...overrides,
  })

  it('reports both missing candidates and extra entries', () => {
    const result = validateInventory([candidate()], [{ id: 'stale', mode: 'classified', reason: 'canonical_enum' }], {})
    expect(result.missing.map(item => item.id)).toEqual(['candidate-1'])
    expect(result.extra.map(item => item.id)).toEqual(['stale'])
  })

  it('validates mapped templates without folding duplicate or reordered expressions', () => {
    const entry: InventoryEntry = {
      id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {current}/{total}',
      expression_bindings: [{ expression: 'current', placeholder: 'current' }, { expression: 'total', placeholder: 'total' }],
    }
    expect(validateInventory([candidate()], [entry], { progress: '进度 {current}/{total}' }).issues).toEqual([])
    expect(validateInventory([candidate()], [{ ...entry, expression_bindings: [...entry.expression_bindings].reverse() }], { progress: '进度 {total}/{current}' }).issues).toContainEqual(expect.objectContaining({ code: 'expression_mismatch' }))
    const duplicate = candidate({ raw: '${current}/${current}', expressions: ['current', 'current'], static_parts: ['', '/', ''] })
    expect(validateInventory([duplicate], [{ ...entry, template: '{current}/{current}', expression_bindings: [{ expression: 'current', placeholder: 'current' }] }], { progress: '{current}/{current}' }).issues).toContainEqual(expect.objectContaining({ code: 'expression_mismatch' }))
  })

  it('rejects unknown classification reasons and catalog value mismatch', () => {
    const mapped: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {current}/{total}', expression_bindings: [{ expression: 'current', placeholder: 'current' }, { expression: 'total', placeholder: 'total' }] }
    expect(validateInventory([candidate()], [mapped], { progress: '不同文案 {current}/{total}' }).issues).toContainEqual(expect.objectContaining({ code: 'catalog_value_mismatch' }))
    expect(validateInventory([candidate()], [{ id: 'candidate-1', mode: 'classified', reason: 'anything' as never }], {}).issues).toContainEqual(expect.objectContaining({ code: 'invalid_reason' }))
  })

  it('rejects mapped static text that differs from the source candidate', () => {
    const plain = candidate({ kind: 'string_literal', raw: '原始文案', expressions: [], static_parts: ['原始文案'] })
    const entry: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'plain', template: '错误文案', expression_bindings: [] }
    expect(validateInventory([plain], [entry], { plain: '错误文案' }).issues).toContainEqual(expect.objectContaining({ code: 'template_mismatch' }))
  })

  it('rejects matching placeholders when static template parts differ', () => {
    const entry: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '错误 {current}/{total}', expression_bindings: [{ expression: 'current', placeholder: 'current' }, { expression: 'total', placeholder: 'total' }] }
    expect(validateInventory([candidate()], [entry], { progress: entry.template }).issues).toContainEqual(expect.objectContaining({ code: 'template_mismatch' }))
  })

  it('allows semantic placeholder names for exact complex source expressions', () => {
    for (const [expression, placeholder] of [
      ['item.display_name', 'name'],
      ['backend.resources.length', 'count'],
      ['Math.round(progress)', 'percent'],
    ]) {
      const complex = candidate({ raw: `值 \${${expression}}`, expressions: [expression], static_parts: ['值 ', ''] })
      const entry: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'value', template: `值 {${placeholder}}`, expression_bindings: [{ expression, placeholder }] }
      expect(validateInventory([complex], [entry], { value: entry.template }).issues, expression).toEqual([])
    }
  })

  it('rejects invalid placeholder names and placeholder order or repetition differences', () => {
    const base: InventoryEntry = { id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {current}/{total}', expression_bindings: [{ expression: 'current', placeholder: 'current' }, { expression: 'total', placeholder: 'total' }] }
    expect(validateInventory([candidate()], [{ ...base, expression_bindings: [{ expression: 'current', placeholder: 'bad-name' }, base.expression_bindings[1]] }], { progress: '进度 {bad-name}/{total}' }).issues).toContainEqual(expect.objectContaining({ code: 'invalid_placeholder' }))
    expect(validateInventory([candidate()], [{ ...base, template: '进度 {total}/{current}' }], { progress: '进度 {total}/{current}' }).issues).toContainEqual(expect.objectContaining({ code: 'template_mismatch' }))
    expect(validateInventory([candidate()], [{ ...base, template: '进度 {current}/{current}' }], { progress: '进度 {current}/{current}' }).issues).toContainEqual(expect.objectContaining({ code: 'template_mismatch' }))
  })

  it('requires distinct source expressions to bind distinct placeholders', () => {
    const entry: InventoryEntry = {
      id: 'candidate-1', mode: 'mapped', catalog_key: 'progress', template: '进度 {value}/{value}',
      expression_bindings: [{ expression: 'current', placeholder: 'value' }, { expression: 'total', placeholder: 'value' }],
    }
    expect(validateInventory([candidate()], [entry], { progress: entry.template }).issues).toContainEqual(expect.objectContaining({ code: 'placeholder_collision' }))
  })

  it('allows repeated occurrences of one expression to reuse its placeholder', () => {
    const repeated = candidate({ raw: '${name} 对应 ${name}', expressions: ['name', 'name'], static_parts: ['', ' 对应 ', ''] })
    const entry: InventoryEntry = {
      id: 'candidate-1', mode: 'mapped', catalog_key: 'name', template: '{name} 对应 {name}',
      expression_bindings: [{ expression: 'name', placeholder: 'name' }, { expression: 'name', placeholder: 'name' }],
    }
    expect(validateInventory([repeated], [entry], { name: entry.template }).issues).toEqual([])
  })

  it('treats an empty staging inventory as incomplete when repository candidates exist', () => {
    const result = validateRepositoryInventory([candidate()], { version: 1, entries: [] }, {})
    expect(result.missing).toHaveLength(1)
    expect(result.complete).toBe(false)
  })
})

describe('repository production source inventory', () => {
  it('completely maps or classifies every Simplified Chinese AST candidate', () => {
    const rendererCandidates = rendererProductionCandidates()
    const electronCandidates = electronProductionCandidates()
    const candidates = [...rendererCandidates, ...electronCandidates]
    const inventory = JSON.parse(readFileSync(resolve(process.cwd(), 'src/i18n/locales/zh-CN/inventory.json'), 'utf8'))
    const catalog = flattenMessages(BUILT_IN_MESSAGES)
    const result = validateRepositoryInventory(candidates, inventory, catalog)
    const mappedEntries = inventory.entries.filter((entry: InventoryEntry) => entry.mode === 'mapped')
    const classifiedEntries = inventory.entries.filter((entry: InventoryEntry) => entry.mode === 'classified')

    expect(rendererCandidates).toHaveLength(408)
    expect(electronCandidates).toHaveLength(120)
    expect(candidates).toHaveLength(528)
    expect(mappedEntries).toHaveLength(457)
    expect(classifiedEntries).toHaveLength(71)
    expect(inventory.entries.map((entry: InventoryEntry) => entry.id)).toEqual(
      inventory.entries.map((entry: InventoryEntry) => entry.id).sort(),
    )
    const candidateById = new Map(candidates.map(candidate => [candidate.id, candidate]))
    expect(classifiedEntries.map((entry: InventoryEntry) => ({
      source: candidateById.get(entry.id)?.source,
      reason: entry.mode === 'classified' ? entry.reason : undefined,
    }))).toEqual(expect.arrayContaining([
      ...Array.from({ length: 6 }, () => ({ source: 'src/api/types.ts', reason: 'canonical_enum' })),
      { source: 'src/views/ProfileBuilder.vue', reason: 'protocol_token' },
    ]))
    expect(classifiedEntries.filter((entry: InventoryEntry) => entry.mode === 'classified' && entry.reason === 'protocol_token')).toHaveLength(1)
    const electronIds = new Set(electronCandidates.map(candidate => candidate.id))
    const electronMapped = mappedEntries.filter((entry: InventoryEntry) => electronIds.has(entry.id))
    const electronClassified = classifiedEntries.filter((entry: InventoryEntry) => electronIds.has(entry.id))
    expect(electronMapped).toHaveLength(56)
    expect(electronClassified).toHaveLength(64)
    expect(new Set(electronCandidates.filter(candidate => /(?:index\.html|pet\.json)$/.test(candidate.source)).map(candidate => candidate.source))).toEqual(new Set([
      'electron/pet/index.html', 'electron/pets/motuan/pet.json',
    ]))
    expect(new Set(electronClassified.map((entry: InventoryEntry) => entry.mode === 'classified' ? entry.reason : undefined))).toEqual(
      new Set(['compatibility_fallback', 'static_markup_template']),
    )
    expect(electronClassified.filter((entry: InventoryEntry) => entry.mode === 'classified' && entry.reason === 'compatibility_fallback')).toHaveLength(62)
    expect(electronClassified.filter((entry: InventoryEntry) => entry.mode === 'classified' && entry.reason === 'static_markup_template').map((entry: InventoryEntry) => entry.id).sort()).toEqual([
      '1b5b736bc4d3cbed5291fd84', '1f422c82bdd2fe669228e4a9',
    ])
    for (const entry of electronClassified) {
      if (entry.mode !== 'classified' || entry.reason !== 'compatibility_fallback') continue
      const candidate = candidateById.get(entry.id)!
      const lines = readFileSync(resolve(process.cwd(), candidate.source), 'utf8').split('\n')
      expect(lines.slice(Math.max(0, candidate.line - 4), candidate.line + 3).join('\n'), entry.id).toMatch(/[A-Z][A-Z0-9_]{3,}/)
    }
    for (const id of [
      '45e70d4d57fe3f0987de0c40', // unsigned updater source notice
      '348ce279868556f2221eddeb', '4b622d7cdc3128c4b8762fce', // diagnostics save dialog
      '20aa3117c75db0d5dd954e15', 'af1ad8a389786ada67cd3292', // knowledge import dialog
      '063cf5f360006ae4b7356de7', '230e7872a03da15c6f0df5e1', // startup failure dialog
      '531cc01f9d2febc411827287', // pet character import dialog
      'b87c5babd3c31dda8cc1bbeb', '4857e8f62bba5dba822a07a8', 'ba20c63f9564ed00eaa20dae',
      '9bd4e45250d76c294b36df7b', 'd228f5161545ad26381fe303', '2bbeb5e9b25a8074097dadaf',
      '2b43fe7f2a4fb847860bf0e7', '3ade964ec1d0aa9baa7e48f2', '3a87b364faa0a8400f7ce515',
      '112d90853419b0e477c28d61', '3fe2e47e983e2092ef6d0170', '76ed2e4fd6c4e7a885a1f568',
      'dc510ad5c85e63c4c837a988', '7d7b10582a1236315b9901b7',
    ]) expect(electronMapped.some((entry: InventoryEntry) => entry.id === id), id).toBe(true)
    expect(mappedEntries.filter((entry: InventoryEntry) => entry.mode === 'mapped'
      && (entry.template.includes('{value}') || entry.expression_bindings.some(binding => binding.placeholder === 'value'))
    ).map((entry: InventoryEntry) => entry.id)).toEqual([])
    expect(mappedEntries.filter((entry: InventoryEntry & { catalog_key?: string }) =>
      !/^(?:common(?:\.|$)|navigation(?:\.|$)|views\.|components\.|statuses(?:\.|$)|errors(?:\.|$)|desktop(?:\.|$)|pet(?:\.|$))/.test(entry.catalog_key ?? ''),
    ).map((entry: InventoryEntry) => entry.id)).toEqual([])
    expect(electronMapped.filter((entry: InventoryEntry) => entry.mode === 'mapped'
      && !/^(?:common\.|desktop\.|errors\.[A-Z][A-Z0-9_]+$|pet\.)/.test(entry.catalog_key)
    ).map((entry: InventoryEntry) => entry.id)).toEqual([])
    for (const prefix of [
      'views.dashboard', 'views.profile', 'views.agents', 'views.learningPath', 'views.tutor', 'views.assessment',
      'views.knowledge', 'views.modelSettings', 'views.desktopSettings', 'views.onboarding',
    ]) expect(mappedEntries.some((entry: InventoryEntry) => entry.mode === 'mapped' && entry.catalog_key.startsWith(`${prefix}.`)), prefix).toBe(true)

    expect({
      complete: result.complete,
      missing: result.missing.map(candidate => `${candidate.id} ${candidate.source}:${candidate.line} ${candidate.raw}`),
      extra: result.extra.map(entry => entry.id),
      issues: result.issues,
    }).toEqual({ complete: true, missing: [], extra: [], issues: [] })
  })
})
