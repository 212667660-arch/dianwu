# A3 Desktop Pet MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在智学协作台中交付可启动、透明置顶、可拖动、可交互并能跟随任务状态的桌宠 MVP。

**Architecture:** Electron 主进程新增纯逻辑配置模块和窗口控制器；桌宠使用独立 sandbox renderer/preload；主 Vue renderer 只通过固定 IPC 管理设置和上报任务状态。默认角色为本地脚本生成的原创 8×9 WebP atlas，自定义角色目录只由主进程解析。

**Tech Stack:** Electron 32、Node test runner、Vue 3、Pinia、Vitest、Python Pillow、Apache-2.0 hatch-pet 校验脚本。

---

### Task 1: 角色清单、设置和屏幕约束纯逻辑

**Files:**
- Create: `electron/pet-config.mjs`
- Create: `electron/pet-config.test.mjs`
- Modify: `package.json`

- [ ] 写失败测试，覆盖九状态固定行号、帧数、相对 spritesheet 路径、缩放/速度枚举、非法额外字段，以及把窗口矩形约束到包含负坐标的显示器 workArea。
- [ ] 运行 `E:\Node\node.exe --test electron/pet-config.test.mjs`，确认模块不存在或导出缺失导致失败。
- [ ] 实现 `validatePetManifest`、`validatePetSettingsPatch`、`clampPetBounds`、`defaultPetBounds` 和固定常量；拒绝绝对路径、路径穿越、非有限数值和未知状态。
- [ ] 重跑聚焦测试并确认通过。

### Task 2: 设置持久化与桌宠控制器

**Files:**
- Create: `electron/pet-controller.mjs`
- Create: `electron/pet-controller.test.mjs`

- [ ] 写失败测试，使用临时目录和 fake BrowserWindow/screen，覆盖原子设置保存、默认/自定义角色回退、透明无边框置顶窗口选项、显示/隐藏、缩放重算、位置保存、显示器变化约束、任务状态广播、拖动方向和不可信 sender 拒绝。
- [ ] 运行聚焦测试，确认控制器不存在导致失败。
- [ ] 实现 `createPetController`，依赖注入 `BrowserWindow`、`screen`、`fs`、`userDataDir`、`packagedPetDir`、`petPreload` 和 `petIndex`，不在模块内访问全局 Electron 状态。
- [ ] 重跑聚焦测试并确认通过。

### Task 3: 原创素材和 hatch-pet 校验工具

**Files:**
- Create: `tools/pet/generate_motuan.py`
- Create: `tools/pet/third_party/hatch-pet/LICENSE.txt`
- Create: `tools/pet/third_party/hatch-pet/NOTICE.md`
- Create: `tools/pet/third_party/hatch-pet/validate_atlas.py`
- Create: `tools/pet/third_party/hatch-pet/make_contact_sheet.py`
- Create: `electron/pets/motuan/pet.json`
- Create: `electron/pets/motuan/spritesheet.webp`

- [ ] 复制上游 Apache-2.0 LICENSE、未修改校验脚本和联系表脚本；NOTICE 记录来源 URL、上游提交、未修改文件和本项目原创文件。
- [ ] 实现 Pillow 生成器，按固定行数绘制“墨团”的呼吸、左右移动、挥手、跳跃、失败、等待、工作和检查帧；透明像素清零，未使用格不绘制。
- [ ] 运行生成器得到 `pet.json` 和 lossless WebP。
- [ ] 运行上游 `validate_atlas.py` 与 `make_contact_sheet.py`，确认 atlas 几何和透明约束通过；仅进行 MVP 联系表检查，不宣称完成全面视觉 QA。

### Task 4: 独立桌宠 renderer 与交互

**Files:**
- Create: `electron/pet/index.html`
- Create: `electron/pet/pet.css`
- Create: `electron/pet/pet-renderer.js`
- Create: `electron/pet-preload.cjs`
- Create: `electron/pet-renderer.test.mjs`

- [ ] 写失败测试，抽出并覆盖帧推进、速度换算、任务/交互状态优先级、单击延迟、双击取消、拖动方向和 60 秒低活跃判断。
- [ ] 实现无 Node 权限的 canvas renderer；按 DPR 绘制 192×208 源格，隐藏时停止 RAF，idle 长时间无交互时降低频率。
- [ ] pet preload 仅暴露 `ready/beginDrag/moveDrag/endDrag/onState/onSettings`，不暴露通用 ipcRenderer。
- [ ] 重跑 renderer 测试。

### Task 5: 主进程接线、固定 IPC 与打包契约

**Files:**
- Modify: `electron/main.mjs`
- Modify: `electron/preload.cjs`
- Modify: `electron/ipc-contract.mjs`
- Modify: `electron/ipc-contract.test.mjs`
- Modify: `electron/runtime.test.mjs`
- Modify: `package.json`

- [ ] 先扩展测试，要求主 preload 只新增固定桌宠方法，main 创建控制器、应用启动后创建宠物窗口、退出时销毁，并拒绝 renderer 任意路径/状态/数值。
- [ ] 把 controller 接入 `app.whenReady`、`display-added/removed/display-metrics-changed`、before-quit 和固定 IPC。
- [ ] test mode 默认创建但不显示桌宠，避免破坏现有退出验收；打包 `electron/**` 自动包含 renderer 和默认角色。
- [ ] 运行所有 Electron Node 测试。

### Task 6: Vue 设置卡片与任务状态联动

**Files:**
- Create: `src/components/pet/PetSettingsCard.vue`
- Create: `src/components/pet/PetSettingsCard.test.ts`
- Create: `src/pet/task-state.ts`
- Create: `src/pet/task-state.test.ts`
- Modify: `src/components/workspace/DeskPanel.vue`
- Modify: `src/components/workspace/DeskPanel.test.ts`
- Modify: `src/layouts/AppLayout.vue`
- Modify: `src/views/SmartTutor.vue`
- Modify: `src/views/SmartTutor.test.ts`
- Modify: `src/api/types.ts`
- Modify: `src/api/transport.ts`
- Modify: `src/api/backend.ts`

- [ ] 写失败 Vitest：设置卡片读取/显示/缩放/速度；Web 模式安全降级；状态协调器处理嵌套任务与失败定时恢复；SmartTutor 开始为 running、validation 为 review、成功为 waiting、异常为 failed。
- [ ] 实现 typed bridge/API 和桌宠设置卡片，替换现有“桌宠功能预留”。
- [ ] 实现 renderer 状态协调器；AppLayout 映射全局 loading/model/knowledge busy，SmartTutor 映射细粒度生成状态。
- [ ] 运行聚焦 Vitest 与完整 `npm test`。

### Task 7: 桌面构建、运行验收与文档

**Files:**
- Modify: `README.md`
- Modify: `a3-front/a3-front/src/api/README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] 更新启动、显示/隐藏、素材替换、用户自定义目录、九状态、资源节流和许可证说明。
- [ ] 运行 `npm run build:desktop` 和 `npm run desktop:pack`。
- [ ] 使用隔离 userData 启动 unpacked：确认主窗口和桌宠窗口加载、设置持久化、拖动后位置恢复、隐藏/恢复、缩放、状态切换和退出无残留。
- [ ] 重跑 atlas 校验、密钥/令牌/任意路径扫描与 `git diff --check`。
- [ ] 更新队列，将本阶段完成项与明确暂缓项分开记录并独立提交；不 merge、不 push。

