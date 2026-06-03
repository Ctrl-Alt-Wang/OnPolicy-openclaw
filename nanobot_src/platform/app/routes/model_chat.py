"""POST /api/model/chat — SSE streaming endpoint for external backends.

Accepts the standardised ModelChat request format, creates a Hermes
chat completion, subscribes to the SSE event stream, and re-emits events
in the format expected by the downstream consumer (Yang's backend / front-end).

Uses /v1/chat/completions with X-Hermes-Session-Id header so the Hermes
container automatically loads conversation history from its SQLite session DB.

Response SSE payload types:
  4 = text stream delta (message for final text, reasoningMessage for thinking)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import tarfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import requests as _sync_requests
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.container.manager import get_docker_container
from app.training_trace import append_jsonl_trace, build_model_chat_trace_record

logger = logging.getLogger(__name__)
router = APIRouter(tags=["model-chat"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ModelChatMessage(BaseModel):
    role: str  # system | user | assistant | tool
    content: str


class ModelChatRequest(BaseModel):
    linkId: str
    sessionId: str
    userId: int = 1
    functionId: int = 1
    messages: list[ModelChatMessage] = []
    type: int = 0  # -1 = abort
    attachment: Any = {}
    callTools: bool = True
    XAPIVersion: Any = 1

    @field_validator("attachment", mode="before")
    @classmethod
    def _coerce_attachment(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("XAPIVersion", mode="before")
    @classmethod
    def _coerce_xapi_version(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 1
        except (TypeError, ValueError):
            return 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Session → run_id mapping so we can abort by sessionId
_session_run_map: dict[str, str] = {}
_session_run_cleanup_tasks: dict[str, asyncio.TimerHandle] = {}
# Session → container URL (for session affinity, file download, abort routing)
_session_container_map: dict[str, str] = {}

# Container URL → session_id (tracks which session currently holds the container)
_busy_containers: dict[str, str] = {}

# Async lock protecting _busy_containers, _rr_index, and writes to _session_container_map
_container_lock = asyncio.Lock()

# Explicit round-robin index as mutable container (replaces itertools.cycle)
_rr_index = [0]

_TYPEWRITER_DELAY = 0.05  # seconds between tokens
_TYPEWRITER_FAST_DELAY = 0.01  # when queue > 20
_SESSION_CONTAINER_TTL = 30 * 60  # 30 minutes before cleaning up session→container mapping
_STREAM_REWRITE_TAIL_CHARS = 512  # keep enough tail text for split file paths


def _build_base(req: ModelChatRequest) -> dict[str, Any]:
    return {
        "linkId": req.linkId,
        "sessionId": req.sessionId,
        "userId": req.userId,
        "functionId": req.functionId,
        "attachment": req.attachment or {},
        "XAPIVersion": req.XAPIVersion,
    }


def _sse_line(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _format_tool_event(event: dict[str, Any]) -> str | None:
    """Convert a hermes tool event to a human-readable progress string."""
    evt = event.get("event") or event.get("type") or ""
    if evt == "tool.started":
        name = event.get("tool") or "unknown"
        return f"[工具] 调用: {name}"
    if evt == "tool.completed":
        name = event.get("tool") or "unknown"
        err = " (失败)" if event.get("error") else ""
        return f"[工具] 完成: {name}{err}"
    return None


def _container_name_from_url(url: str) -> str:
    """Extract container name from URL like 'http://hermes-innovation-03:18080'."""
    from urllib.parse import urlparse
    return urlparse(url).hostname or ""


# Regex to match file paths in agent messages (absolute paths with common extensions)
_FILE_EXTENSIONS = r'(?:md|docx|pdf|pptx|xlsx|csv|html|txt|json|png|jpg|jpeg|gif|svg|zip|tar|gz)'
# Pattern 1: backtick-wrapped paths like `/tmp/report.pdf`
_FILE_PATH_BACKTICK_RE = re.compile(
    r'`(/(?!/)[^`\s]+\.' + _FILE_EXTENSIONS + r')`',
)
# Pattern 2: bare paths (preceded by whitespace, colon, or line start; not URLs)
_FILE_PATH_BARE_RE = re.compile(
    r'(?:^|[\s：:*])(/(?!/)[^\s\'"<>]+\.' + _FILE_EXTENSIONS + r')',
    re.MULTILINE,
)


def _inject_download_urls(text: str, session_id: str) -> str:
    """Replace file paths in text with markdown download links.

    Two passes: backtick-wrapped paths first, then bare paths.
    """
    def _make_link(path: str) -> str:
        filename = path.rsplit("/", 1)[-1]
        base = os.environ.get("DOWNLOAD_BASE_URL", "").rstrip("/")
        url = f"{base}/api/model/chat/file?sessionId={quote(session_id)}&path={quote(path)}"
        return f'[{filename}]({url})'

    # Pass 1: backtick-wrapped  `/path/file.pdf` → [file.pdf](url)
    def _replace_backtick(m: re.Match) -> str:
        return _make_link(m.group(1))
    text = _FILE_PATH_BACKTICK_RE.sub(_replace_backtick, text)

    # Pass 2: bare paths  /path/file.pdf → [file.pdf](url)
    def _replace_bare(m: re.Match) -> str:
        path = m.group(1)
        prefix = m.group(0)[0] if m.group(0)[0] != "/" else ""
        return f'{prefix}{_make_link(path)}'
    text = _FILE_PATH_BARE_RE.sub(_replace_bare, text)

    return text


# Tokenise text for typewriter: Chinese chars individually, English words together
_TOKEN_RE = re.compile(r"[a-zA-Z]+|\S|\s", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text) or [text]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(os.environ.get("MODEL_CHAT_CACHE_DIR", "/opt/data/cache/model_chat"))
_CACHE_ENABLED = os.environ.get("MODEL_CHAT_CACHE_ENABLED", "1") == "1"


def _compute_cache_key(body: ModelChatRequest) -> str:
    """Generate a deterministic cache key from the request content.

    Excludes session-specific fields (linkId, sessionId, userId, attachment).
    """
    payload = json.dumps(
        {
            "messages": [{"role": m.role, "content": m.content} for m in body.messages],
            "functionId": body.functionId,
            "callTools": body.callTools,
            "XAPIVersion": body.XAPIVersion,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_file_path(cache_key: str) -> Path:
    return _CACHE_DIR / f"{cache_key}.jsonl"


def _read_cache(cache_key: str) -> list[dict[str, Any]] | None:
    """Read cached SSE events from disk. Returns None on miss or error."""
    path = _cache_file_path(cache_key)
    if not path.exists():
        return None
    try:
        events: list[dict[str, Any]] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events
    except Exception:
        return None


def _write_cache(cache_key: str, events: list[dict[str, Any]]) -> None:
    """Write captured SSE events to disk cache."""
    path = _cache_file_path(cache_key)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for evt in events:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[model-chat] 缓存写入失败: %s", exc)


# ---------------------------------------------------------------------------
# Hermes connection helpers
# ---------------------------------------------------------------------------

def _hermes_auth_headers() -> dict[str, str]:
    key = settings.dedicated_hermes_api_key
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


# Pool of 10 pre-created innovation hermes containers
_INNOVATION_CONTAINERS = [f"http://hermes-innovation-{i:02d}:{settings.dedicated_hermes_internal_port}" for i in range(10)]


async def _resolve_hermes_url(session_id: str) -> str:
    """Return the base URL for a pre-created innovation hermes runtime.

    Session-affinity round-robin: if a session previously used a container and
    that container is not busy, prefer it. Otherwise fall back to round-robin
    across available containers.
    """
    async with _container_lock:
        # 1. Check session affinity: prefer previously assigned container
        preferred = _session_container_map.get(session_id)
        if preferred and preferred not in _busy_containers:
            _busy_containers[preferred] = session_id
            logger.info("[model-chat] 会话亲和: session=%s → %s (复用已分配容器)", session_id, preferred)
            return preferred

        # 2. Scan for a non-busy container starting from round-robin index
        n = len(_INNOVATION_CONTAINERS)
        for offset in range(n):
            idx = (_rr_index[0] + offset) % n
            url = _INNOVATION_CONTAINERS[idx]
            if url not in _busy_containers:
                _busy_containers[url] = session_id
                _session_container_map[session_id] = url
                _rr_index[0] = (idx + 1) % n
                logger.info("[model-chat] 轮询分配: session=%s → %s (preferred=%s, busy=%s)", session_id, url, preferred, bool(preferred))
                return url

        # 3. All busy: fallback to preferred or round-robin pick
        if preferred:
            chosen = preferred
        else:
            chosen = _INNOVATION_CONTAINERS[_rr_index[0]]
            _rr_index[0] = (_rr_index[0] + 1) % n
        _busy_containers[chosen] = session_id
        _session_container_map[session_id] = chosen
        logger.warning("[model-chat] 所有容器均忙碌，复用容器: %s (session=%s)", chosen, session_id)
        return chosen


async def _release_container(container_url: str, session_id: str) -> None:
    """Mark a container as no longer busy after its SSE stream completes."""
    async with _container_lock:
        # Only release if the session still owns this container entry
        if _busy_containers.get(container_url) == session_id:
            _busy_containers.pop(container_url, None)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/api/model/chat")
async def model_chat(
    request: Request,
    body: ModelChatRequest,
    user=None,
):
    # --- Abort ---
    if body.type == -1:
        run_id = _session_run_map.get(body.sessionId)
        if run_id:
            try:
                # Use session's assigned container directly (not round-robin)
                base_url = _session_container_map.get(body.sessionId)
                if not base_url:
                    # Fallback: session mapping expired, resolve via affinity
                    base_url = await _resolve_hermes_url(body.sessionId)
                    await _release_container(base_url, body.sessionId)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{base_url}/v1/runs/{run_id}/stop",
                        headers=_hermes_auth_headers(),
                    )
            except Exception as exc:
                logger.warning("abort failed for session %s: %s", body.sessionId, exc)
            _session_run_map.pop(body.sessionId, None)
        return {"linkId": body.linkId, "sessionId": body.sessionId, "ok": True}

    # --- Validate ---
    if not body.linkId or not body.sessionId:
        raise HTTPException(status_code=400, detail="linkId and sessionId are required")
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages array is required and must not be empty")

    logger.info(
        "[model-chat] 请求开始: linkId=%s sessionId=%s userId=%s functionId=%s type=%s",
        body.linkId, body.sessionId, body.userId, body.functionId, body.type,
    )

    base = _build_base(body)

    # --- Cache: return cached response if available ---
    cache_key: str | None = None
    if _CACHE_ENABLED:
        cache_key = _compute_cache_key(body)
        cached_events = _read_cache(cache_key)
        if cached_events is not None:
            logger.info(
                "[model-chat] 缓存命中: sessionId=%s key=%s events=%d",
                body.sessionId, cache_key[:16], len(cached_events),
            )

            async def _replay_from_cache():
                for evt in cached_events:
                    # Substitute session-specific fields with current request values
                    evt["linkId"] = base["linkId"]
                    evt["sessionId"] = base["sessionId"]
                    evt["userId"] = base["userId"]
                    evt["functionId"] = base["functionId"]
                    yield _sse_line(evt)
                    await asyncio.sleep(0.1)

            return StreamingResponse(
                _replay_from_cache(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

    base_url = await _resolve_hermes_url(body.sessionId)
    trace_tool_events: list[dict[str, Any]] = []
    trace_run_id = ""
    trace_status = "not_started"
    trace_written = False

    # Build headers with X-Hermes-Session-Id for automatic history loading
    hermes_headers = _hermes_auth_headers()
    hermes_headers["X-Hermes-Session-Id"] = body.sessionId

    # Build messages for chat completions (only need the latest user message;
    # history is auto-loaded from SQLite via X-Hermes-Session-Id)
    chat_messages = [{"role": msg.role, "content": msg.content} for msg in body.messages]

    async def _stream():
        full_text = ""           # 累积完整消息原文
        pending_text = ""        # 暂存尾部，避免跨 chunk 文件路径被改写坏
        _usage: dict[str, int] = {}   # 从最终 chunk 中提取的 token 用量
        _model_name: str = ""         # 实际使用的模型名

        def _pop_rewritten_pending(force: bool = False) -> str:
            nonlocal pending_text
            if not pending_text:
                return ""
            if force:
                text = pending_text
                pending_text = ""
            elif len(pending_text) > _STREAM_REWRITE_TAIL_CHARS:
                cut = len(pending_text) - _STREAM_REWRITE_TAIL_CHARS
                text = pending_text[:cut]
                pending_text = pending_text[cut:]
            else:
                return ""
            return _inject_download_urls(text, body.sessionId)

        def _trace_enabled() -> bool:
            return bool(getattr(settings, "training_trace_enabled", False))

        def _write_trace_once(status_text: str) -> None:
            nonlocal trace_written
            if trace_written or not _trace_enabled():
                return
            trace_written = True
            try:
                record = build_model_chat_trace_record(
                    link_id=body.linkId,
                    session_id=body.sessionId,
                    request_user_id=body.userId,
                    function_id=body.functionId,
                    messages=body.messages,
                    user=None,
                    run_id=trace_run_id,
                    model="hermes-agent",
                    runtime="hermes",
                    tool_events=trace_tool_events,
                    final_output=full_text,
                    status=status_text,
                    trace_hash_salt=getattr(settings, "training_trace_hash_salt", ""),
                )
                append_jsonl_trace(getattr(settings, "training_trace_dir", ".hermes/training_traces"), record)
            except Exception as exc:
                logger.warning("[model-chat] training trace write failed: %s", exc)

        # 立刻返回 thinking，让用户感受到响应
        yield _sse_line({**base, "message": "", "reasoningMessage": "thinking:", "type": 4})

        # 1. Create chat completion stream
        try:
            client = httpx.AsyncClient(timeout=None)
            req = client.build_request(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers=hermes_headers,
                json={
                    "model": "hermes-agent",
                    "messages": chat_messages,
                    "stream": True,
                },
            )
            event_stream = await client.send(req, stream=True)
        except Exception as exc:
            logger.error("[model-chat] create chat completion error: %s", exc)
            _write_trace_once("create_chat_completion_error")
            await _release_container(base_url, body.sessionId)
            yield _sse_line({**base, "message": "[stop]", "reasoningMessage": "", "type": 4})
            return

        if event_stream.status_code >= 400:
            logger.error("[model-chat] chat completion returned %s", event_stream.status_code)
            _write_trace_once("stream_connect_failed")
            await event_stream.aclose()
            await client.aclose()
            await _release_container(base_url, body.sessionId)
            yield _sse_line({**base, "message": "[stop]", "reasoningMessage": "", "type": 4})
            return

        # 2. Process SSE event stream
        try:
            buffer = ""
            current_event = ""  # for named events like hermes.tool.progress
            async for chunk in event_stream.aiter_bytes():
                if await request.is_disconnected():
                    trace_status = "disconnected"
                    break

                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n\n" in buffer:
                    raw_block, buffer = buffer.split("\n\n", 1)

                    # Parse event type if present (e.g. "event: hermes.tool.progress")
                    for line in raw_block.splitlines():
                        if line.startswith("event:"):
                            current_event = line[6:].strip()

                    # Parse data lines
                    data_lines = [
                        line[5:].strip()
                        for line in raw_block.splitlines()
                        if line.startswith("data:")
                    ]
                    if not data_lines:
                        current_event = ""
                        continue
                    data_str = "\n".join(data_lines)
                    if data_str == "[DONE]":
                        current_event = ""
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        current_event = ""
                        continue
                    if not isinstance(data, dict):
                        current_event = ""
                        continue

                    # --- Tool progress events → reasoning ---
                    if current_event == "hermes.tool.progress":
                        tool_name = data.get("tool") or "unknown"
                        status = data.get("status") or ""
                        if status:
                            trace_tool_events.append(
                                {
                                    "event": f"tool.{status}",
                                    "tool": tool_name,
                                    "status": status,
                                    "label": data.get("label"),
                                }
                            )
                        if status == "running":
                            label = data.get("label") or tool_name
                            yield _sse_line({
                                **base,
                                "message": "",
                                "reasoningMessage": f"[工具] 调用: {label}",
                                "type": 4,
                            })
                        elif status == "completed":
                            yield _sse_line({
                                **base,
                                "message": "",
                                "reasoningMessage": f"[工具] 完成: {tool_name}",
                                "type": 4,
                            })
                        current_event = ""
                        continue

                    # --- Reasoning/thinking deltas → reasoningMessage ---
                    if current_event == "hermes.reasoning.delta":
                        reasoning_text = data.get("text") or ""
                        if reasoning_text:
                            yield _sse_line({
                                **base,
                                "message": "",
                                "reasoningMessage": reasoning_text,
                                "type": 4,
                            })
                        current_event = ""
                        continue

                    # --- Chat completion chunks → message ---
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            full_text += content
                            pending_text += content
                            rewritten_delta = _pop_rewritten_pending()
                            if rewritten_delta:
                                yield _sse_line({**base, "message": rewritten_delta, "reasoningMessage": "", "type": 4})

                        # Check for finish — extract usage from same chunk
                        finish_reason = choices[0].get("finish_reason")
                        if finish_reason:
                            _usage = data.get("usage") or {}
                            _model_name = data.get("model") or ""
                            trace_status = "completed"
                            break

                    current_event = ""

        except httpx.ConnectError as exc:
            logger.error("[model-chat] hermes stream connect error: %s", exc)
            trace_status = "stream_connect_error"
        except Exception as exc:
            logger.error("[model-chat] hermes stream error: %s", exc)
            trace_status = "stream_error"
        finally:
            await event_stream.aclose()
            await client.aclose()

        rewritten_tail = _pop_rewritten_pending(force=True)
        if rewritten_tail:
            yield _sse_line({**base, "message": rewritten_tail, "reasoningMessage": "", "type": 4})

        # Emit token usage event (type=999) before stop
        total_tokens = _usage.get("total_tokens", 0)
        if total_tokens:
            yield _sse_line({**base, "message": {"totalToken": total_tokens}, "reasoningMessage": "", "type": 999})

        if trace_status == "not_started":
            trace_status = "stream_ended"
        _write_trace_once(trace_status)

        # Send stop signal
        yield _sse_line({**base, "message": "[stop]", "reasoningMessage": "", "type": 4})

        # Cleanup: release container, remove run mapping, schedule container mapping cleanup
        _session_run_map.pop(body.sessionId, None)
        await _release_container(base_url, body.sessionId)

        async def _delayed_cleanup(sid: str):
            await asyncio.sleep(_SESSION_CONTAINER_TTL)
            _session_container_map.pop(sid, None)
            logger.debug("[model-chat] 清理 session→container 映射: %s", sid)

        asyncio.create_task(_delayed_cleanup(body.sessionId))
        logger.info("[model-chat] 请求结束: sessionId=%s", body.sessionId)

    # --- Wrap stream for cache capture (cache miss only) ---
    if cache_key:
        _original_stream = _stream

        async def _stream():
            events: list[dict[str, Any]] = []
            async for sse_line in _original_stream():
                if sse_line.startswith("data: "):
                    try:
                        events.append(json.loads(sse_line[6:].strip()))
                    except json.JSONDecodeError:
                        pass
                yield sse_line
            if events:
                _write_cache(cache_key, events)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# File download endpoint
# ---------------------------------------------------------------------------

@router.get("/api/model/chat/file")
async def model_chat_file(
    sessionId: str = Query(..., description="会话ID"),
    path: str = Query(..., description="容器内文件绝对路径，如 /tmp/report.pdf"),
):
    """从 hermes 容器下载生成的文件（支持任意路径和文件类型）。"""
    container_url = _session_container_map.get(sessionId)
    if not container_url:
        raise HTTPException(status_code=404, detail="会话未找到或已过期")
    container_name = _container_name_from_url(container_url)

    # 安全校验：禁止路径穿越和敏感文件
    normalized = path.replace("\\", "/")
    if ".." in normalized:
        raise HTTPException(status_code=400, detail="非法路径")
    _SENSITIVE = {".env", "config.yaml", "config.yml", ".ssh", "id_rsa", "id_ed25519"}
    if any(seg in _SENSITIVE for seg in normalized.split("/")):
        raise HTTPException(status_code=403, detail="无法访问该文件")

    try:
        container = get_docker_container(container_name)
        stream, _stat = container.get_archive(normalized)
        archive = b"".join(stream)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                content = extracted.read()
                media_type = mimetypes.guess_type(normalized)[0] or "application/octet-stream"
                filename = normalized.rsplit("/", 1)[-1]
                return Response(
                    content=content,
                    media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
    except DockerNotFound:
        raise HTTPException(status_code=404, detail="文件未找到")
    except DockerAPIError as exc:
        logger.error("[model-chat] file download docker error: %s", exc)
        raise HTTPException(status_code=500, detail="文件读取失败")
    except Exception as exc:
        logger.error("[model-chat] file download error: %s", exc)
        raise HTTPException(status_code=500, detail="文件读取失败")

    raise HTTPException(status_code=404, detail="文件未找到")
