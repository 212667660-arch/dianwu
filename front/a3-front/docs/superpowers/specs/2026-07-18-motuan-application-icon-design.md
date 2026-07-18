# 墨团应用图标设计

## 目标

将 Windows 主程序、安装器、卸载器、桌面与开始菜单快捷方式以及运行中的主窗口图标统一为项目内置角色“墨团”，同时保持现有托盘小图标不变。

## 方案

以 `electron/pets/motuan/spritesheet.webp` 的 idle 动画首帧作为唯一形象来源。首帧尺寸为 192×208，裁切后按比例居中到透明 512×512 画布，保留完整身体、书页和右侧小挂件，不新增文字、描边或外部素材。由该主图生成包含 16、24、32、48、64、128、256 像素图层的 `app-icon.ico`，保证资源管理器、任务栏和快捷方式在不同缩放下均可用。

## Electron 接入

- `build.win.icon` 指向 `electron/assets/app-icon.ico`。
- 恢复 Electron Builder 的 Windows 可执行文件资源编辑，使墨团图标写入最终 EXE。
- NSIS 的安装器和卸载器图标显式指向同一 ICO；快捷方式继承主程序图标。
- 主 `BrowserWindow` 显式使用 `electron/assets/app-icon.png`，开发模式和 unpacked 运行时保持一致。
- 托盘继续使用经过小尺寸适配的 `tray-icon.png`。

## 验证

1. 配置测试先证明当前包缺少应用图标契约。
2. 生成后校验 PNG 为 512×512 RGBA、ICO 含完整尺寸集合且源自墨团首帧。
3. 运行 Electron/Node 全量测试、Vitest、类型检查和桌面构建。
4. 重新执行 `desktop:pack` 与 `desktop:dist`。
5. 从最终 EXE 提取关联图标并进行视觉检查；验证安装包版本、哈希、桌面生命周期与零残留进程。

## 边界

不更换墨团角色素材，不重绘品牌标志，不修改界面配色，不引入在线图像服务。代码签名仍是独立发布事项。
