import path from 'node:path'

import { PET_ANIMATION_SPECS, parsePetManifestText } from './pet-config.mjs'

const MANIFEST_LIMIT = 65_536
const ATLAS_LIMIT = 12 * 1024 * 1024
const ATLAS_WIDTH = 1536
const ATLAS_HEIGHT = 1872
const CELL_WIDTH = 192
const CELL_HEIGHT = 208
const MIN_USED_PIXELS = 50
const MAX_USED_PIXELS = CELL_WIDTH * CELL_HEIGHT * 0.95

export function validatePetAtlasBitmap(bitmap, width, height) {
  if (!bitmap || width !== ATLAS_WIDTH || height !== ATLAS_HEIGHT || bitmap.length !== width * height * 4) return false
  for (const spec of Object.values(PET_ANIMATION_SPECS)) {
    for (let column = 0; column < 8; column += 1) {
      const left = column * CELL_WIDTH
      const top = spec.row * CELL_HEIGHT
      let nontransparent = 0
      for (let y = top; y < top + CELL_HEIGHT; y += 1) {
        for (let x = left; x < left + CELL_WIDTH; x += 1) {
          const offset = (y * width + x) * 4
          const alpha = bitmap[offset + 3]
          if (alpha === 0 && (bitmap[offset] || bitmap[offset + 1] || bitmap[offset + 2])) return false
          if (alpha !== 0) nontransparent += 1
        }
      }
      const used = column < spec.durations.length
      if (used && (nontransparent < MIN_USED_PIXELS || nontransparent > MAX_USED_PIXELS)) return false
      if (!used && nontransparent !== 0) return false
    }
  }
  return true
}

export function createPetCharacterImporter({ fs, userDataDir, inspectAtlas, uniqueId = () => Date.now().toString(36) }) {
  const petsRoot = path.join(userDataDir, 'pets')
  const currentDir = path.join(petsRoot, 'current')

  async function importFromDirectory(sourceDir) {
    const sourceStat = await fs.lstat(sourceDir)
    if (!sourceStat.isDirectory() || sourceStat.isSymbolicLink()) throw new TypeError('Character source must be an ordinary directory.')
    await validateDirectory(sourceDir)
    await fs.mkdir(petsRoot, { recursive: true })
    const token = uniqueId()
    const staging = path.join(petsRoot, `.staging-${token}`)
    const backup = path.join(petsRoot, `.backup-${token}`)
    await fs.rm(staging, { recursive: true, force: true })
    await fs.mkdir(staging)
    try {
      await fs.copyFile(path.join(sourceDir, 'pet.json'), path.join(staging, 'pet.json'))
      await fs.copyFile(path.join(sourceDir, 'spritesheet.webp'), path.join(staging, 'spritesheet.webp'))
      const manifest = await validateDirectory(staging)
      const hasCurrent = await exists(currentDir)
      if (hasCurrent) await fs.rename(currentDir, backup)
      try {
        await fs.rename(staging, currentDir)
      } catch (error) {
        if (hasCurrent && await exists(backup)) await fs.rename(backup, currentDir)
        throw error
      }
      await fs.rm(backup, { recursive: true, force: true })
      return manifest
    } finally {
      await fs.rm(staging, { recursive: true, force: true })
    }
  }

  async function validateDirectory(directory) {
    const manifestPath = path.join(directory, 'pet.json')
    const atlasPath = path.join(directory, 'spritesheet.webp')
    const [manifestStat, atlasStat] = await Promise.all([fs.lstat(manifestPath), fs.lstat(atlasPath)])
    if (!manifestStat.isFile() || manifestStat.isSymbolicLink() || !atlasStat.isFile() || atlasStat.isSymbolicLink()) {
      throw new TypeError('Character files must be ordinary files.')
    }
    if (manifestStat.size > MANIFEST_LIMIT || atlasStat.size > ATLAS_LIMIT) throw new TypeError('Character file size exceeds the limit.')
    const manifest = parsePetManifestText(await fs.readFile(manifestPath, 'utf8'))
    if (manifest.spritesheetPath !== 'spritesheet.webp') throw new TypeError('Character atlas filename is invalid.')
    const atlas = await inspectAtlas(atlasPath)
    if (atlas?.width !== ATLAS_WIDTH || atlas?.height !== ATLAS_HEIGHT || atlas?.validTransparency !== true) {
      throw new TypeError('Character atlas geometry or transparency is invalid.')
    }
    return manifest
  }

  async function reset() {
    await fs.rm(currentDir, { recursive: true, force: true })
  }

  async function exists(target) {
    return fs.access(target).then(() => true).catch(() => false)
  }

  return { importFromDirectory, reset, currentDir }
}
