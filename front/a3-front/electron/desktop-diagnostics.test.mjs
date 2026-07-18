import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createDesktopDiagnostics, redactDiagnosticText } from './desktop-diagnostics.mjs'

test('diagnostic redaction removes credentials request text and absolute local paths', () => {
  const value = redactDiagnosticText('Authorization: Bearer secret-token api_key=sk-abcdefghij token=desktop-secret message="我的隐私问题" C:\\Users\\student\\private\\a3.log')
  assert.doesNotMatch(value, /secret-token|sk-abcdefghij|desktop-secret|我的隐私问题|C:\\Users/i)
  assert.match(value, /<redacted>/)
  assert.match(value, /<local-path>/)
})

test('diagnostics report and export contain only sanitized bounded logs', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'a3-diagnostics-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const logPath = path.join(root, 'electron.log')
  const exportPath = path.join(root, 'report.json')
  await fs.writeFile(logPath, [
    'backend ready',
    'Authorization: Bearer secret-token',
    'request_text="private lesson" C:\\Users\\student\\book.pdf',
  ].join('\n'), 'utf8')
  const diagnostics = createDesktopDiagnostics({
    fs,
    logPath,
    showSaveDialog: async () => ({ canceled: false, filePath: exportPath }),
    context: async () => ({ app_version: '1.2.3', platform: 'win32', backend_ready: true, ocr_available: true }),
  })

  const report = await diagnostics.report()
  const exported = await diagnostics.exportReport()
  const written = await fs.readFile(exportPath, 'utf8')

  assert.equal(report.app_version, '1.2.3')
  assert.equal(report.logs.length, 3)
  assert.deepEqual(exported, { exported: true, file_name: 'report.json' })
  assert.doesNotMatch(JSON.stringify(report), /secret-token|private lesson|C:\\Users/i)
  assert.doesNotMatch(written, /secret-token|private lesson|C:\\Users/i)
  assert.deepEqual(diagnostics.checkForUpdates(), {
    status: 'offline_build', message: '当前安装包未配置签名发布源，不会自动下载更新。',
  })
})
