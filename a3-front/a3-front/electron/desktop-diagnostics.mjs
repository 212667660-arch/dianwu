import path from 'node:path'

const MAX_LOG_LINES = 200
const MAX_LOG_LINE_LENGTH = 1_000

export function redactDiagnosticText(input) {
  let value = String(input ?? '').slice(0, 100_000)
  value = value.replace(/"(?:message|prompt|content|request_text)"\s*:\s*"(?:[^"\\]|\\.)*"/gi, match => `${match.split(':')[0]}:"<redacted>"`)
  value = value.replace(/\b(?:message|prompt|content|request_text)\s*=\s*(?:"[^"]*"|'[^']*'|\S+)/gi, field => `${field.split('=')[0]}=<redacted>`)
  value = value.replace(/(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+/gi, '$1<redacted>')
  value = value.replace(/\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1$2<redacted>')
  value = value.replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, '<redacted>')
  value = value.replace(/[A-Za-z]:\\[^\r\n]*/g, '<local-path>')
  value = value.replace(/\/(?:Users|home)\/[^\r\n]*/g, '<local-path>')
  return value
}

export function createDesktopDiagnostics({ fs, logPath, showSaveDialog, context }) {
  return {
    report,
    exportReport,
    checkForUpdates() {
      return {
        status: 'offline_build',
        message: '当前安装包未配置签名发布源，不会自动下载更新。',
      }
    },
  }

  async function report() {
    const base = await context()
    const logs = await recentLogs(fs, logPath)
    return {
      generated_at: new Date().toISOString(),
      ...base,
      logs,
    }
  }

  async function exportReport() {
    const selection = await showSaveDialog()
    if (selection?.canceled || !selection?.filePath) return { exported: false, file_name: null }
    const payload = await report()
    await fs.mkdir(path.dirname(selection.filePath), { recursive: true })
    await fs.writeFile(selection.filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
    return { exported: true, file_name: path.basename(selection.filePath) }
  }
}

async function recentLogs(fs, logPath) {
  try {
    const text = await fs.readFile(logPath, 'utf8')
    return text.split(/\r?\n/).filter(Boolean).slice(-MAX_LOG_LINES)
      .map(line => redactDiagnosticText(line.slice(0, MAX_LOG_LINE_LENGTH)))
  } catch {
    return []
  }
}
