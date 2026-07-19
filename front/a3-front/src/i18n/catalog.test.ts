import { bytesToHex } from '@noble/hashes/utils'
import { sha256 } from '@noble/hashes/sha256'
import canonicalize from 'canonicalize'
import { describe, expect, it } from 'vitest'

import {
  BASE_CATALOG_HASH,
  BUILT_IN_MESSAGES,
  CATALOG_VERSION,
  buildBaseCatalogPayload,
  flattenMessages,
  placeholdersFor,
} from './catalog'

const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor'])
const VISIBLE_SOURCE_INVENTORY = [
  '智学协作台', '给学习留一点温度', '学习总览', '学习画像', '智能体协作', '学习路径',
  '学习助手', '练习评估', '知识库', '模型设置', '桌面设置', '首次启动', '打开导航',
  '打开书桌', '模型就绪', '后端在线', '服务离线', '新的学习空间', '尚未开始',
  '今天想一起学点什么？', '模型未就绪', '资源生成进度', '需要先完成学习诊断',
  '教材资料尚未绑定', '教材证据不足', '重新检索', '扩大范围', '说点什么…',
  '本空间资料 · {count}', '允许模型参考相关片段', '仅本机检索，不发送片段',
  '一页空白，也是一种邀请。把讲义、笔记或表格放进来吧。', '资料集合', '导入文件',
  '选一份资料，看看它被整理成了什么模样。', '需要本地 OCR', '总结知识点',
  '生成例题与步骤', '预览（本地阅读器）', '重新解析', '删除资料', '初高中数学教材',
  '出版社官方在线阅读', '学习资源包', '学习笔记', '知识导图', '例题讲解', '练习题',
  '模型配置', '默认配置', '备用配置', '自动切换备用配置', '测试连接', '连接成功',
  '墨团设置', '始终置顶', '空闲时降低动画频率', '新学习会话', '随手记', '使用建议',
] as const

