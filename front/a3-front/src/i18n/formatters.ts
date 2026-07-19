import { i18n } from './index'

type DateInput = Date | number | string

const dateDefaults: Intl.DateTimeFormatOptions = { year: 'numeric', month: '2-digit', day: '2-digit' }
const dateTimeDefaults: Intl.DateTimeFormatOptions = {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
}

export function formatDate(value: DateInput, options: Intl.DateTimeFormatOptions = {}): string {
  return new Intl.DateTimeFormat(activeLocale(), { ...dateDefaults, ...options }).format(toDate(value))
}

export function formatDateTime(value: DateInput, options: Intl.DateTimeFormatOptions = {}): string {
  return new Intl.DateTimeFormat(activeLocale(), { ...dateTimeDefaults, ...options }).format(toDate(value))
}

export function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(activeLocale(), options).format(value)
}

export function formatPercent(value: number, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(activeLocale(), { style: 'percent', maximumFractionDigits: 1, ...options }).format(value)
}

export function formatRelativeTime(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
  options: Intl.RelativeTimeFormatOptions = {},
): string {
  return new Intl.RelativeTimeFormat(activeLocale(), { numeric: 'auto', ...options }).format(value, unit)
}

function activeLocale(): string {
  return i18n.global.locale.value
}

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value)
}
