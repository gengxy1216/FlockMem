# API Reference 📡

> Complete API documentation for MiniMem

## Base URL

```
http://127.0.0.1:20195
```

## Authentication 🔐

All API endpoints (except `/health`) require Basic Auth:

```
Username: admin
Password: admin123
```

---

## Endpoints

### Health

#### Get Health Status

```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

### Memories

#### Store Memory

```
POST /api/v1/memories
```

`Content-Type` 必须是 `application/json`，若携带 `charset` 参数则必须为 `utf-8`（否则返回 `415`）。

**Request Body:**
```json
{
  "message_id": "msg-001",
  "create_time": 1735603201,
  "sender": "zhangsan",
  "content": "用户消息内容",
  "group_id": "default:zhangsan",
  "group_name": "默认分组",
  "sender_name": "张三",
  "role": "user"
}
```

**Required fields:**
- `message_id`
- `create_time` (Unix 秒级时间戳或 ISO8601 字符串)
- `sender`
- `content`

**Response:**
```json
{
  "status": "ok",
  "message": "memory written",
  "result": {
    "success": true,
    "message_id": "msg-001",
    "sender": "zhangsan",
    "group_id": "default:zhangsan",
    "event_id": "d5f1a8...",
    "write_time": 1735603201,
    "summary": "摘要",
    "importance_score": 0.78,
    "memory": {
      "id": "c4ac1f...",
      "episode": "用户消息内容",
      "summary": "摘要"
    }
  },
  "request_id": "a8b3..."
}
```

#### Search Memories

```
GET /api/v1/memories/search?query=your+search+query&top_k=10
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search query |
| `user_id` | string | - | User scope |
| `group_id` | string | - | Group scope, empty means all groups |
| `retrieve_method` | string | `keyword` | `keyword` / `vector` / `hybrid` / `rrf` / `agentic` |
| `decision_mode` | string | `static` | `static` / `rule` / `agent` |
| `top_k` | int | `20` | Max results (1-100) |

**Response:**
```json
{
  "status": "ok",
  "result": {
    "memories": [
      {
        "id": "c4ac1f...",
        "event_id": "d5f1a8...",
        "group_id": "default:zhangsan",
        "content": "原始记忆内容（统一字段）",
        "episode": "原始记忆内容",
        "summary": "摘要",
        "score": 0.95,
        "source": "keyword"
      }
    ],
    "effective_policy": {},
    "conflicts": [],
    "profile": null
  }
}
```

#### List Memory Groups

```
GET /api/v1/memories/groups?user_id=zhangsan&limit=100
```

**Response:**
```json
{
  "status": "ok",
  "result": {
    "groups": [
      {
        "group_id": "default:zhangsan",
        "memory_count": 42,
        "last_timestamp": 1735603300
      }
    ],
    "total_count": 1,
    "has_more": false
  }
}
```

---

### Ingest

#### Ingest Skill Output (Normalized Contract)

```
POST /api/v1/ingest/skill
```

用于接收上游 Agent/Skill 已解析的结构化内容，统一契约字段：
`agent_id/sender/group_id/task_id/channel/trace_id`。

**Request Body:**
```json
{
  "source_type": "pdf",
  "source_uri": "file:///tmp/demo.pdf",
  "summary": "文档摘要",
  "chunks": ["段落1", "段落2"],
  "metadata": {"lang": "zh"},
  "skill_name": "pdf",
  "skill_version": "1.0.0",
  "agent_id": "agent-a",
  "sender": "agent-a",
  "group_id": "default:agent-a",
  "task_id": "task-001",
  "channel": "channel-a",
  "trace_id": "trace-001",
  "role": "user",
  "create_time": 1735603201
}
```

**Response (`accepted=true`):**
```json
{
  "status": "ok",
  "message": "skill ingest completed",
  "result": {
    "accepted": true,
    "skill_name": "pdf",
    "trace_id": "trace-001",
    "sender": "agent-a",
    "group_id": "default:agent-a",
    "ingested_count": 2,
    "event_ids": ["evt-1", "evt-2"],
    "source_type": "pdf"
  }
}
```

**Response (`accepted=false`, 非阻断提示):**
```json
{
  "status": "ok",
  "message": "skill is not in whitelist",
  "result": {
    "accepted": false,
    "hint": "allowed skills: markitdown, pdf, pptx",
    "skill_name": "unknown-skill",
    "trace_id": "trace-abc"
  }
}
```

---

### Chat

#### Simple Chat

```
POST /api/v1/chat/simple
```

**Request Body:**
```json
{
  "message": "What do you remember about our previous conversation?",
  "conversation_id": "conv_123"
}
```

**Response:**
```json
{
  "response": "Based on our previous conversation...",
  "citations": [
    {
      "memory_id": "mem_abc123",
      "content": "Previous conversation context",
      "score": 0.92
    }
  ]
}
```

---

### Graph

#### Search Graph

```
GET /api/v1/graph/search?entity=person&limit=10
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity` | string | required | Entity name to search |
| `limit` | int | 10 | Max results |

**Response:**
```json
{
  "nodes": [
    {
      "id": "node_1",
      "type": "person",
      "name": "John"
    }
  ],
  "edges": [
    {
      "from": "node_1",
      "to": "node_2",
      "type": "knows"
    }
  ]
}
```

#### Get Neighbors

```
GET /api/v1/graph/neighbors?node_id=node_1&depth=2
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `node_id` | string | required | Starting node ID |
| `depth` | int | 1 | Search depth |

---

### Model Config

#### Get Configuration

```
GET /api/v1/model-config
```

**Response:**
```json
{
  "chat_provider": "openai",
  "chat_model": "gpt-4o-mini",
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-small",
  "graph_enabled": true
}
```

#### Update Configuration

```
PUT /api/v1/model-config
```

**Request Body:**
```json
{
  "chat_provider": "openai",
  "chat_model": "gpt-4o-mini"
}
```

#### Test Connectivity

```
POST /api/v1/model-config/test
```

**Response:**
```json
{
  "chat": {
    "status": "ok",
    "latency_ms": 150
  },
  "embedding": {
    "status": "ok",
    "latency_ms": 80
  }
}
```

---

### Conversation Meta

#### List Conversations

```
GET /api/v1/conversations
```

**Response:**
```json
{
  "conversations": [
    {
      "id": "conv_123",
      "title": "Chat about Python",
      "created_at": "2024-01-01T12:00:00Z",
      "message_count": 10
    }
  ]
}
```

#### Delete Conversation

```
DELETE /api/v1/conversations/{conversation_id}
```

---

## Error Responses

All endpoints may return error responses:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

Common status codes:
- `200` - Success
- `400` - Bad Request
- `415` - Unsupported Media Type / Charset
- `401` - Unauthorized
- `500` - Internal Server Error
