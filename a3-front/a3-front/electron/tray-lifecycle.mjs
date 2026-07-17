export function mainWindowCloseAction({ isQuitting, hasTray }) {
  if (isQuitting) return 'allow'
  return hasTray ? 'hide' : 'quit'
}


export function showMainWindow(window) {
  if (!window || window.isDestroyed()) return false
  if (window.isMinimized()) window.restore()
  window.show()
  window.focus()
  return true
}


export function createTrayController({
  Tray,
  Menu,
  icon,
  getMainWindow,
  requestQuit,
}) {
  if (!icon || typeof icon.isEmpty !== 'function' || icon.isEmpty()) {
    throw new Error('Tray icon is empty.')
  }

  const tray = new Tray(icon)
  const show = () => showMainWindow(getMainWindow())
  const menuTemplate = [
    { label: '打开智学协作台', click: show },
    { type: 'separator' },
    { label: '退出智学协作台', click: requestQuit },
  ]
  const menu = Menu.buildFromTemplate(menuTemplate)
  let destroyed = false

  tray.setToolTip('智学协作台')
  tray.setContextMenu(menu)
  tray.on('click', show)
  tray.on('double-click', show)

  return {
    tray,
    menu,
    menuTemplate,
    show,
    destroy() {
      if (destroyed) return
      destroyed = true
      tray.destroy()
    },
  }
}
