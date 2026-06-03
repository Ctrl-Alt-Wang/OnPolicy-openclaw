# Nanobot 部署与测试指南

本文档说明如何将 `hermes_model_chat` 分支部署到服务器，并测试 `/api/model/chat` 接口。

---

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Linux（Ubuntu 20.04+ 推荐） |
| Docker | 20.10+ |
| Docker Compose | V2（`docker compose` 命令） |
| Python | 3.10+（服务器上运行部署脚本和测试脚本） |
| Git | 2.x |
| 内存 | 建议 16GB+（每个用户容器约 2GB） |

---

## 2. 首次部署

### 2.1 拉取代码

```bash
mkdir -p /data/server/guo_data
cd /data/server/guo_data
git clone <仓库地址> nanobot
cd nanobot
git checkout hermes_model_chat
```

### 2.2 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，必须修改的项：

```bash
# JWT 签名密钥（生产环境必须修改）
JWT_SECRET=<随机强密钥>
# 生成方法: python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 管理员账号
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<你的密码>

# 至少配置一个 LLM API Key
DASHSCOPE_API_KEY=sk-xxx
# 或者
DEEPSEEK_API_KEY=sk-xxx
# 或者其他 provider...

# 默认模型
DEFAULT_MODEL=dashscope/qwen3-coder-plus

# 运行时后端（必须设为 hermes）
PLATFORM_DEDICATED_RUNTIME_BACKEND=hermes
```

> 完整的环境变量说明参见 `.env.example` 文件中的注释。

### 2.3 构建并启动

```bash
python3 deploy_docker.py \
  --host <服务器公网IP> \
  --relative-api
```

首次构建会拉取基础镜像并编译所有服务，大约需要 5-10 分钟。

构建完成后会显示：

```
==================================================
  OpenClaw 部署状态
==================================================
  用户前端:        http://<IP>:3080
  简化版前端:      http://<IP>:3082
  管理员前端:      http://<IP>:3081
  共享前端:        http://<IP>:3083
  platform网关:    http://<IP>:8080
==================================================
```

### 2.4 验证部署

```bash
# 检查所有容器是否运行
docker compose ps

# 测试 API 连通性
curl http://localhost:8080/api/ping
# 预期返回: {"message":"pong","service":"openclaw-platform"}
```

---

## 3. 后续更新部署

代码更新后，在服务器上执行：

```bash
cd /data/server/guo_data/nanobot
bash deploy.sh
```

`deploy.sh` 会自动执行：
1. 拉取 `hermes_model_chat` 分支最新代码
2. 重建并重启相关容器（gateway、frontend 等）

如果只需要重建特定服务：

```bash
# 只重建 gateway（修改了 platform 代码时）
python3 deploy_docker.py --rebuild gateway --host <IP> --relative-api --fast

# 只重建前端
python3 deploy_docker.py --rebuild frontend --host <IP> --relative-api --fast

# 重建 hermes 基础镜像（修改了 hermes-agent 代码时）
python3 deploy_docker.py --rebuild hermes,gateway --host <IP> --relative-api --fast
```

如果想临时部署其他分支：

```bash
BRANCH_NAME=openclaw_newfront bash deploy.sh
```

---

## 4. 服务架构

```
                    ┌─────────────────────┐
                    │   frontend (:3080)   │
                    │   manage   (:3081)   │
                    │   simple   (:3082)   │
                    │   share    (:3083)   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  gateway (:8080)     │
                    │  (platform/FastAPI)  │
                    │  - /api/auth/*       │
                    │  - /api/model/chat   │
                    │  - /api/admin/*      │
                    │  - /llm/v1/*         │
                    └──┬────────────┬──────┘
                       │            │
              ┌────────▼───┐  ┌────▼─────────────┐
              │  postgres   │  │ shared-openclaw   │
              │  (:15432)   │  │ (hermes共享实例)  │
              └─────────────┘  └──────────────────┘
                       │
          ┌────────────▼────────────────┐
          │  hermes-user-xxx (per-user) │
          │  hermes-user-yyy (per-user) │
          │  ...动态创建的用户容器...     │
          └─────────────────────────────┘
```

