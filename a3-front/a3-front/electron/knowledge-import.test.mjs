import assert from 'node:assert/strict'
import {
  mkdtemp,
  readFile,
  readdir,
  symlink,
  truncate,
  writeFile,
} from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import {
  createKnowledgeImporter,
  validateKnowledgeFileSize,
} from './knowledge-import.mjs'


async function tempRoot() {
  return mkdtemp(path.join(os.tmpdir(), 'a3-knowledge-'))
}


test('imports one verified object atomically and deduplicates by sha256', async () => {
  const root = await tempRoot()
  const source = path.join(root, 'lesson.txt')
  await writeFile(source, '你好，知识库。', 'utf8')
  const importer = createKnowledgeImporter({ userDataDir: root })

  const first = await importer.importPaths([source])
  const second = await importer.importPaths([source])

  assert.equal(first.length, 1)
  assert.equal(first[0].sha256, second[0].sha256)
  assert.equal(first[0].object_relpath, 'objects/' + first[0].sha256)
  assert.equal(first[0].display_name, 'lesson.txt')
  assert.equal(first[0].mime_type, 'text/plain')
  assert.equal(Object.hasOwn(first[0], 'path'), false)
  assert.equal(
    await readFile(path.join(root, 'knowledge', first[0].object_relpath), 'utf8'),
    '你好，知识库。',
  )
  assert.deepEqual(await readdir(path.join(root, 'knowledge', 'tmp')), [])
})


test('prepares an empty optional-pack directory with local installation guidance', async () => {
  const root = await tempRoot()
  const importer = createKnowledgeImporter({ userDataDir: root })

  await importer.prepare()

  const packsRoot = path.join(root, 'knowledge', 'packs')
  assert.deepEqual(await readdir(packsRoot), ['README.txt'])
  const guidance = await readFile(path.join(packsRoot, 'README.txt'), 'utf8')
  assert.match(guidance, /不会自动下载/)
  assert.match(guidance, /许可和 SHA-256/)
})


test('rejects symbolic links and extension-signature mismatches', async t => {
  const root = await tempRoot()
  const importer = createKnowledgeImporter({ userDataDir: root })
  const target = path.join(root, 'target.txt')
  const link = path.join(root, 'link.txt')
  const fakePdf = path.join(root, 'fake.pdf')
  await writeFile(target, 'target', 'utf8')
  await writeFile(fakePdf, 'not a pdf', 'utf8')

  await assert.rejects(
    () => importer.importPaths([fakePdf]),
    error => error?.code === 'KNOWLEDGE_FILE_SIGNATURE_MISMATCH',
  )
  try {
    await symlink(target, link)
  } catch (error) {
    if (error?.code === 'EPERM') {
      t.diagnostic('symbolic link creation is not permitted on this Windows host')
      return
    }
    throw error
  }
  await assert.rejects(
    () => importer.importPaths([link]),
    error => error?.code === 'KNOWLEDGE_FILE_PATH_UNSAFE',
  )
})


test('rejects unsupported formats directories and oversized individual files', async () => {
  const root = await tempRoot()
  const importer = createKnowledgeImporter({ userDataDir: root })
  const unsupported = path.join(root, 'lesson.exe')
  const oversized = path.join(root, 'oversized.txt')
  await writeFile(unsupported, 'binary', 'utf8')
  await writeFile(oversized, 'x', 'utf8')
  await truncate(oversized, 500 * 1024 * 1024 + 1)

  await assert.rejects(
    () => importer.importPaths([unsupported]),
    error => error?.code === 'KNOWLEDGE_FORMAT_UNSUPPORTED',
  )
  await assert.rejects(
    () => importer.importPaths([root]),
    error => error?.code === 'KNOWLEDGE_FILE_PATH_UNSAFE',
  )
  await assert.rejects(
    () => importer.importPaths([oversized]),
    error => error?.code === 'KNOWLEDGE_FILE_TOO_LARGE' && /500 MiB/.test(error.message),
  )
})


test('accepts an individual file size up to five hundred MiB', () => {
  assert.doesNotThrow(() => validateKnowledgeFileSize(500 * 1024 * 1024))
  assert.throws(
    () => validateKnowledgeFileSize(500 * 1024 * 1024 + 1),
    error => error?.code === 'KNOWLEDGE_FILE_TOO_LARGE' && /500 MiB/.test(error.message),
  )
})


test('rejects more than fifty files before reading their contents', async () => {
  const root = await tempRoot()
  const source = path.join(root, 'lesson.txt')
  await writeFile(source, 'text', 'utf8')
  const importer = createKnowledgeImporter({ userDataDir: root })

  await assert.rejects(
    () => importer.importPaths(Array.from({ length: 51 }, () => source)),
    error => error?.code === 'KNOWLEDGE_IMPORT_BATCH_TOO_LARGE',
  )
})


test('rejects batches above five hundred MiB from metadata before hashing', async () => {
  const root = await tempRoot()
  const paths = []
  for (let index = 0; index < 6; index += 1) {
    const filePath = path.join(root, 'large-' + index + '.txt')
    await writeFile(filePath, 'x', 'utf8')
    await truncate(filePath, index === 5 ? 1 : 100 * 1024 * 1024)
    paths.push(filePath)
  }
  const importer = createKnowledgeImporter({ userDataDir: root })

  await assert.rejects(
    () => importer.importPaths(paths),
    error => error?.code === 'KNOWLEDGE_IMPORT_BATCH_TOO_LARGE',
  )
})
