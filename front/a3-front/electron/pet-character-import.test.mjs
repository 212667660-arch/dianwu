import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { PET_ANIMATION_SPECS } from './pet-config.mjs'
import * as petCharacterImport from './pet-character-import.mjs'

const { createPetCharacterImporter } = petCharacterImport

function manifest(id = 'friend') {
  return {
    id, displayName: '新伙伴', description: '测试角色。', spritesheetPath: 'spritesheet.webp',
    cell: { width: 192, height: 208 }, grid: { columns: 8, rows: 9 },
    animations: Object.fromEntries(Object.entries(PET_ANIMATION_SPECS).map(([state, spec]) => [state, { row: spec.row, durations: [...spec.durations] }])),
  }
}

async function fixture() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'a3-pet-import-'))
  const source = path.join(root, 'source')
  const userDataDir = path.join(root, 'user')
  await fs.mkdir(source, { recursive: true })
  await fs.writeFile(path.join(source, 'pet.json'), JSON.stringify(manifest()), 'utf8')
  await fs.writeFile(path.join(source, 'spritesheet.webp'), 'webp', 'utf8')
  const importer = createPetCharacterImporter({
    fs, userDataDir,
    inspectAtlas: async () => ({ width: 1536, height: 1872, validTransparency: true }),
    uniqueId: () => 'test',
  })
  return { root, source, userDataDir, importer }
}

test('imports only the two validated character files into current', async () => {
  const { source, userDataDir, importer } = await fixture()
  await fs.writeFile(path.join(source, 'pet.json'), `\uFEFF${JSON.stringify(manifest())}`, 'utf8')
  const value = await importer.importFromDirectory(source)
  assert.equal(value.id, 'friend')
  assert.deepEqual((await fs.readdir(path.join(userDataDir, 'pets', 'current'))).sort(), ['pet.json', 'spritesheet.webp'])
})

test('invalid imports preserve the previously installed character', async () => {
  const { source, userDataDir, importer } = await fixture()
  await importer.importFromDirectory(source)
  await fs.writeFile(path.join(source, 'pet.json'), '{"broken":true}', 'utf8')
  await assert.rejects(() => importer.importFromDirectory(source))
  const stored = JSON.parse(await fs.readFile(path.join(userDataDir, 'pets', 'current', 'pet.json'), 'utf8'))
  assert.equal(stored.id, 'friend')
})

test('rejects symlinks, oversized files and invalid atlas transparency', async (context) => {
  const { source, userDataDir } = await fixture()
  await context.test('symlink', async () => {
    const link = path.join(path.dirname(source), 'link-source')
    await fs.symlink(source, link, 'junction')
    const importer = createPetCharacterImporter({ fs, userDataDir, inspectAtlas: async () => ({ width: 1536, height: 1872, validTransparency: true }) })
    await assert.rejects(() => importer.importFromDirectory(link), /ordinary directory/i)
  })
  await context.test('oversized manifest', async () => {
    await fs.writeFile(path.join(source, 'pet.json'), 'x'.repeat(65_537), 'utf8')
    const importer = createPetCharacterImporter({ fs, userDataDir, inspectAtlas: async () => ({ width: 1536, height: 1872, validTransparency: true }) })
    await assert.rejects(() => importer.importFromDirectory(source), /size/i)
  })
  await context.test('invalid transparency', async () => {
    await fs.writeFile(path.join(source, 'pet.json'), JSON.stringify(manifest()), 'utf8')
    const importer = createPetCharacterImporter({ fs, userDataDir, inspectAtlas: async () => ({ width: 1536, height: 1872, validTransparency: false }) })
    await assert.rejects(() => importer.importFromDirectory(source), /atlas/i)
  })
})

test('reset removes only the current custom character', async () => {
  const { source, userDataDir, importer } = await fixture()
  await importer.importFromDirectory(source)
  const sibling = path.join(userDataDir, 'pets', 'keep.txt')
  await fs.writeFile(sibling, 'keep', 'utf8')
  await importer.reset()
  await assert.rejects(() => fs.access(path.join(userDataDir, 'pets', 'current')))
  assert.equal(await fs.readFile(sibling, 'utf8'), 'keep')
})

test('atlas pixel validation rejects an empty used animation cell', () => {
  assert.equal(typeof petCharacterImport.validatePetAtlasBitmap, 'function')
  const width = 1536
  const height = 1872
  const bitmap = Buffer.alloc(width * height * 4)
  for (const spec of Object.values(PET_ANIMATION_SPECS)) {
    for (let column = 0; column < spec.durations.length; column += 1) {
      const left = column * 192
      const top = spec.row * 208
      for (let pixel = 0; pixel < 50; pixel += 1) {
        const x = left + (pixel % 10)
        const y = top + Math.floor(pixel / 10)
        bitmap[(y * width + x) * 4 + 3] = 255
      }
    }
  }
  assert.equal(petCharacterImport.validatePetAtlasBitmap(bitmap, width, height), true)

  const emptyCellLeft = 7 * 192
  const emptyCellTop = 1 * 208
  for (let pixel = 0; pixel < 50; pixel += 1) {
    const x = emptyCellLeft + (pixel % 10)
    const y = emptyCellTop + Math.floor(pixel / 10)
    bitmap[(y * width + x) * 4 + 3] = 0
  }
  assert.equal(petCharacterImport.validatePetAtlasBitmap(bitmap, width, height), false)
})
