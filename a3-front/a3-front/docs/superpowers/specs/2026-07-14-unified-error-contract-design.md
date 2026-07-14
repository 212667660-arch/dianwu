# T-029 统一错误响应契约设计

**日期：** 2026-07-14
**任务：** T-029 统一 FastAPI、Web 与 Electron 的错误响应契约
**状态：** 已确认，待实施计划

## 目标

让 A3 的所有 HTTP 非 2xx 响应（包括 `/health/ready` 的模型未配置 503）使用同一份安全、可解析的错误信封；Web 开发模式和 Electron 桌面模式均转换为相同的前端错误对象，并保留状态码、业务代码、重试语义和请求追踪标识。

成功响应、SSE 正常事件和已有桌面 IPC 的 `{ ok, status, data }` 外层结构保持不变。

## 固定 HTTP 错误信封

所有 HTTP 非 2xx 响应均返回 `application/json`：

```json
{
  "code": "SESSION_NOT_FOUND",
  "message": "会话不存在。",
  "retryable": false,
  "request_id": "4c8c1d..."
}
```

字段规则：

- `code`：稳定、全大写、下划线分隔的业务代码；前端按它分支，不能依赖中文文案或 FastAPI `detail`。
- `message`：可直接展示的中文安全文案；不能包含模型密钥、令牌、请求体、后端地址、文件路径、堆栈或 Pydantic 原始输入。
- `retryable`：仅在立即重试可能成功时为 `true`，例如本地服务暂不可用、模型超时和未预期服务故障。
- `request_id`：沿用请求的 `X-Request-ID`，否则生成 UUID；同时写入响应 `X-Request-ID` 头，供用户反馈问题时关联日志。

`/health/live` 和 `/health/ready` 成功时仍返回现有状态对象。模型未配置时，`/health/ready` 返回：

```json
{
  "code": "MODEL_NOT_READY",
  "message": "模型服务尚未配置。",
  "retryable": false,
  "request_id": "..."
}
```

HTTP 状态为 `503`。

## 后端映射

`backend/errors.py` 保留 `AppError` 作为唯一业务异常基类，并增加只表达安全语义的资源错误类型或构造器。路由不再直接抛出 `HTTPException` 处理预期的资源状态。

| 场景 | HTTP | `code` | `retryable` |
| --- | --- | --- | --- |
| 会话不存在 | 404 | `SESSION_NOT_FOUND` | `false` |
| 练习题不存在或不属于会话 | 404 | `QUESTION_NOT_FOUND` | `false` |
| 学习资源不存在 | 404 | `LEARNING_RESOURCE_NOT_FOUND` | `false` |
| 生成任务不存在、已结束或不属于会话 | 404 | `GENERATION_NOT_FOUND` | `false` |
| 路由/方法不存在 | 404/405 | `HTTP_NOT_FOUND` / `HTTP_METHOD_NOT_ALLOWED` | `false` |
| Pydantic 请求体、路径或查询参数校验失败 | 422 | `REQUEST_VALIDATION_ERROR` | `false` |
| 手动不支持格式或其他客户端输入错误 | 422 | `REQUEST_VALIDATION_ERROR` | `false` |
| 未配置模型的 readiness 检查 | 503 | `MODEL_NOT_READY` | `false` |
| 已有 `AppError` | 原状态 | 原业务 `code` | 原语义 |
| 未捕获异常 | 500 | `BACKEND_UNEXPECTED_ERROR` | `true` |

FastAPI 的 `RequestValidationError`、FastAPI/Starlette `HTTPException` 与 `Exception` 都在应用级 handler 转换；handler 只记录状态、代码、请求 ID、方法和路径。认证/限流中间件复用同一个错误响应构造器，不再重复组装 JSON。

SSE 已经通过 `error` 事件传递 `code` 和 `message`，本任务只要求保持该字段安全；HTTP 建流失败改用上述信封，并由 Web/Electron 转换为同一种前端错误对象。

## 前端与 Electron 边界

在 `src/api/transport.ts` 定义通用 `BackendApiError`：

```ts
class BackendApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryable: boolean
  readonly requestId?: string
}
```

`DesktopApiError` 作为兼容导出保留，现有调用方和测试不需要迁移名称。桌面 IPC 将后端的 `request_id` 继续转换为 `requestId`，其他字段原样保留。

Web transport 不再把 Axios 原始 `detail` 作为 UI 契约。普通请求和 fetch SSE 建流失败均解析固定信封并构造 `BackendApiError`；网络失败或非信封上游响应使用不泄露细节的本地兜底错误。`errorMessage()` 只展示该错误的安全 `message`，不再读取 `detail`。

Electron `backend-proxy` 继续独占令牌与动态后端地址；它仅转发符合固定信封的字段，不将任意上游 JSON、响应文本或网络错误详情传给 renderer。

## 测试与验收

后端测试覆盖：

1. 缺失会话、生成任务、资源和练习题分别返回对应 404 `code`。
2. 空消息、非法会话 ID、缺少必填查询参数和不支持导出格式均返回统一 422 `REQUEST_VALIDATION_ERROR`，没有 `detail`。
3. 未配置 `/health/ready` 返回 503 `MODEL_NOT_READY`。
4. 已有 `AppError`、认证和限流保留原业务代码，且所有错误都带请求 ID 头与正文。
5. 未捕获异常返回安全 500，不泄漏异常文本。

前端/Electron 测试覆盖：

1. Web 普通请求、Web SSE 建流失败和桌面请求把同一错误信封转换为相同的 `BackendApiError` 字段。
2. `errorMessage()` 不再依赖 `detail`，也不显示非信封响应或网络异常的内部内容。
3. Electron proxy 保留合法错误信封的 `code/message/retryable/requestId`，同时继续拒绝非 JSON、畸形 JSON 和敏感上游详情。

完成标准：后端完整测试、Electron Node 测试、Vitest、Web/desktop build 均退出码 0；Web 和 Electron 对同一 404、422、503 产生相同用户文案与代码。

## 非目标

- 不修改成功响应结构、学习业务流程或数据库模型。
- 不引入 RFC 7807 `problem+json` 的新字段体系，避免破坏现有桌面 IPC。
- 不改变 SSE 正常事件协议，不实现自动重试。
- 不新增账号、桌宠或远程后端能力。