describe('built-in zh-CN catalog contract', () => {
  it('uses stable ASCII semantic catalog key segments', () => {
    const keys = Object.keys(flattenMessages(BUILT_IN_MESSAGES))
    const forbiddenSegment = /^(?:动态文案|displayText.*|vueStaticAttribute|vueText|stringLiteral|templateExpression|source|message\d+|[a-f0-9]{16,}|\d+)$/i
    expect(keys.filter(key => key.split('.').some((segment, index, segments) => {
      const isStableErrorCode = segments[0] === 'errors' && index === segments.length - 1
        && /^[A-Z][A-Z0-9_]+$/.test(segment)
      const isCanonicalStatus = segments[0] === 'statuses' && index === segments.length - 1
        && /^[A-Z][A-Z0-9_]+$/.test(segment)
      return !isStableErrorCode && !isCanonicalStatus && !/^[a-z][A-Za-z0-9]*$/.test(segment)
    }))).toEqual([])
    expect(keys.filter(key => key.split('.').some(segment => forbiddenSegment.test(segment)))).toEqual([])
  })
  it('publishes the versioned required catalog keys', () => {
    expect(CATALOG_VERSION).toBe(1)
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    expect(flat['navigation.dashboard']).toBeTruthy()
    expect(flat['views.desktopSettings.language.title']).toBeTruthy()
    expect(flat['errors.BACKEND_UNAVAILABLE']).toBeTruthy()
    expect(flat['desktop.tray.quit']).toBeTruthy()
  })

  it('preserves stable backend error codes and canonical status enums exactly', () => {
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    expect(Object.keys(BUILT_IN_MESSAGES.errors).filter(key => /^[A-Z][A-Z0-9_]+$/.test(key))).toEqual([
      'BACKEND_UNAVAILABLE', 'DESKTOP_BACKEND_UNAVAILABLE', 'DESKTOP_BRIDGE_UNAVAILABLE', 'DESKTOP_ONLY',
      'MODEL_NOT_CONFIGURED', 'MODEL_AUTHENTICATION_ERROR', 'MODEL_RATE_LIMITED', 'MODEL_REQUEST_FAILED',
      'MODEL_PROFILE_DEFAULT_MODEL_INVALID', 'STREAM_INVALID', 'STREAM_CANCELLED',
      'KNOWLEDGE_FILE_SIGNATURE_MISMATCH', 'KNOWLEDGE_PARSE_FAILED', 'KNOWLEDGE_OCR_PACK_REQUIRED',
      'KNOWLEDGE_OCR_PAGE_FAILED', 'IMPORT_FAILED', 'EXPORT_FAILED', 'LANGUAGE_PACK_INVALID',
      'LANGUAGE_PACK_INCOMPATIBLE', 'LANGUAGE_PACK_SIGNATURE_INVALID',
    ])
    expect(Object.keys(BUILT_IN_MESSAGES.statuses.session)).toEqual(['NEW', 'DIAGNOSING', 'PROFILED', 'GENERATING', 'PRACTICING', 'REVIEWING', 'COMPLETED'])
    expect(Object.keys(BUILT_IN_MESSAGES.statuses.mastery)).toEqual(['UNASSESSED', 'WEAK', 'LEARNING', 'PROFICIENT', 'MASTERED'])
    expect(Object.keys(BUILT_IN_MESSAGES.statuses.document)).toEqual(['QUEUED', 'VALIDATING', 'PARSING', 'OCR_REQUIRED', 'OCR_RUNNING', 'INDEXING', 'COMPLETED', 'FAILED'])
    expect(Object.keys(BUILT_IN_MESSAGES.statuses.resource)).toEqual(['PENDING', 'GENERATING', 'COMPLETED', 'FAILED'])
    expect(Object.keys(BUILT_IN_MESSAGES.statuses.update)).toEqual(['CHECKING', 'AVAILABLE', 'CURRENT', 'OFFLINE_BUILD', 'ERROR'])
    expect(flat['errors.KNOWLEDGE_PARSE_FAILED']).toBe('解析器未能读取这份资料。')
    expect(flat['statuses.document.OCR_REQUIRED']).toBe('等待 OCR')
  })

  it('keeps generic error fallbacks semantic and excludes internal replacement literals', () => {
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    expect(flat['errors.unknown']).toBe('请求失败，请稍后重试。')
    expect(flat['errors.unknownWithReference']).toBe('请求失败，请稍后重试。参考编号：{referenceId}')
    expect(flat['errors.UNKNOWN']).toBeUndefined()
    expect(flat['errors.UNKNOWN_WITH_REFERENCE']).toBeUndefined()
    expect(flat['components.knowledgeSourceList.normalizedPageReplacement']).toBeUndefined()
    expect(Object.values(flat)).not.toContain('第$1页')
  })

  it('uses reviewed semantic keys for shared renderer component copy', () => {
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    expect(flat['components.collectionRail.gardenTitle']).toBe('资料花园')
    expect(flat['components.collectionRail.documentCountSuffix']).toBe('份资料 ·')
    expect(flat['components.safeMermaid.unavailableNotice']).toContain('Mermaid 渲染不可用')
    expect(flat['components.safeMermaid.outlineUnavailableTitle']).toBe('大纲不可用')
    expect(flat['components.petSettingsCard.settingsLoadFailure']).toContain('无法读取')
    expect(flat['components.petSettingsCard.actionPreviewUnavailable']).toContain('不可用')
    expect(flat['components.petSettingsCard.settingsSaveFailure']).toContain('没有保存成功')
    expect(flat['components.resourceCard.securityReviewUnavailable']).toContain('审核暂时不可用')
    expect(flat['components.documentGrid.offlineOcrUnavailable']).toContain('OCR 组件不可用')
  })

  it('rejects obvious mechanical catalog key patterns while retaining semantic empty-state keys', () => {
    const flat = flattenMessages(BUILT_IN_MESSAGES)
    const mechanical = /(?:None|UnavailableAvailable|AvailableUnavailable|^source$|^message\d+$|stringLiteral|templateExpression|vueText|vueStaticAttribute)/
    expect(Object.keys(flat).filter(key => /^(?:common|navigation|components|pet|errors)\./.test(key)
      && key.split('.').some(segment => mechanical.test(segment)))).toEqual([])
    expect(flat['common.state.empty']).toBe('暂无内容')
    expect(flat['components.documentGrid.empty']).toContain('一页空白')
    expect(flat['components.conversationRail.empty']).toContain('还没有历史会话')
  })

  it('covers the reviewed SmartTutor visible-string inventory', () => {
    const values = Object.values(flattenMessages(BUILT_IN_MESSAGES))
    for (const visibleText of [
      '模型未就绪',
      '这次回答仍保持同一条清晰的上下文。',
      '中断前保留',
      '学习诊断不是电脑故障检测，而是画像 Agent 通过几轮对话了解你的学习目标、当前基础和薄弱点。',
      '当前画像已经完成，可以重新尝试刚才的请求。',
      '请先继续回答学习助手的问题，画像完成后即可生成练习和学习资源。',
      '教材资料尚未绑定',
    ]) expect(values).toContain(visibleText)
  })

  it('maps every visible Simplified Chinese source token into the catalog', () => {
    const catalogValues = new Set(Object.values(flattenMessages(BUILT_IN_MESSAGES)))
    expect(VISIBLE_SOURCE_INVENTORY.filter(message => !catalogValues.has(message))).toEqual([])
  })

  it('extracts stable sorted placeholder names', () => {
    expect(placeholdersFor('已导出 {fileName}')).toEqual(['fileName'])
    expect(placeholdersFor('{zeta}、{alpha}、{zeta}')).toEqual(['alpha', 'zeta'])
    expect(placeholdersFor('{a}、{A}')).toEqual(['A', 'a'])
  })

  it('contains only safe, non-empty string leaves', () => {
    const visit = (value: unknown, path: string[] = []): void => {
      expect(Array.isArray(value), path.join('.')).toBe(false)
      expect(value, path.join('.')).not.toBeNull()
      if (typeof value === 'object') {
        for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
          expect(FORBIDDEN_KEYS.has(key), [...path, key].join('.')).toBe(false)
          visit(child, [...path, key])
        }
        return
      }
      expect(typeof value, path.join('.')).toBe('string')
      expect((value as string).trim(), path.join('.')).not.toBe('')
      expect(value as string, path.join('.')).not.toMatch(/<\/?[A-Za-z][^>]*>/)
      expect(value as string, path.join('.')).not.toMatch(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/)
    }
    visit(BUILT_IN_MESSAGES)
  })

  it('rejects invalid catalog structures while flattening', () => {
    expect(() => flattenMessages({ list: ['invalid'] })).toThrow(/array/i)
    expect(() => flattenMessages({ missing: null })).toThrow(/null/i)
    expect(() => flattenMessages(JSON.parse('{"constructor":"invalid"}'))).toThrow(/forbidden/i)
    expect(() => flattenMessages({ count: 1 })).toThrow(/string/i)
  })

  it('derives a deterministic uppercase SHA-256 catalog digest', () => {
    const compareCodePoints = (left: string, right: string) => {
      const a = [...left].map(character => character.codePointAt(0)!)
      const b = [...right].map(character => character.codePointAt(0)!)
      for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
        if (a[index] !== b[index]) return a[index] - b[index]
      }
      return a.length - b.length
    }
    const messages = Object.entries(flattenMessages(BUILT_IN_MESSAGES))
      .sort(([left], [right]) => compareCodePoints(left, right))
      .map(([key, message]) => [key, placeholdersFor(message)])
    const payload = canonicalize({ catalog_version: CATALOG_VERSION, messages })
    expect(payload).not.toBeUndefined()
    const independentHash = bytesToHex(sha256(new TextEncoder().encode(payload!))).toUpperCase()

    expect(buildBaseCatalogPayload()).toBe(payload)
    expect(BASE_CATALOG_HASH).toMatch(/^[A-F0-9]{64}$/)
    expect(BASE_CATALOG_HASH).toBe(independentHash)
    expect(BASE_CATALOG_HASH).toBe('41B286ECB33CB107452B2DCFC530A123ED26500B79BE4FEE881D9F94EBAE5ADC')
  })

  it('deep-freezes every built-in namespace without changing the digest', () => {
    const hashBefore = BASE_CATALOG_HASH
    expect(Object.isFrozen(BUILT_IN_MESSAGES.views.tutor)).toBe(true)
    expect(() => {
      ;(BUILT_IN_MESSAGES.views.tutor as { title: string }).title = '被篡改'
    }).toThrow()
    expect(BUILT_IN_MESSAGES.views.tutor.title).toBe('今天想一起学点什么？')
    expect(BASE_CATALOG_HASH).toBe(hashBefore)
  })
})
