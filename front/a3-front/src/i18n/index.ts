import { createI18n } from 'vue-i18n'

import { BUILT_IN_LOCALE, BUILT_IN_MESSAGES } from './catalog'

type LocaleMessage = string | LocaleMessages
interface LocaleMessages {
  [key: string]: LocaleMessage
}
const defaultLocale: string = BUILT_IN_LOCALE
const initialMessages: Record<string, LocaleMessages> = {
  [defaultLocale]: BUILT_IN_MESSAGES as unknown as LocaleMessages,
}

export const i18n = createI18n({
  legacy: false,
  locale: defaultLocale,
  fallbackLocale: defaultLocale,
  missingWarn: false,
  fallbackWarn: false,
  missing: (_locale, key) => key === 'common.notAvailable'
    ? BUILT_IN_MESSAGES.common.state.unknown
    : key,
  messages: initialMessages,
})

export function installLocaleMessages(locale: string, messages: LocaleMessages): void {
  const installed = sanitizeMessages(messages)
  const existing = i18n.global.getLocaleMessage(locale) as LocaleMessages
  const base = locale === BUILT_IN_LOCALE
    ? BUILT_IN_MESSAGES as unknown as LocaleMessages
    : existing
  i18n.global.setLocaleMessage(locale, mergeMessages(base, installed))
}

export function activateLocale(locale: string): string {
  const activeLocale = i18n.global.availableLocales.includes(locale) ? locale : BUILT_IN_LOCALE
  i18n.global.locale.value = activeLocale
  if (typeof document !== 'undefined') document.documentElement.lang = activeLocale
  return activeLocale
}

function sanitizeMessages(value: Record<string, unknown>): LocaleMessages {
  const sanitized: LocaleMessages = {}
  for (const [key, child] of Object.entries(value)) {
    if (typeof child === 'string') {
      if (child.trim()) sanitized[key] = child
    } else if (isMessageObject(child)) {
      const nested = sanitizeMessages(child)
      if (Object.keys(nested).length) sanitized[key] = nested
    }
  }
  return sanitized
}

function mergeMessages(base: LocaleMessages, additions: LocaleMessages): LocaleMessages {
  const merged: LocaleMessages = { ...base }
  for (const [key, value] of Object.entries(additions)) {
    const original = merged[key]
    merged[key] = isMessageObject(original) && isMessageObject(value)
      ? mergeMessages(original, value)
      : value
  }
  return merged
}

function isMessageObject(value: unknown): value is LocaleMessages {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

activateLocale(BUILT_IN_LOCALE)
