import crypto from 'node:crypto'
import { createReadStream, createWriteStream } from 'node:fs'
import {
  access,
  link,
  lstat,
  mkdir,
  open,
  rm,
  unlink,
} from 'node:fs/promises'
import path from 'node:path'
import { Transform } from 'node:stream'
import { pipeline } from 'node:stream/promises'


const MAX_FILE_BYTES = 100 * 1024 * 1024
const MAX_BATCH_BYTES = 500 * 1024 * 1024
const MAX_BATCH_FILES = 50
const SUPPORTED = Object.freeze({
  '.pdf': { mime: 'application/pdf', signature: 'pdf' },
  '.docx': { mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', signature: 'zip' },
  '.pptx': { mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', signature: 'zip' },
  '.xlsx': { mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', signature: 'zip' },
  '.txt': { mime: 'text/plain', signature: 'text' },
  '.md': { mime: 'text/markdown', signature: 'text' },
  '.markdown': { mime: 'text/markdown', signature: 'text' },
  '.csv': { mime: 'text/csv', signature: 'text' },
})


export class KnowledgeImportError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'KnowledgeImportError'
    this.code = code
  }
}


function importError(code, message) {
  return new KnowledgeImportError(code, message)
}


function isNetworkOrDevicePath(filePath) {
  const normalized = filePath.replaceAll('/', '\\')
  return normalized.startsWith('\\\\')
    || normalized.startsWith('\\\\?\\')
    || normalized.startsWith('\\\\.\\')
}


function safeDisplayName(filePath) {
  const value = path.basename(filePath).trim()
  if (!value || value.length > 255 || /[\0\r\n/\\]/.test(value)) {
    throw importError('KNOWLEDGE_FILE_PATH_UNSAFE', '文件名不符合安全要求。')
  }
  return value
}


async function validateSignature(filePath, signature) {
  const handle = await open(filePath, 'r')
  const buffer = Buffer.allocUnsafe(8192)
  let bytesRead
  try {
    ;({ bytesRead } = await handle.read(buffer, 0, buffer.length, 0))
  } finally {
    await handle.close()
  }
  const header = buffer.subarray(0, bytesRead)
  if (signature === 'pdf' && !header.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
    throw importError('KNOWLEDGE_FILE_SIGNATURE_MISMATCH', '文件内容与 PDF 扩展名不一致。')
  }
  if (signature === 'zip') {
    const prefix = header.subarray(0, 4).toString('hex')
    if (!['504b0304', '504b0506', '504b0708'].includes(prefix)) {
      throw importError('KNOWLEDGE_FILE_SIGNATURE_MISMATCH', '文件内容与 Office 扩展名不一致。')
    }
  }
  if (signature === 'text' && header.includes(0)) {
    throw importError('KNOWLEDGE_FILE_SIGNATURE_MISMATCH', '文本文件包含不支持的二进制内容。')
  }
}


async function validateSource(filePath) {
  if (typeof filePath !== 'string' || !filePath || filePath.includes('\0') || isNetworkOrDevicePath(filePath)) {
    throw importError('KNOWLEDGE_FILE_PATH_UNSAFE', '文件路径不符合安全要求。')
  }
  let metadata
  try {
    metadata = await lstat(filePath)
  } catch {
    throw importError('KNOWLEDGE_OBJECT_MISSING', '文件不存在或无法读取。')
  }
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw importError('KNOWLEDGE_FILE_PATH_UNSAFE', '只能导入本机普通文件。')
  }
  const extension = path.extname(filePath).toLowerCase()
  const format = SUPPORTED[extension]
  if (!format) {
    throw importError('KNOWLEDGE_FORMAT_UNSUPPORTED', '暂不支持这种文件格式。')
  }
  if (metadata.size <= 0) {
    throw importError('KNOWLEDGE_PARSE_FAILED', '空文件不能导入知识库。')
  }
  if (metadata.size > MAX_FILE_BYTES) {
    throw importError('KNOWLEDGE_FILE_TOO_LARGE', '单个文件不能超过 100 MB。')
  }
  return {
    sourcePath: filePath,
    displayName: safeDisplayName(filePath),
    extension,
    mimeType: format.mime,
    byteSize: metadata.size,
    signature: format.signature,
  }
}


async function syncFile(filePath) {
  const handle = await open(filePath, 'r+')
  try {
    await handle.sync()
  } finally {
    await handle.close()
  }
}


async function copyAndHash(sourcePath, tempPath) {
  const hash = crypto.createHash('sha256')
  const tap = new Transform({
    transform(chunk, _encoding, callback) {
      hash.update(chunk)
      callback(null, chunk)
    },
  })
  await pipeline(
    createReadStream(sourcePath),
    tap,
    createWriteStream(tempPath, { flags: 'wx' }),
  )
  await syncFile(tempPath)
  return hash.digest('hex')
}


async function publishObject(tempPath, finalPath) {
  try {
    await link(tempPath, finalPath)
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    await access(finalPath)
  } finally {
    await unlink(tempPath).catch(() => {})
  }
}


export function createKnowledgeImporter({ userDataDir }) {
  if (typeof userDataDir !== 'string' || !path.isAbsolute(userDataDir)) {
    throw new TypeError('Knowledge importer requires an absolute userData directory.')
  }
  const knowledgeRoot = path.join(userDataDir, 'knowledge')
  const objectsRoot = path.join(knowledgeRoot, 'objects')
  const tempRoot = path.join(knowledgeRoot, 'tmp')

  async function ensureDirectories() {
    await mkdir(objectsRoot, { recursive: true })
    await mkdir(tempRoot, { recursive: true })
  }

  async function importOne(source) {
    const tempPath = path.join(tempRoot, crypto.randomUUID() + '.part')
    try {
      const digest = await copyAndHash(source.sourcePath, tempPath)
      const finalPath = path.join(objectsRoot, digest)
      await publishObject(tempPath, finalPath)
      return Object.freeze({
        sha256: digest,
        display_name: source.displayName,
        extension: source.extension,
        mime_type: source.mimeType,
        byte_size: source.byteSize,
        object_relpath: 'objects/' + digest,
      })
    } catch (error) {
      await rm(tempPath, { force: true }).catch(() => {})
      if (error instanceof KnowledgeImportError) throw error
      throw importError('KNOWLEDGE_OBJECT_COPY_FAILED', '文件复制到本地知识库时失败。')
    }
  }

  async function importPaths(paths) {
    if (!Array.isArray(paths) || paths.length < 1 || paths.length > MAX_BATCH_FILES) {
      throw importError('KNOWLEDGE_IMPORT_BATCH_TOO_LARGE', '一次只能导入 1 至 50 个文件。')
    }
    await ensureDirectories()
    const sources = []
    for (const filePath of paths) {
      sources.push(await validateSource(filePath))
    }
    const totalBytes = sources.reduce((total, source) => total + source.byteSize, 0)
    if (totalBytes > MAX_BATCH_BYTES) {
      throw importError('KNOWLEDGE_IMPORT_BATCH_TOO_LARGE', '一次导入的文件总量不能超过 500 MB。')
    }
    for (const source of sources) {
      await validateSignature(source.sourcePath, source.signature)
    }
    const manifests = []
    for (const source of sources) {
      manifests.push(await importOne(source))
    }
    return manifests
  }

  return Object.freeze({
    importPaths,
    knowledgeRoot,
    objectsRoot,
  })
}
