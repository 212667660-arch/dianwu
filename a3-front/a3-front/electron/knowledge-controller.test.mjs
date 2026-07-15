import assert from 'node:assert/strict'
import { mkdtemp, readFile, stat, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createKnowledgeController } from './knowledge-controller.mjs'


test('choose files imports objects then submits only manifests', async () => {
  const posted = []
  const safeManifest = {
    sha256: 'a'.repeat(64), display_name: 'lesson.pdf', extension: '.pdf',
    mime_type: 'application/pdf', byte_size: 12, object_relpath: 'objects/' + 'a'.repeat(64),
  }
  const controller = createKnowledgeController({
    chooseFiles: async () => ['C:\\private\\lesson.pdf'],
    importer: { importPaths: async () => [safeManifest] },
    apiRequest: async request => { posted.push(request); return { ok: true, status: 202, data: { jobs: [{ id: 7 }] } } },
    validateSender: () => true,
  })

  await controller.chooseFiles({}, 3)

  assert.deepEqual(posted[0], {
    method: 'POST', path: '/api/knowledge/imports',
    body: { collection_id: 3, files: [safeManifest] },
  })
  assert.equal(JSON.stringify(posted).includes('C:\\private'), false)
})


test('open source resolves document hash to a controlled readonly copy', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'a3-preview-'))
  const objectPath = path.join(root, 'object')
  await writeFile(objectPath, 'source', 'utf8')
  const opened = []
  const controller = createKnowledgeController({
    chooseFiles: async () => [],
    importer: {
      importPaths: async () => [],
      resolveObject: async digest => {
        assert.equal(digest, 'b'.repeat(64))
        return objectPath
      },
    },
    apiRequest: async () => ({
      ok: true, status: 200,
      data: { id: 9, sha256: 'b'.repeat(64), display_name: '讲义.txt' },
    }),
    validateSender: () => true,
    previewRoot: path.join(root, 'knowledge-preview'),
    openPath: async filePath => { opened.push(filePath); return '' },
  })

  const result = await controller.openSource({}, 9, { type: 'page', start: 2, end: 2 })

  assert.equal(result.ok, true)
  assert.match(result.value.mode, /^readonly-copy$/)
  assert.match(result.value.displayName, /讲义\.txt/)
  assert.equal(await readFile(opened[0], 'utf8'), 'source')
  assert.equal((await stat(opened[0])).mode & 0o222, 0)
  assert.equal(JSON.stringify(result).includes(root), false)
})


test('untrusted dropped-file sender is rejected before any disk import', async () => {
  let imported = false
  const controller = createKnowledgeController({
    chooseFiles: async () => [],
    importer: { importPaths: async () => { imported = true; return [] } },
    apiRequest: async () => ({ ok: true, status: 200, data: {} }),
    validateSender: () => false,
  })

  const result = await controller.importDroppedFiles({}, { collectionId: 1, paths: ['C:\\private\\lesson.txt'] })

  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
  assert.equal(imported, false)
})
