import { afterEach, describe, expect, it } from 'vitest'

import { BackendApiError } from '@/api/transport'
import { BUILT_IN_LOCALE, BUILT_IN_MESSAGES } from './catalog'
import { errorMessage } from './errors'
import { formatDate, formatNumber } from './formatters'
import { activateLocale, i18n, installLocaleMessages } from './index'

const fixedUtcDate = new Date('2026-07-19T08:15:30.000Z')

afterEach(() => {
  activateLocale(BUILT_IN_LOCALE)
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

  it('formats values through Intl using the active locale explicitly', () => {
    activateLocale('zh-CN')
    expect(formatNumber(12345.6)).toBe(new Intl.NumberFormat('zh-CN').format(12345.6))
    expect(formatDate(fixedUtcDate, { timeZone: 'UTC' })).toBe(new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC',
    }).format(fixedUtcDate))
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