| 服务 | 端口 | 说明 |
|---|---|---|
| gateway | 8080 | API 网关，所有接口入口 |
| frontend | 3080 | 用户前端 |
| manage-front | 3081 | 管理员后台 |
| simple-front | 3082 | 简化版前端 |
| share-openclaw-front | 3083 | 共享前端 |
| postgres | 15432 | 数据库（外部访问端口） |
| shared-openclaw | 内部 | hermes 共享实例 |
| hermes-user-* | 动态 | 每用户独立 hermes 容器 |

---

## 5. 手动测试 model-chat 接口

### 5.1 登录获取 Token

```bash
TOKEN=$(curl -s -X POST "http://<IP>:8080/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<密码>"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

echo $TOKEN
```

### 5.2 单轮对话

```bash
curl -s -N -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "linkId": "t1",
    "sessionId": "s1",
    "messages": [{"role":"user","content":"你好"}],
    "type": 0
  }'
```

预期输出（SSE 流）：

```
data: {"linkId":"t1","sessionId":"s1","userId":1,"functionId":1,"message":"你","type":4,...}
data: {"linkId":"t1","sessionId":"s1","userId":1,"functionId":1,"message":"好","type":4,...}
data: {"linkId":"t1","sessionId":"s1","userId":1,"functionId":1,"message":"！","type":4,...}
...
data: {"linkId":"t1","sessionId":"s1","userId":1,"functionId":1,"message":"[stop]","reasoningMessage":"","type":4,...}
```

### 5.3 多轮对话

```bash
curl -s -N -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "linkId": "t2",
    "sessionId": "s1",
    "messages": [
      {"role":"user","content":"我叫小明"},
      {"role":"assistant","content":"你好小明！"},
      {"role":"user","content":"我叫什么名字？"}
    ],
    "type": 0
  }'
```

### 5.4 中止对话

```bash
# 终端1: 发起长任务
curl -s -N -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"linkId":"t3","sessionId":"s-abort","messages":[{"role":"user","content":"请写一篇3000字的文章"}],"type":0}'

# 终端2: 中止
curl -s -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"linkId":"t3","sessionId":"s-abort","type":-1}'
# 预期返回: {"linkId":"t3","sessionId":"s-abort","ok":true}
```

### 5.5 错误场景验证

```bash
# 无 Token → 401
curl -s -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -d '{"linkId":"t","sessionId":"s","messages":[{"role":"user","content":"hi"}],"type":0}'

# 空 messages → 400
curl -s -X POST "http://<IP>:8080/api/model/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"linkId":"t","sessionId":"s","messages":[],"type":0}'
```

---

## 6. 自动化测试脚本

项目提供了端到端测试脚本 `tests/test_model_chat_e2e.py`。

### 6.1 安装依赖

```bash
pip install aiohttp
```

### 6.2 运行完整测试套件

```bash
python3 tests/test_model_chat_e2e.py \
  --base-url http://<IP>:8080 \
  --username admin \
  --password <密码>
```

测试项：

| 编号 | 测试项 | 说明 |
|---|---|---|
| 1 | 登录 | 获取 JWT token |
| 2 | 用户信息 | 验证 /api/auth/me |
| 3 | 单轮对话 | SSE 流式输出 + [stop] |
| 4 | 多轮对话 | 带历史消息，验证上下文记忆 |
| 5 | 工具调用 | 触发 agent 工具调用事件 |
| 6 | 中止对话 | type=-1 中止进行中的任务 |
| 7 | API Token | 365 天长期 token 对话测试 |
| 8 | 错误场景 | 无 token / 空 messages / 无效 token / 缺字段 |
| 9 | 并发请求 | 多请求同时发送 |

