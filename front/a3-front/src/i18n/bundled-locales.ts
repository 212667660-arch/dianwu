import enUS from './locales/en-US/bundled.json'
import zhTW from './locales/zh-TW/bundled.json'

export const BUNDLED_LOCALES = ['zh-CN', 'en-US', 'zh-TW'] as const
export type BundledLocale = typeof BUNDLED_LOCALES[number]

export const BUNDLED_LOCALE_STORAGE_KEY = 'a3.ui-locale'

export const BUNDLED_LOCALE_SUMMARIES = [
  { locale: 'zh-CN', nativeName: 'Simplified Chinese', status: 'built_in' as const },
  { locale: 'en-US', nativeName: enUS.nativeName, status: 'built_in' as const },
  { locale: 'zh-TW', nativeName: zhTW.nativeName, status: 'built_in' as const },
]

export const BUNDLED_LOCALE_OVERLAYS = {
  'en-US': enUS.messages,
  'zh-TW': zhTW.messages,
} satisfies Record<Exclude<BundledLocale, 'zh-CN'>, Record<string, unknown>>

export function isBundledLocale(value: unknown): value is BundledLocale {
  return typeof value === 'string' && (BUNDLED_LOCALES as readonly string[]).includes(value)
}
