import { afterEach, describe, expect, it } from 'vitest'

import { BackendApiError } from '@/api/transport'
import { BUILT_IN_LOCALE, BUILT_IN_MESSAGES } from './catalog'
import { errorMessage } from './errors'
import {
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatRelativeTime,
} from './formatters'
import { activateLocale, i18n, installLocaleMessages, resetLocaleRuntimeForTests } from './index'

const fixedUtcDate = new Date('2026-07-19T08:15:30.000Z')

afterEach(() => {
  resetLocaleRuntimeForTests()
})

describe('renderer localization runtime', () => {
  it('starts with the built-in Chinese locale and updates the document language', () => {
    expect(i18n.global.locale.value).toBe('zh-CN')
    expect(i18n.global.fallbackLocale.value).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('does not allow installed messages to remove or blank built-in messages', () => {
    const original = BUILT_IN_MESSAGES.errors.BACKEND_UNAVAILABLE
    installLocaleMessages('zh-CN', { errors: { BACKEND_UNAVAILABLE: '' } })
    expect(i18n.global.t('errors.BACKEND_UNAVAILABLE')).toBe(original)
    expect(i18n.global.t('common.notAvailable')).toBe(BUILT_IN_MESSAGES.common.state.unknown)
  })

  it('activates installed locales and falls back to Chinese for unknown locales', () => {
    installLocaleMessages('en-US', { common: { notAvailable: 'Not available' } })
    expect(activateLocale('en-US')).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
    expect(activateLocale('fr-FR')).toBe('zh-CN')
    expect(i18n.global.locale.value).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('rejects forbidden keys recursively without registering a locale or polluting prototypes', () => {
    const malicious = JSON.parse('{"common":{"safe":"ok","nested":{"__proto__":{"polluted":"yes"}}},"constructor":{"prototype":{"polluted":"yes"}}}') as Record<string, unknown>

    expect(() => installLocaleMessages('evil', malicious)).toThrow(TypeError)
    expect(i18n.global.availableLocales).not.toContain('evil')
    expect(({} as { polluted?: string }).polluted).toBeUndefined()
  })

  it('resets installed locales so tests do not depend on execution order', () => {
    installLocaleMessages('en-US', { common: { state: { unknown: 'Unknown' } } })
    installLocaleMessages('zh-TW', { common: { state: { unknown: '未知' } } })
    expect(i18n.global.availableLocales).toEqual(expect.arrayContaining(['en-US', 'zh-TW']))

    resetLocaleRuntimeForTests()

    expect(i18n.global.availableLocales).toEqual(['zh-CN'])
    expect(i18n.global.locale.value).toBe('zh-CN')
    expect(activateLocale('en-US')).toBe('zh-CN')
  })

  it('formats values through Intl using the active locale explicitly', () => {
    activateLocale('zh-CN')
    expect(formatNumber(12345.6)).toBe(new Intl.NumberFormat('zh-CN').format(12345.6))
    expect(formatDate(fixedUtcDate, { timeZone: 'UTC' })).toBe(new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC',
    }).format(fixedUtcDate))
  })

  it('allows every formatter to override the active locale explicitly', () => {
    activateLocale('zh-CN')
    const dateOptions = { timeZone: 'UTC' } satisfies Intl.DateTimeFormatOptions
    const numberOptions = { style: 'unit', unit: 'kilometer' } satisfies Intl.NumberFormatOptions
    const percentOptions = { maximumFractionDigits: 1 } satisfies Intl.NumberFormatOptions

    const explicit = [
      formatDate(fixedUtcDate, dateOptions, 'en-US'),
      formatDateTime(fixedUtcDate, dateOptions, 'en-US'),
      formatNumber(12345.6, numberOptions, 'en-US'),
      formatPercent(0.1234, percentOptions, 'en-US'),
      formatRelativeTime(-1, 'day', {}, 'en-US'),
    ]
    const chinese = [
      formatDate(fixedUtcDate, dateOptions, 'zh-CN'),
      formatDateTime(fixedUtcDate, dateOptions, 'zh-CN'),
      formatNumber(12345.6, numberOptions, 'zh-CN'),
      formatPercent(0.1234, percentOptions, 'zh-CN'),
      formatRelativeTime(-1, 'day', {}, 'zh-CN'),
    ]

    expect(explicit).toEqual([
      new Intl.DateTimeFormat('en-US', { year: 'numeric', month: '2-digit', day: '2-digit', ...dateOptions }).format(fixedUtcDate),
      new Intl.DateTimeFormat('en-US', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', ...dateOptions }).format(fixedUtcDate),
      new Intl.NumberFormat('en-US', numberOptions).format(12345.6),
      new Intl.NumberFormat('en-US', { style: 'percent', ...percentOptions }).format(0.1234),
      new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' }).format(-1, 'day'),
    ])
    ;[0, 1, 2, 4].forEach(index => expect(explicit[index]).not.toBe(chinese[index]))
  })

  it('defaults every formatter to the current global locale', () => {
    installLocaleMessages('en-US', { common: { state: { unknown: 'Unknown' } } })
    activateLocale('en-US')
    const dateOptions = { timeZone: 'UTC' } satisfies Intl.DateTimeFormatOptions
    const numberOptions = { style: 'unit', unit: 'kilometer' } satisfies Intl.NumberFormatOptions

    expect(formatDate(fixedUtcDate, dateOptions)).toBe(formatDate(fixedUtcDate, dateOptions, 'en-US'))
    expect(formatDateTime(fixedUtcDate, dateOptions)).toBe(formatDateTime(fixedUtcDate, dateOptions, 'en-US'))
    expect(formatNumber(12345.6, numberOptions)).toBe(formatNumber(12345.6, numberOptions, 'en-US'))
    expect(formatPercent(0.1234)).toBe(formatPercent(0.1234, {}, 'en-US'))
    expect(formatRelativeTime(-1, 'day')).toBe(formatRelativeTime(-1, 'day', {}, 'en-US'))
  })

  it('maps known backend error codes to built-in messages', () => {
    const error = new BackendApiError(503, 'BACKEND_UNAVAILABLE', '后端原始消息', true, 'req-1')
    expect(errorMessage(error)).toBe(BUILT_IN_MESSAGES.errors.BACKEND_UNAVAILABLE)
    expect(errorMessage(error)).not.toContain(error.message)
  })

  it('renders unknown codes with a request reference and never exposes backend messages', () => {
    const error = new BackendApiError(500, 'PRIVATE_UPSTREAM_FAILURE', '后端私密错误', false, 'req-secret')
    const message = errorMessage(error)
    expect(message).toContain('PRIVATE_UPSTREAM_FAILURE')
    expect(message).toContain('req-secret')
    expect(message).not.toContain(error.message)
  })

  it('uses common.notAvailable when an unknown error has no request id', () => {
    const message = errorMessage(new BackendApiError(500, 'UNKNOWN_CODE', 'do not expose'))
    expect(message).toContain('UNKNOWN_CODE')
    expect(message).toContain(BUILT_IN_MESSAGES.common.state.unknown)
    expect(message).not.toContain('do not expose')
  })
})
