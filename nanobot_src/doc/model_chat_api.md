# Model Chat API 接口文档

## 概述

`POST /api/model/chat` 是一个 SSE（Server-Sent Events）流式对话接口，运行在 platform 层（Python/FastAPI），对接 hermes agent。

每个用户拥有独立的 hermes 容器（dedicated 模式），首次请求时自动创建，后续请求复用。

---

## 1. 认证

所有接口请求需要在 Header 中携带 JWT token：

```
Authorization: Bearer <token>
```

### 1.1 登录获取 token

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "用户名",
  "password": "密码"
}
```

返回：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user_id": "81e807e0-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "username": "yangge",
  "role": "user"
}
```

- `access_token`：有效期 24 小时，用于所有 API 请求
- `refresh_token`：有效期 30 天，用于刷新 access_token

### 1.2 刷新 token

access_token 过期后，使用 refresh_token 获取新 token：

```http
POST /api/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

返回格式与登录相同。

### 1.3 长期 API Token（推荐）

如果不想频繁刷新 token，可以生成一个 365 天有效的 API Token：

```http
POST /api/auth/api-token
Authorization: Bearer <access_token>
```

返回：

```json
{
  "api_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in_days": 365
}
```

后续请求中直接使用 `api_token` 作为 Bearer token 即可。

---

## 2. 对话接口

### 2.1 发送消息（SSE 流式）

```http
POST /api/model/chat
Content-Type: application/json
Authorization: Bearer <token>
```

#### 请求体

```json
{
  "linkId": "req-001",
  "sessionId": "session-001",
  "userId": 1,
  "functionId": 1,
  "messages": [
    {"role": "system", "content": "你是一个医学助手"},
    {"role": "user", "content": "高血压的最新治疗方案有哪些？"}
  ],
  "type": 0,
  "attachment": {},
  "callTools": true,
  "XAPIVersion": 1
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| linkId | string | 是 | - | 请求唯一标识，用于关联请求和响应 |
| sessionId | string | 是 | - | 会话 ID，同一 sessionId 表示同一轮对话 |
| userId | int | 否 | 1 | 用户 ID（业务层面） |
| functionId | int | 否 | 1 | 功能 ID |
| messages | array | 是 | [] | 消息数组，不能为空 |
| type | int | 否 | 0 | `0` = 正常对话，`-1` = 中止对话 |
| attachment | object | 否 | {} | 附件信息 |
| callTools | bool | 否 | true | 是否允许 agent 调用工具 |
| XAPIVersion | int | 否 | 1 | API 版本号 |

#### messages 格式

```json
[
  {"role": "system", "content": "系统提示词"},
  {"role": "user", "content": "用户消息"},
  {"role": "assistant", "content": "AI 之前的回复"},
  {"role": "user", "content": "用户新消息"}
]
```

- `role` 可选值：`system`、`user`、`assistant`、`tool`
- 多轮对话时，把完整的历史消息按顺序放入 messages 数组
- 最后一条 `user` 消息作为本次提问内容，其余作为上下文

### 2.2 SSE 响应格式

返回 `Content-Type: text/event-stream`，每条消息格式：

```
data: {"linkId":"req-001","sessionId":"session-001","userId":1,"functionId":1,"message":"...","reasoningMessage":"...","type":4,"attachment":{},"XAPIVersion":1}\n\n
```

#### 响应字段

| 字段 | 说明 |
|---|---|
| message | 最终结果文本（增量输出，带打字机效果） |
| reasoningMessage | 思考过程（工具调用、推理等），展示在思考区域 |
| type | 固定为 `4`（SSE 流式消息） |
| attachment | 附加信息，工具事件时包含 `agentEvent` 详情 |

#### 消息类型判断

| 条件 | 含义 | 前端处理 |
|---|---|---|
| `message` 有内容且不是 `[stop]` | 正文文本增量 | 追加到正文显示区 |
| `reasoningMessage` 有内容 | 思考/工具调用过程 | 追加到思考区域 |
| `message == "[stop]"` | **结束信号** | 关闭连接，对话结束 |

#### 事件映射关系

| Hermes 事件 | 输出字段 | 说明 |
|---|---|---|
| `tool.started` | `reasoningMessage: "[工具] 调用: xxx"` | agent 开始调用工具 |
| `tool.completed` | `reasoningMessage: "[工具] 完成: xxx"` | 工具调用完成 |
| `reasoning.available` | `reasoningMessage: "思考内容"` | agent 推理过程 |
| `message.delta` | `message: "增量文本"` | 最终结果，逐字输出 |
| `run.completed` / `run.failed` | `message: "[stop]"` | 结束信号 |

### 2.3 SSE 流示例

```
data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"","reasoningMessage":"[工具] 调用: search","type":4,"attachment":{"agentEvent":{"event":"tool.started","tool":"search"}},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"","reasoningMessage":"[工具] 完成: search","type":4,"attachment":{"agentEvent":{"event":"tool.completed","tool":"search"}},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"高","type":4,"attachment":{},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"血","type":4,"attachment":{},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"压","type":4,"attachment":{},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"的治疗方案包括","type":4,"attachment":{},"XAPIVersion":1}

data: {"linkId":"req-001","sessionId":"s1","userId":1,"functionId":1,"message":"[stop]","reasoningMessage":"","type":4,"attachment":{},"XAPIVersion":1}
```

### 2.4 中止对话

发送 `type: -1` 中止当前正在进行的对话：

```http
POST /api/model/chat
Content-Type: application/json
Authorization: Bearer <token>

{
  "linkId": "req-001",
  "sessionId": "session-001",
  "type": -1
}
```

返回 JSON（非 SSE）：

```json
{
  "linkId": "req-001",
  "sessionId": "session-001",
  "ok": true
}
```

---

## 3. 多轮对话

多轮对话通过在 `messages` 中传递完整历史实现：

**第一轮：**

```json
{
  "linkId": "req-001",
  "sessionId": "session-001",
  "messages": [
    {"role": "user", "content": "高血压有哪些分类？"}
  ],
  "type": 0
}
```

**第二轮：**

```json
{
  "linkId": "req-002",
  "sessionId": "session-001",
  "messages": [
    {"role": "user", "content": "高血压有哪些分类？"},
    {"role": "assistant", "content": "高血压主要分为原发性和继发性两大类..."},
    {"role": "user", "content": "继发性高血压的常见病因？"}
  ],
  "type": 0
}
```

注意：
- `sessionId` 保持不变表示同一轮对话
- `linkId` 每次请求使用新的唯一值
- 每次请求需要传递完整的对话历史

---

## 4. 容器机制

- 每个用户拥有独立的 hermes 容器（dedicated 模式）
- **首次请求**时自动创建容器，可能需要几秒钟启动时间
- 后续请求复用已有容器
- 容器被外部删除后，下次请求会自动重建
- 容器数据通过 Docker Volume 持久化

---

## 5. 错误处理

| HTTP 状态码 | 说明 |
|---|---|
| 200 | 成功，返回 SSE 流 |
| 400 | 请求参数错误（缺少 linkId/sessionId/messages） |
| 401 | 未认证或 token 过期 |
| 503 | hermes 容器不可用 |

SSE 流中如果 hermes 连接异常，会直接发送 `[stop]` 信号结束流：

```
data: {"linkId":"...","sessionId":"...","message":"[stop]","reasoningMessage":"","type":4}
```

---

## 6. 完整调用示例

### curl

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST "http://your-server:8080/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"yangge","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. 发送对话请求（SSE 流式）
curl -s -N -X POST "http://your-server:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "linkId": "q1",
    "sessionId": "test-001",
    "messages": [{"role":"user","content":"你好"}],
    "type": 0
  }'

