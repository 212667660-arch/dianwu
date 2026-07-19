import { i18n } from './index'

type DateInput = Date | number | string

const dateDefaults: Intl.DateTimeFormatOptions = { year: 'numeric', month: '2-digit', day: '2-digit' }
const dateTimeDefaults: Intl.DateTimeFormatOptions = {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
}

export function formatDate(
  value: DateInput,
  options: Intl.DateTimeFormatOptions = {},
  locale: string = activeLocale(),
): string {
  return new Intl.DateTimeFormat(locale, { ...dateDefaults, ...options }).format(toDate(value))
}

export function formatDateTime(
  value: DateInput,
  options: Intl.DateTimeFormatOptions = {},
  locale: string = activeLocale(),
): string {
  return new Intl.DateTimeFormat(locale, { ...dateTimeDefaults, ...options }).format(toDate(value))
}

export function formatNumber(
  value: number,
  options: Intl.NumberFormatOptions = {},
  locale: string = activeLocale(),
): string {
  return new Intl.NumberFormat(locale, options).format(value)
}

export function formatPercent(
  value: number,
  options: Intl.NumberFormatOptions = {},
  locale: string = activeLocale(),
): string {
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1, ...options }).format(value)
}

export function formatRelativeTime(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
  options: Intl.RelativeTimeFormatOptions = {},
  locale: string = activeLocale(),
): string {
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto', ...options }).format(value, unit)
}

function activeLocale(): string {
  return i18n.global.locale.value
}

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value)
}
