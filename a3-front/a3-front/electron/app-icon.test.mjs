import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const projectDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const packageJson = JSON.parse(fs.readFileSync(path.join(projectDir, 'package.json'), 'utf8'))
const mainSource = fs.readFileSync(path.join(projectDir, 'electron', 'main.mjs'), 'utf8')
const pngPath = path.join(projectDir, 'electron', 'assets', 'app-icon.png')
const icoPath = path.join(projectDir, 'electron', 'assets', 'app-icon.ico')

test('Windows executable and NSIS use the Motuan application icon', () => {
  assert.equal(packageJson.build.win.icon, 'electron/assets/app-icon.ico')
  assert.notEqual(packageJson.build.win.signAndEditExecutable, false)
  assert.equal(packageJson.build.nsis.installerIcon, 'electron/assets/app-icon.ico')
  assert.equal(packageJson.build.nsis.uninstallerIcon, 'electron/assets/app-icon.ico')
})

test('main BrowserWindow uses the Motuan application icon at runtime', () => {
  assert.match(mainSource, /icon:\s*path\.join\(mainDir,\s*'assets',\s*'app-icon\.png'\)/)
})

test('Motuan icon assets provide a 512px RGBA source and complete Windows sizes', () => {
  assert.ok(fs.existsSync(pngPath), 'app-icon.png must exist')
  assert.ok(fs.existsSync(icoPath), 'app-icon.ico must exist')

  const png = fs.readFileSync(pngPath)
  assert.deepEqual([...png.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10])
  assert.equal(png.toString('ascii', 12, 16), 'IHDR')
  assert.equal(png.readUInt32BE(16), 512)
  assert.equal(png.readUInt32BE(20), 512)
  assert.equal(png[25], 6, 'PNG must use RGBA color type')

  const ico = fs.readFileSync(icoPath)
  assert.equal(ico.readUInt16LE(0), 0)
  assert.equal(ico.readUInt16LE(2), 1)
  const count = ico.readUInt16LE(4)
  const sizes = []
  for (let index = 0; index < count; index += 1) {
    const width = ico[6 + index * 16] || 256
    const height = ico[7 + index * 16] || 256
    assert.equal(width, height)
    sizes.push(width)
  }
  assert.deepEqual(sizes, [16, 24, 32, 48, 64, 128, 256])
})

test('the standard desktop test command includes the icon contract', () => {
  assert.match(packageJson.scripts.test, /electron\/app-icon\.test\.mjs/)
})
