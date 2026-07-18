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
  const labels: Record<string, string> = {
    DIAGNOSE: '完成诊断', REVIEW: '到期复习', START_PRACTICE: '开始练习',
    REMEDIATE: '基础纠错', PRACTICE: '渐进练习', CONSOLIDATE: '综合巩固', CHALLENGE: '挑战迁移',
  }
  return action ? labels[action] || action : '等待诊断'
}

export function masteryLabel(label?: string): string {
  const labels: Record<string, string> = {
    WEAK: '薄弱', LEARNING: '学习中', PROFICIENT: '较熟练', MASTERED: '已掌握',
  }
  return label ? labels[label] || label : '未评估'
}
