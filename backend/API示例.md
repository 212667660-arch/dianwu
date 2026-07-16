# API 请求响应示例

基础地址：`http://127.0.0.1:8000`

## 健康检查

```http
GET /health/live
```

响应：

```json
{"status":"live"}
```

## 普通对话

```http
POST /api/chat
Content-Type: application/json

{
  "session_id": "student_001",
  "message": "我想学习一次函数，希望掌握基础题"
}
```

首次响应示例：

```json
{
  "reply": "为了更准确地帮你制定学习计划，你目前最容易在哪一步出错？",
  "phase": "diagnosis",
  "state": "DIAGNOSING",
  "profile_version": 0
}
```

画像生成完成时，`phase` 为 `profile`，`state` 为 `PROFILED`。后续请求会返回 `phase=resource`。

## 画像接口

```http
POST /api/profile
Content-Type: application/json

{
  "messages": ["我想学习一次函数", "我在画图和求解析式时容易出错"]
}
```

响应：

```json
{"profile_text":"【协议:learner-profile/v1】\n...【协议结束】"}
```

## 资源接口

```http
POST /api/resource
Content-Type: application/json

{
  "profile_text": "【协议:learner-profile/v1】\n...【协议结束】",
  "message": "请生成一次函数基础笔记和三道分层练习题"
}
```

响应：

```json
{
  "resource_text":"【协议:learning-resource/v1】\n...【协议结束】",
  "sources":[{"title":"资料标题","url":"https://example.edu/resource","snippet":"公开资料摘要"}]
}
```

## SSE 流式对话

```http
POST /api/chat/stream
Content-Type: application/json
Accept: text/event-stream

{"session_id":"student_001","message":"请生成一次函数的基础练习"}
```

事件格式：

```text
 event: phase
 data: {"request_id":"...","generation_id":"...","phase":"resource"}

 event: delta
 data: {"request_id":"...","content":"【协议:learning-resource/v1】","provisional":true}

 event: sources
 data: {"request_id":"...","sources":[{"title":"资料标题","url":"https://example.edu/resource","snippet":"公开资料摘要"}],"cached":false}

 event: knowledge_sources
 data: {"request_id":"...","sources":[{"reference_id":"资料1","document_id":9,"document_name":"极限讲义.pdf","locator_label":"第 3 页","locator":{"type":"page","start":3,"end":3},"chunk_id":11,"retrieval_mode":"keyword"}],"cached":false}

 event: validation
 data: {"request_id":"...","valid":true,"repair_attempted":false,"error_code":null}

 event: persisted
 data: {"request_id":"...","resource_id":12}

 event: done
 data: {"request_id":"...","status":"completed","state":"PROFILED"}
```

客户端取消：`DELETE /api/generations/{generation_id}?session_id=student_001`。`session_id` 必须与发起该流式任务的会话一致；流中随后会收到 `CLIENT_CANCELLED` 错误事件和 `status=cancelled` 完成事件。

## 会话管理

- `GET /api/sessions/{session_id}`：读取画像、消息和资源。
- `POST /api/sessions/{session_id}/rediagnose`：重新开始诊断。
- `DELETE /api/sessions/{session_id}`：删除会话及关联数据。

## 学习进度与答题反馈

资源生成后，`GET /api/sessions/{session_id}` 的每个资源会返回 `questions`，其中包含可提交的题目 ID、序号、难度和题干。为兼容现有纯文本协议，资源的 `content` 仍包含完整答案和解析；正式学习界面可按答题阶段控制正文展示。

```http
POST /api/sessions/student_001/questions/12/attempts
Content-Type: application/json

{"answer":"1","hint_count":0,"idempotency_key":"attempt_001"}
```

响应包含判分、参考答案、解析、掌握度和下次复习时间。相同 `session_id + idempotency_key` 重复提交不会重复计分。

- `GET /api/sessions/{session_id}/progress`：读取知识点掌握度、正确率和学习状态版本。
- `GET /api/sessions/{session_id}/next-action`：根据到期复习、掌握度和答题历史返回下一步动作、目标知识点、建议难度和可直接提交的生成请求。
- `GET /api/sessions/{session_id}/reviews?due_only=true`：读取已到期复习任务；去掉参数可读取全部待复习任务。
- `GET /api/sessions/{session_id}/mistakes`：读取最近错题、学生答案、参考答案和解析。

