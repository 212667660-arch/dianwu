import { i18n } from '@/i18n'
import { isMastery, isNextAction, masteryKey, nextActionKey } from '@/i18n/display-maps'

export function protocolFields(text?: string | null): Record<string, string> {
  if (!text) return {}
  const fields: Record<string, string> = {}
  text.split(/\r?\n/).forEach((line) => {
    const index = line.indexOf('：')
    if (index <= 0 || line.startsWith('【')) return
    fields[line.slice(0, index)] = line.slice(index + 1).trim()
  })
  return fields
}

export function actionLabel(action?: string | null): string {
  if (!action) return i18n.global.t('statuses.diagnosisWaiting')
  return isNextAction(action) ? i18n.global.t(nextActionKey(action)) : action
}

export function masteryLabel(label?: string): string {
  if (!label) return i18n.global.t('statuses.masteryDisplay.unassessed')
  return isMastery(label) ? i18n.global.t(masteryKey(label)) : label
}
