import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { KNOWLEDGE_IMPORT_STATUSES } from '@/api/types'
import { actionLabel, masteryLabel, protocolFields } from '@/utils/protocol'
import { flattenMessages, BUILT_IN_MESSAGES } from './catalog'
import {
  accessModeKey, artifactStatusKey, bundleStatusKey, difficultyKey, evidenceStatusKey,
  importStatusKey, masteryKey, nextActionKey, privacyModeKey, providerKey,
  reasoningEffortKey, resourceTypeKey, stageKey, subjectKey,
} from './display-maps'

const catalog = flattenMessages(BUILT_IN_MESSAGES)

describe('localized application shell coverage', () => {
  it('uses resolvable title keys for every route', () => {
    const visit = (items: typeof routes): void => items.forEach((route) => {
      expect(route.meta).not.toHaveProperty('title')
      expect(route.meta?.titleKey).toEqual(expect.any(String))
      expect(catalog[String(route.meta?.titleKey)]).toEqual(expect.any(String))
      if (route.children) visit(route.children as typeof routes)
    })
    visit(routes)
  })

  it('maps every canonical API value, including the public import-status contract, to a resolvable catalog key', () => {
    expect(KNOWLEDGE_IMPORT_STATUSES).toEqual([
      'QUEUED', 'VALIDATING', 'PARSING', 'OCR_REQUIRED', 'OCR_RUNNING',
      'INDEXING', 'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED',
    ])

    const mappedKeys = [
      ...(['基础', '提高', '挑战'] as const).map(difficultyKey),
      ...(['初中', '高中'] as const).map(stageKey),
      ...(['数学'] as const).map(subjectKey),
      ...(['WEAK', 'LEARNING', 'PROFICIENT', 'MASTERED'] as const).map(masteryKey),
      ...(['course_explanation', 'mind_map', 'question_bank', 'extended_reading', 'adaptive_practice'] as const).map(resourceTypeKey),
      ...(['COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED'] as const).map(bundleStatusKey),
      ...(['SUCCEEDED', 'FAILED', 'CANCELLED'] as const).map(artifactStatusKey),
      ...(['grounded', 'insufficient', 'unavailable'] as const).map(evidenceStatusKey),
      ...(['openai', 'anthropic'] as const).map(providerKey),
      ...(['auto', 'off', 'low', 'medium', 'high', 'xhigh'] as const).map(reasoningEffortKey),
      ...KNOWLEDGE_IMPORT_STATUSES.map(importStatusKey),
      ...(['OFFICIAL_READER', 'LICENSED_DOWNLOAD', 'EXTERNAL_CATALOG'] as const).map(accessModeKey),
      ...(['allow_model_context', 'local_search_only'] as const).map(privacyModeKey),
      ...(['DIAGNOSE', 'REVIEW', 'START_PRACTICE', 'REMEDIATE', 'PRACTICE', 'CONSOLIDATE', 'CHALLENGE'] as const).map(nextActionKey),
    ]

    expect(mappedKeys).toContain('statuses.difficulty.basic')
    for (const key of mappedKeys) expect(catalog[key], key).toEqual(expect.any(String))
  })

  it('keeps Han literals out of every production renderer Vue and TypeScript file', () => {
    const root = resolve(__dirname, '..')
    const productionSurface = readdirSync(root, { recursive: true })
      .map(file => String(file).replaceAll('\\', '/'))
      .filter(file => /\.(?:ts|vue)$/.test(file))
      .filter(file => !/\.(?:test|spec)\.ts$/.test(file) && !file.startsWith('tests/'))
      .sort()
    const preciseAllowlist = new Set(['api/types.ts', 'utils/protocol.ts'])

    expect(productionSurface).toHaveLength(49)
    expect(productionSurface.filter(file => file.startsWith('views/'))).toHaveLength(10)
    expect(productionSurface).toContain('components/language/LanguageSettingsCard.vue')
    productionSurface
      .filter(file => !preciseAllowlist.has(file))
      .forEach(file => expect(readFileSync(resolve(root, file), 'utf8'), file).not.toMatch(/\p{Script=Han}/u))

    const shell = readFileSync(resolve(root, 'layouts/AppLayout.vue'), 'utf8')
    expect(shell).toContain('statuses.sessionState.')
    expect(shell).not.toContain('statuses.session.')

    const types = readFileSync(resolve(root, 'api/types.ts'), 'utf8')
    expect(types.match(/\p{Script=Han}+/gu) ?? []).toEqual(['初中', '高中', '数学', '基础', '提高', '挑战'])

    const protocol = readFileSync(resolve(root, 'utils/protocol.ts'), 'utf8')
    expect(protocol.trimStart().startsWith("import { i18n } from '@/i18n'"), 'protocol import location').toBe(true)
    expect([...protocol.matchAll(/line\.(?:indexOf|startsWith)\('([^']+)'\)/g)].map(match => match[1]).sort()).toEqual(['【', '：'].sort())
    expect(protocol).not.toMatch(/\p{Script=Han}/u)
  })

  it('keeps fixed Chinese protocol parsing while localizing only display labels', () => {
    expect(protocolFields('【学习者画像】\n学习目标：掌握一次函数\n无效行')).toEqual({ 学习目标: '掌握一次函数' })
    expect(actionLabel()).toBe('等待诊断')
    expect(actionLabel('CHALLENGE')).toBe('挑战迁移')
    expect(actionLabel('FUTURE_ACTION')).toBe('FUTURE_ACTION')
    expect(masteryLabel()).toBe('未评估')
    expect(masteryLabel('MASTERED')).toBe('已掌握')
    expect(masteryLabel('FUTURE_MASTERY')).toBe('FUTURE_MASTERY')
  })
})
