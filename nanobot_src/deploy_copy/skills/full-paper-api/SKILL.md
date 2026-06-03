---
name: full-paper-api
description: "医学文献全文 API 查询技能，通过 HTTP 接口从 InfoX-Med 全文 API 获取文献全文内容（标题、摘要、正文、中文翻译、PDF链接）。当用户需要通过 API 接口阅读论文全文、获取文献详细内容时触发此技能。"
---

# Full Paper API — 医学文献全文 API 查询

## 概述

通过 HTTP API 接口获取 InfoX-Med 医学文献全文内容。与 `full-paper-read` 直连数据库不同，本技能通过 FastAPI 服务间接查询，更安全，适合对外提供服务。

> **与 full-paper-read 的区别**：`full-paper-read` 直接连接 MongoDB 数据库查询；`full-paper-api` 通过 HTTP API 接口查询，不暴露数据库连接信息，更安全。

## API 服务地址

- **默认地址**：`http://60.205.166.229:9306`
- **启动命令**：`python <skill_directory>/../full-paper-read/main.py`（或 `uvicorn main:app --host 0.0.0.0 --port 8000`）

## 鉴权

所有 API 请求需要在 Header 中携带 `X-Token`，格式为 `32位hex|7位数字`，总长度 40 字符。

**示例 Token**：`e3f62087e126439aa12ad4637cf4f12b|1106970`

> 当前仅校验 token 格式（长度和模式），不验证 token 内容，便于调试。

## 调用方式

### 步骤 1：确定文献 doc_id

从以下来源获取 `doc_id`：
- **搜索结果**：通过 `medical-keyword-search` 或 `medical-pico-search` 搜索后，结果中的 `id` 字段即为 `doc_id`
- **用户提供**：用户直接给出 InfoX-Med 平台的文献 ID

### 步骤 2：调用 API 查询

#### 通过 doc_id 查询

```bash
curl -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
  "http://60.205.166.229:9306/api/v1/paper/doc-id/116"
```

#### 通过 MongoDB ObjectId 查询

```bash
curl -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
  "http://60.205.166.229:9306/api/v1/paper/object-id/507f1f77bcf86cd799439011"
```

#### 返回原始完整记录

```bash
curl -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
  "http://60.205.166.229:9306/api/v1/paper/doc-id/116?raw=true"
```

#### 健康检查

```bash
curl "http://60.205.166.229:9306/api/v1/health"
```

### 步骤 3：读取并分析全文

解析返回的 JSON 数据，根据用户需求进行：
- 全文内容展示与摘要
- 研究方法、结果、结论的结构化提取
- PICO 要素提取
- 关键发现总结
- 文献质量评估

## API 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/paper/doc-id/{doc_id}` | 通过 doc_id 查询全文 |
| GET | `/api/v1/paper/object-id/{object_id}` | 通过 MongoDB ObjectId 查询全文 |
| GET | `/api/v1/health` | 健康检查 |

## 请求参数

| 参数 | 位置 | 必选 | 说明 |
|------|------|------|------|
| `X-Token` | Header | 是 | 鉴权 token，格式：`32位hex\|7位数字` |
| `doc_id` | Path | 是（doc-id 接口） | 文献的 doc_id（整数） |
| `object_id` | Path | 是（object-id 接口） | MongoDB ObjectId 字符串 |
| `raw` | Query | 否 | 是否返回原始完整记录，默认 `false` |

## 返回结果格式

### 成功（200）

```json
{
  "code": 200,
  "msg": "查询到 1 条全文记录",
  "data": [
    {
      "_id": "116",
      "doc_id": 116,
      "pmid": 27484016,
      "title": "文献标题",
      "abstract": "摘要内容",
      "full_text": "Markdown 格式英文全文...",
      "full_text_zh": "Markdown 格式中文翻译全文...",
      "pdf_url": "https://doc3.infox-med.com/xxx.pdf"
    }
  ]
}
```

### 未找到（404）

```json
{
  "code": 404,
  "msg": "未找到匹配的全文记录",
  "data": []
}
```

### Token 无效（401）

```json
{
  "detail": "无效的 token 格式，要求：32位hex|7位数字（总长度40字符）"
}
```

## 典型使用场景

### 场景 1：搜索后通过 API 阅读全文

```bash
curl -s -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
  "http://60.205.166.229:9306/api/v1/paper/doc-id/116" | python -m json.tool
```

### 场景 2：批量查询

```bash
for id in 116 220 335; do
  curl -s -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
    "http://60.205.166.229:9306/api/v1/paper/doc-id/$id" > "/tmp/paper_${id}.json"
done
```

## 启动服务

```bash
cd <skill_directory>/../full-paper-read
pip install fastapi uvicorn pymongo
python main.py
```

服务默认监听 `0.0.0.0:8000`，可通过 Swagger UI 查看接口文档：`http://60.205.166.229:9306/docs`

## 注意事项

1. 需要先启动 FastAPI 服务才能调用 API
2. 并非所有文献都有全文记录，若返回 404 表示该文献未收录全文
3. 全文内容以 Markdown 格式存储，包含英文原文 (`full_text`) 和中文翻译 (`full_text_zh`)
4. 全文内容可能较长（数万字符），注意接口响应体大小
5. Token 当前仅校验格式，不验证真实性
