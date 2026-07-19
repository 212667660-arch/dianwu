import { i18n } from '@/i18n'
import { isMastery, isNextAction, masteryKey, nextActionKey } from '@/i18n/display-maps'

export const LEARNER_PROFILE_PROTOCOL_PREFIX = '\u3010\u534f\u8bae:learner-profile/v1\u3011'
export const TEXTBOOK_MATH_SUBJECT = '\u6570\u5b66' as const
export const PEOPLE_EDUCATION_PRESS_PUBLISHER = '\u4eba\u6c11\u6559\u80b2\u51fa\u7248\u793e'
export const LEGACY_DEFAULT_MODEL_LABEL = '\u9ed8\u8ba4\u6a21\u578b'

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