答题后学习状态版本会递增，旧资源缓存自动失效；后续资源生成会携带低掌握度和近期错误摘要。

会话资源还会返回 `quality_score` 和 `quality_issues`。质量校验检查声明难度是否有对应题目、题量是否充足、题目是否重复及学习笔记是否过短；低于门槛的模型输出会自动修复一次。

## 学习资源导出

已生成并持久化的资源可直接导出，导出不会再次调用模型。

`GET /api/sessions/{session_id}/resources/{resource_id}/export?format=markdown`

`format` 支持 `markdown`（默认）和 `txt`。资源 ID 必须属于该会话，否则返回 `404`。若资源生成时使用了在线检索，导出内容会在正文后附上持久化的“参考来源”；会话历史、普通资源阶段响应和 SSE 的 `sources` 事件会返回同一份来源快照。

## 本地知识库

知识库接口只接收 Electron 主进程已经复制并校验的对象 manifest，不接收用户原路径，也不提供 multipart 文件上传。`object_relpath` 只能是与 SHA-256 一致的 `objects/<64 位小写十六进制>`；后端会再次检查对象大小与哈希。

```http
POST /api/knowledge/collections
Content-Type: application/json

{"name":"高数","description":"极限与导数","color":"#c98f65"}
```

集合还支持 `GET /api/knowledge/collections`、`PUT /api/knowledge/collections/{id}` 和 `DELETE /api/knowledge/collections/{id}`。删除集合不会直接删除仍被其他集合引用的对象。

```http
POST /api/knowledge/imports
Content-Type: application/json

{
  "collection_id": 3,
  "files": [
    {
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "display_name": "极限讲义.pdf",
      "extension": ".pdf",
      "mime_type": "application/pdf",
      "byte_size": 1024,
      "object_relpath": "objects/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
```

导入返回 `202` 和任务列表。`GET /api/knowledge/imports` 读取进度，`DELETE /api/knowledge/imports/{job_id}` 取消任务；`POST /api/knowledge/documents/{document_id}/rebuild` 重新解析，`DELETE /api/knowledge/documents/{document_id}` 删除文档及无引用对象。支持格式为 PDF、DOCX、PPTX、XLSX、TXT、Markdown 和 CSV；单文件不超过 100 MiB，一次最多 50 个文件和 500 MiB。

学习空间绑定：

```http
PUT /api/sessions/student_001/knowledge-collections
Content-Type: application/json

{"collection_ids":[3,4],"privacy_mode":"allow_model_context"}
```

`privacy_mode=allow_model_context` 允许把当前检索命中的少量片段作为不可信参考数据发送给模型；`local_search_only` 只允许本机搜索，不向模型发送片段。

```http
POST /api/knowledge/search
Content-Type: application/json

{"session_id":"student_001","query":"极限的直观定义","limit":8}
```

搜索只覆盖该会话已绑定的集合，返回 `keyword` 或 `hybrid` 模式、受控文档 ID、显示名、文本片段和 page/slide/sheet_rows/paragraph locator，不返回原始路径或对象路径。常见稳定错误码包括 `KNOWLEDGE_FILE_SIGNATURE_MISMATCH`、`KNOWLEDGE_ARCHIVE_UNSAFE`、`KNOWLEDGE_DOCUMENT_ENCRYPTED`、`KNOWLEDGE_PARSE_TIMEOUT`、`KNOWLEDGE_PARSE_FAILED`、`KNOWLEDGE_OCR_PACK_REQUIRED`、`KNOWLEDGE_INDEX_UNAVAILABLE` 和 `KNOWLEDGE_OBJECT_MISSING`。

## 错误响应

```json
{"code":"MODEL_TIMEOUT","message":"模型响应超时，请稍后重试。","retryable":true,"request_id":"a1b2c3"}
```

配置桌面令牌或使用生产模式时，高成本接口会按本地桌面客户端限流；达到上限返回 `429 REQUEST_RATE_LIMITED`，响应头 `Retry-After` 表示可重试的等待秒数。


## 本地模型设置