# 3. 中止对话
curl -s -X POST "http://your-server:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"linkId":"q1","sessionId":"test-001","type":-1}'
```

### Python

```python
import requests
import json

BASE_URL = "http://your-server:8080"

# 1. 登录
resp = requests.post(f"{BASE_URL}/api/auth/login", json={
    "username": "yangge",
    "password": "your_password",
})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. SSE 流式对话
resp = requests.post(
    f"{BASE_URL}/api/model/chat",
    headers=headers,
    json={
        "linkId": "req-001",
        "sessionId": "session-001",
        "messages": [{"role": "user", "content": "你好"}],
        "type": 0,
    },
    stream=True,
)

full_text = ""
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data = json.loads(line[6:])
    msg = data.get("message", "")
    reasoning = data.get("reasoningMessage", "")

    if msg == "[stop]":
        print("\n--- 对话结束 ---")
        break
    if reasoning:
        print(f"[思考] {reasoning}")
    if msg:
        full_text += msg
        print(msg, end="", flush=True)

print(f"\n完整回复: {full_text}")
```

### JavaScript / Node.js

```javascript
const BASE_URL = "http://your-server:8080";

// 1. 登录
const loginResp = await fetch(`${BASE_URL}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "yangge", password: "your_password" }),
});
const { access_token } = await loginResp.json();

// 2. SSE 流式对话
const resp = await fetch(`${BASE_URL}/api/model/chat`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${access_token}`,
  },
  body: JSON.stringify({
    linkId: "req-001",
    sessionId: "session-001",
    messages: [{ role: "user", content: "你好" }],
    type: 0,
  }),
});

const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
let fullText = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop(); // 保留未完成的行

  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const data = JSON.parse(line.slice(6));

    if (data.message === "[stop]") {
      console.log("\n对话结束");
      return;
    }
    if (data.reasoningMessage) {
      console.log(`[思考] ${data.reasoningMessage}`);
    }
    if (data.message) {
      fullText += data.message;
      process.stdout.write(data.message);
    }
  }
}
```
