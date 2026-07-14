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

## 错误响应

```json
{"code":"MODEL_TIMEOUT","message":"模型响应超时，请稍后重试。","retryable":true,"request_id":"a1b2c3"}
```

配置桌面令牌或使用生产模式时，高成本接口会按本地桌面客户端限流；达到上限返回 `429 REQUEST_RATE_LIMITED`，响应头 `Retry-After` 表示可重试的等待秒数。


## 本地模型设置

桌面端可调用以下接口读取或更新本机模型配置。读取接口不会返回完整 API Key，只会返回脱敏提示。开发模式配置 `DESKTOP_TOKEN` 后，以及生产模式下的全部业务接口，都必须携带匹配的 `X-A3-Desktop-Token` 请求头；生产模式还拒绝非 `127.0.0.1` 或 `::1` 的连接。`/health/live` 是唯一匿名健康检查接口。

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

## 缓存行为

资源阶段中，若同一会话、同一画像版本和相同 `message` 在缓存有效期内已有成功资源，`POST /api/chat` 会返回 `"cached": true`；`POST /api/chat/stream` 会先发送 `cache` 事件，再发送完整的非暂存 `delta`。