以下接口是 Web 开发模式和旧客户端的单配置兼容层。`GET` 返回当前运行时默认配置的脱敏视图，绝不返回完整 API Key；连接测试已经转接多配置运行时的统一测试器。开发模式配置 `DESKTOP_TOKEN` 后，以及生产模式下的全部业务接口，都必须携带匹配的 `X-A3-Desktop-Token` 请求头；生产模式还拒绝非 `127.0.0.1` 或 `::1` 的连接。`/health/live` 是唯一匿名健康检查接口。

```http
GET /api/settings/model
```

```http
PUT /api/settings/model
Content-Type: application/json

{
  "provider": "openai",
  "api_key": "仅在本机提交的密钥",
  "base_url": "https://api.deepseek.com",
  "model_name": "deepseek-v4-pro",
  "request_timeout_seconds": 60
}
```

Anthropic 格式 API 使用：

```json
{
  "provider": "anthropic",
  "api_key": "仅在本机提交的密钥",
  "base_url": "https://api.deepseek.com/anthropic",
  "model_name": "deepseek-v4-pro",
  "anthropic_version": "2023-06-01"
}
```

开发模式更新会原子写入 `.env`，并立即让后续模型请求使用新网关。生产模式拒绝后端明文写入密钥，必须由 Electron `safeStorage` 或 Windows Credential Manager 保存后在启动时注入。生产模式仅允许 HTTPS 公网网关；localhost、私网、链路本地地址和非标准端口会被拒绝。开发环境测试本地网关时，需要显式设置 `ALLOW_LOCAL_MODEL_GATEWAY=true`。

正式 Electron 多配置控制面为 `/internal/model-runtime/bootstrap`、`/internal/model-runtime/test`、`/internal/model-runtime/snapshot` 和 `/internal/model-runtime/status`。这些接口只供 Electron 主进程在 loopback 上携带短期桌面令牌调用，不属于公开 API；renderer、Web 客户端和第三方调用方不得直接访问。主进程只通过固定 IPC 传递经过白名单校验的配置字段，并在 `safeStorage` 中保存密文。

运行时默认最多尝试 3 次、最多使用 2 套配置。408、429、502、503、504、连接失败和超时可进入重试或备用；401、403、404 与参数/协议错误直接终止。上游 429 的数字 `Retry-After` 会限制在 300 秒内并同步为该配置的熔断冷却；等待会越过本次请求总截止时间时不会阻塞，而是直接尝试备用配置或返回失败。

## 在线公开资料检索

```http
POST /api/web/search
Content-Type: application/json

{"query":"一次函数 教学资料"}
```

成功响应：

```json
{
  "query":"一次函数 教学资料",
  "results":[
    {"title":"资料标题","url":"https://example.edu/resource","snippet":"公开资料摘要"}
  ]
}
```

资源生成接口默认启用在线检索；可显式关闭：

```json
{
  "profile_text":"【协议:learner-profile/v1】\n...【协议结束】",
  "message":"生成一次函数笔记和练习",
  "use_web_search": false
}
```

开启检索时，`POST /api/resource` 会额外返回 `sources`。搜索源按搜狗、DuckDuckGo、Bing 的固定顺序回退；在线检索不可用时，直接搜索接口返回 `WEB_SEARCH_UNAVAILABLE`；资源生成接口会降级为无来源生成并返回空 `sources`。
## 模型配置连通性检测

在保存模型配置前，可用候选配置发起一次最小模型请求。该请求不会写入 `.env`，也不会返回模型完整回答或密钥。权限规则与模型设置接口相同。

`POST /api/settings/model/test`

请求体与 `PUT /api/settings/model` 相同；成功响应示例：

```json
{"provider":"openai","model_name":"deepseek-v4-pro","status":"connected","latency_ms":326}
```

该响应只包含供应商、模型名、连接状态和安全延迟，不包含测试回复正文、API Key 或完整运行时配置。

## 缓存行为

资源阶段中，若同一会话、同一画像版本和相同 `message` 在缓存有效期内已有成功资源，`POST /api/chat` 会返回 `"cached": true`；`POST /api/chat/stream` 会先发送 `cache` 事件，再发送完整的非暂存 `delta`。
