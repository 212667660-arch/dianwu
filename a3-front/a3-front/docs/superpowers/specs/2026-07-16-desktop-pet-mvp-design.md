# A3 桌宠 MVP 设计

## 目标与范围

在现有 Electron 应用中增加一个独立、透明、无边框、置顶的桌宠窗口，读取固定规格的 `pet.json` 与 `spritesheet.webp`，支持拖动、位置记忆、九种动画、应用任务状态联动以及显示、缩放、速度设置。

本阶段优先交付可启动和可操作版本。全面许可证审计、完整逐帧视觉 QA、九状态人工语义核对、用户图形导入界面、语音鼓励和学习进度策略留到后续任务。本阶段只预留安全的自定义角色目录和状态协议，不提前实现上传或 TTS。

## 方案选择

采用独立 `BrowserWindow`，而不是主窗口内的悬浮组件。独立窗口才能在主应用最小化时继续显示，并正确实现透明、置顶、多显示器和桌面位置记忆。

桌宠由三个边界清晰的单元组成：

1. `pet-config.mjs`：验证角色清单、动画行、设置枚举和数值范围。
2. `pet-controller.mjs`：拥有窗口、设置文件、屏幕约束、任务状态和固定 IPC 行为。
3. `pet-renderer.js`：只负责加载精灵图、按清单播放帧、点击/双击和拖动交互；不接触应用令牌、模型配置或任意文件路径。

主 Vue renderer 只能通过固定 bridge 读取/更新桌宠设置和上报安全状态枚举。桌宠 renderer 使用单独 preload，只能读取启动数据、拖动和接收状态，不获得主应用 API 能力。

## 角色包契约

默认角色目录为 `electron/pets/motuan/`，包含：

```text
pet.json
spritesheet.webp
```

启动时优先检查 Electron userData 下的 `pets/current/`；两文件均合法才使用自定义角色，否则回退到打包的“墨团”。renderer 永远不能提交任意路径。

`pet.json` 保留 hatch-pet 的基本字段，并明确动画数据：

```json
{
  "id": "motuan",
  "displayName": "墨团",
  "description": "住在书页边缘的青墨学习精灵。",
  "spritesheetPath": "spritesheet.webp",
  "cell": { "width": 192, "height": 208 },
  "grid": { "columns": 8, "rows": 9 },
  "animations": {
    "idle": { "row": 0, "durations": [280, 110, 110, 140, 140, 320] }
  }
}
```

九个必需状态及行号固定为 `idle` 0、`running-right` 1、`running-left` 2、`waving` 3、`jumping` 4、`failed` 5、`waiting` 6、`running` 7、`review` 8。帧数和时长采用 hatch-pet 行映射。未使用单元格必须完全透明。

## 窗口、拖动与屏幕约束

窗口属性为 `transparent: true`、`frame: false`、`alwaysOnTop: true`、`skipTaskbar: true`、不可调整尺寸。尺寸由 `192×208×scale` 得到，缩放范围为 0.5–1.5。

Electron `screen` 坐标使用 DIP。控制器根据窗口中心选择最近显示器，并把位置约束到该显示器 `workArea`；启动、缩放、显示器增删和 DPI 指标变化时都会重新约束。位置原子保存到 userData 的 `pet-settings.json`。第一次启动放在主显示器右下安全边距内。

拖动由桌宠 renderer 捕获指针并通过专用 IPC 提交屏幕坐标。水平移动为正时播放 `running-right`，为负时播放 `running-left`；拖动结束后恢复当前任务状态。

## 状态与交互

主任务状态只接受 `idle | running | waiting | review | failed`。学习请求开始为 `running`，SSE 校验阶段为 `review`，成功完成后短暂 `waiting`，失败为 `failed`，随后回到 `idle`。知识导入和模型配置操作至少映射为 `running`，错误映射为 `failed`。

交互动画优先于任务状态：单击延迟确认后播放 `waving`，双击取消单击并播放 `jumping`，拖动播放方向动画。交互结束恢复主任务状态。

## 设置和资源占用

书桌面板中的桌宠卡片提供：显示/隐藏、0.5–1.5 缩放、0.5/0.75/1/1.25/1.5/2 倍动画速度。设置由主进程校验并持久化。

隐藏时窗口 `hide()`，renderer 收到不可见事件后停止动画循环。连续 60 秒没有交互且状态为 `idle` 时进入低活跃模式，只保留低频空闲动画；任务或交互会立即恢复正常。窗口保留 Electron 默认后台节流。

## 素材与许可证

默认“墨团”由项目本地脚本确定性生成，不使用 OpenAI、Codex 名称、Logo 或品牌素材。项目会复制 hatch-pet 的 Apache-2.0 `LICENSE.txt`、`validate_atlas.py` 和 `make_contact_sheet.py`，并在 `NOTICE.md` 说明来源、复制状态和本项目修改边界。原创生成脚本不声称来自上游。

## 测试与验收

- Node 单元测试：清单校验、设置范围、状态枚举、屏幕约束、位置保存、窗口属性、显示/隐藏/缩放/速度、拖动方向和 sender 隔离。
- Vitest：书桌卡片设置操作、主任务状态上报、学习流 `running/review/waiting/failed` 映射。
- 素材验证：`1536×1872`、8×9、192×208、所有已用格非空、未使用格透明、透明像素 RGB 清零。
- 桌面验收：开发版和 unpacked 版启动，窗口透明置顶、拖动后位置恢复、点击/双击可见、隐藏后可从主应用恢复、多屏约束无越界、退出无残留进程。