输出示例：

```
============================================================
  测试结果汇总
============================================================
  [PASS] 登录 (0.12s)
  [PASS] 用户信息 (0.05s)
  [PASS] 单轮对话 (3.21s)
  [PASS] 多轮对话 (6.45s)
  [PASS] 工具调用 (12.30s)
  [PASS] 中止对话 (4.82s)
  [PASS] API Token (3.56s)
  [PASS] 无 Token 拒绝 (0.02s)
  [PASS] 空 messages 拒绝 (0.02s)
  [PASS] 无效 Token 拒绝 (0.02s)
  [PASS] 缺少字段拒绝 (0.02s)
  [PASS] 并发请求 (8.91s)

  12/12 通过
```

### 6.3 跳过耗时测试

```bash
python3 tests/test_model_chat_e2e.py \
  --base-url http://<IP>:8080 \
  --username admin --password <密码> \
  --skip-tool --skip-abort
```

### 6.4 并发压测模式

```bash
# 10 个用户并发请求
python3 tests/test_model_chat_e2e.py \
  --base-url http://<IP>:8080 \
  --username admin --password <密码> \
  --stress -c 10

# 打印每个请求的返回内容
python3 tests/test_model_chat_e2e.py \
  --base-url http://<IP>:8080 \
  --username admin --password <密码> \
  --stress -c 5 -p

# 自定义 prompt
python3 tests/test_model_chat_e2e.py \
  --base-url http://<IP>:8080 \
  --username admin --password <密码> \
  --stress -c 10 --prompt "写一段快排代码"
```

压测报告示例：

```
============================================================
                    并发测试报告
============================================================
  总请求数:  10
  成功:      10
  失败:      0
  成功率:    100.00%
  平均耗时:  4.523s (min=2.113s, max=8.921s)
  首token:   1.234s (min=0.891s, max=2.341s)
============================================================
```

---

## 7. 常见问题

### Q: 首次请求返回 [stop] 没有内容

**原因**: 用户的 hermes 容器刚创建，API Server 还未完全启动。

**解决**: 等待 10-15 秒后重试。后续请求会复用已启动的容器，不会再出现。

### Q: "All connection attempts failed" 错误

检查:
1. 确认 `PLATFORM_DEDICATED_RUNTIME_BACKEND=hermes`（不是 `openclaw`）
2. 删除旧容器重试: `docker rm -f hermes-user-<用户ID前8位>`
3. 检查容器日志: `docker logs hermes-user-<ID> --tail 30`

### Q: 如何确认用户的 runtime_mode

```bash
TOKEN=<用户token>
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/auth/me | python3 -m json.tool
```

确认 `runtime_mode` 字段为 `"dedicated"`。

### Q: 如何查看用户容器状态

```bash
# 列出所有用户容器
docker ps | grep hermes-user

# 查看特定容器日志
docker logs hermes-user-<ID> --tail 50

# 查看容器网络 IP
docker inspect hermes-user-<ID> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

### Q: 如何从数据库查看容器记录

```bash
docker exec openclaw-gateway python3 -c "
import asyncio
async def check():
    from app.db.engine import async_session
    from app.db.models import Container
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(select(Container))
        for c in result.scalars():
            print(f'user={c.user_id[:8]} host={c.internal_host} port={c.internal_port} status={c.status}')
asyncio.run(check())
"
```

### Q: API rate limit 错误

这是 LLM 服务商（如 DeepSeek）的限流，不是平台的配额限制。解决方案:
- 等待一段时间后重试
- 换用其他 LLM provider
- 联系服务商提升限额

---

## 8. 相关文档

| 文档 | 说明 |
|---|---|
| `doc/model_chat_api.md` | Model Chat API 接口详细文档 |
| `.env.example` | 环境变量完整说明 |
| `doc/struct.md` | 项目结构说明 |
| `doc/hermes_plan.md` | Hermes 架构设计 |
