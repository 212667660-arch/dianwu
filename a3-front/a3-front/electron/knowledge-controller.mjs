import crypto from 'node:crypto'
import { chmod, copyFile, mkdir, rm } from 'node:fs/promises'
import path from 'node:path'


const ACTIVE_JOB_STATES = new Set(['QUEUED', 'VALIDATING', 'PARSING', 'OCR_RUNNING', 'INDEXING'])

function failure(code, message, retryable = false) {
  return { ok: false, status: 400, error: { code, message, retryable } }
}

function validId(value) {
  return Number.isSafeInteger(value) && value > 0
}

export function createKnowledgeController({
  chooseFiles,
  importer,
  apiRequest,
  validateSender,
  previewRoot,
  openPath = async () => '',
  showItemInFolder = () => {},
  onProgress = () => {},
}) {
  let pollTimer = null
  let closed = false

  async function request(event, input) {
    if (!validateSender(event)) return failure('DESKTOP_REQUEST_DENIED', '知识库请求来源不可信。')
    return apiRequest(input, event)
  }

  async function submit(event, collectionId, paths) {
    if (!validateSender(event)) return failure('DESKTOP_REQUEST_DENIED', '知识库请求来源不可信。')
    if (!validId(collectionId)) return failure('DESKTOP_REQUEST_INVALID', '知识库集合无效。')
    if (!Array.isArray(paths) || paths.length === 0) return { ok: true, status: 200, data: { jobs: [] } }
    try {
      const files = await importer.importPaths(paths)
      const response = await request(event, {
        method: 'POST', path: '/api/knowledge/imports',
        body: { collection_id: collectionId, files },
      })
      if (response?.ok) void pollJobs(event)
      return response
    } catch (error) {
      return failure(
        typeof error?.code === 'string' ? error.code : 'KNOWLEDGE_IMPORT_FAILED',
        error instanceof Error ? error.message : '知识库导入失败。',
      )
    }
  }

  async function choose(event, collectionId) {
    if (!validateSender(event)) return failure('DESKTOP_REQUEST_DENIED', '知识库请求来源不可信。')
    const paths = await chooseFiles()
    return submit(event, collectionId, paths)
  }

  async function importDroppedFiles(event, input) {
    if (!input || !validId(input.collectionId) || !Array.isArray(input.paths)) {
      return failure('DESKTOP_REQUEST_INVALID', '拖放导入参数无效。')
    }
    return submit(event, input.collectionId, input.paths)
  }

  async function documentSource(event, documentId) {
    if (!validId(documentId)) return failure('DESKTOP_REQUEST_INVALID', '知识库文档无效。')
    const response = await request(event, {
      method: 'GET', path: `/api/knowledge/documents/${documentId}`,
    })
    if (!response?.ok) return response
    const document = response.data
    if (!/^[a-f0-9]{64}$/.test(document?.sha256 || '') || typeof document?.display_name !== 'string') {
      return failure('KNOWLEDGE_SOURCE_OPEN_FAILED', '知识库文档元数据无效。')
    }
    return { response, document, sourcePath: await importer.resolveObject(document.sha256) }
  }

  async function revealSource(event, documentId) {
    const source = await documentSource(event, documentId)
    if (source?.ok === false) return source
    showItemInFolder(source.sourcePath)
    return { ok: true, status: 200, data: { mode: 'controlled-reveal' } }
  }

  async function openSource(event, documentId, _locator) {
    if (!previewRoot) return failure('KNOWLEDGE_SOURCE_OPEN_FAILED', '预览目录尚未配置。')
    const source = await documentSource(event, documentId)
    if (source?.ok === false) return source
    const directory = path.join(previewRoot, crypto.randomUUID())
    await mkdir(directory, { recursive: true })
    const safeName = path.basename(source.document.display_name).replace(/[\0\r\n/\\]/g, '_').slice(0, 255) || 'knowledge-source'
    const previewPath = path.join(directory, safeName)
    await copyFile(source.sourcePath, previewPath)
    await chmod(previewPath, 0o444)
    const message = await openPath(previewPath)
    if (message) return failure('KNOWLEDGE_SOURCE_OPEN_FAILED', message)
    return {
      ok: true,
      value: { mode: 'readonly-copy', displayName: safeName },
      status: 200,
      data: { mode: 'readonly-copy', displayName: safeName },
    }
  }

  async function pollJobs(event) {
    if (closed || pollTimer) return
    const tick = async () => {
      const response = await request(event, { method: 'GET', path: '/api/knowledge/imports' })
      if (!response?.ok) return false
      const jobs = Array.isArray(response.data) ? response.data : (response.data?.jobs || [])
      onProgress(jobs)
      const active = jobs.some(job => ACTIVE_JOB_STATES.has(job.status))
      if (!active && pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      return active
    }
    const active = await tick()
    if (active && !closed && !pollTimer) pollTimer = setInterval(() => { void tick() }, 1000)
  }

  async function shutdown() {
    closed = true
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
    if (previewRoot) await rm(previewRoot, { recursive: true, force: true })
  }

  return Object.freeze({
    chooseFiles: choose,
    importDroppedFiles,
    revealSource,
    openSource,
    pollJobs,
    shutdown,
  })
}
