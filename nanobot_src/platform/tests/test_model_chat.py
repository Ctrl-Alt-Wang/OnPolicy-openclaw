"""Tests for POST /api/model/chat SSE endpoint."""

import json
import sys
import types
from typing import Any

import httpx
import pytest

# Stub docker before any app imports
if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.DockerClient = object
    docker_stub.from_env = lambda: None
    docker_stub.types = types.SimpleNamespace(Mount=lambda *a, **kw: None)
    docker_stub.models = types.SimpleNamespace(
        containers=types.SimpleNamespace(Container=object)
    )
    sys.modules["docker"] = docker_stub
    docker_errors = types.ModuleType("docker.errors")
    docker_errors.APIError = RuntimeError
    docker_errors.NotFound = RuntimeError
    docker_stub.errors = docker_errors
    sys.modules["docker.errors"] = docker_errors

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = types.ModuleType("asyncpg")

from app.db.models import User
from app.routes.model_chat import (
    ModelChatRequest,
    _build_base,
    _format_tool_event,
    _inject_download_urls,
    _sse_line,
    _tokenize,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(runtime_mode: str = "dedicated") -> User:
    return User(
        id="u-test-1234",
        username="tester",
        email="tester@example.com",
        password_hash="x",
        runtime_mode=runtime_mode,
        is_active=True,
    )


def make_request(**overrides) -> ModelChatRequest:
    defaults = {
        "linkId": "req-001",
        "sessionId": "sess-001",
        "userId": 1,
        "functionId": 1,
        "messages": [{"role": "user", "content": "hello"}],
        "type": 0,
        "attachment": {},
        "callTools": True,
        "XAPIVersion": 1,
    }
    defaults.update(overrides)
    return ModelChatRequest(**defaults)


def sse_block(event: dict[str, Any]) -> bytes:
    """Encode one SSE data block as bytes (like hermes would send)."""
    return f"data: {json.dumps(event)}\n\n".encode()


def named_sse_block(event_name: str, event: dict[str, Any]) -> bytes:
    """Encode one named SSE event block."""
    return f"event: {event_name}\ndata: {json.dumps(event)}\n\n".encode()


class FakeStreamResponse:
    """Fake httpx streaming response for Hermes chat completions."""

    def __init__(self, chunks: list[bytes], status_code: int = 200):
        self.status_code = status_code
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        return None


class FakeAsyncClient:
    """Fake httpx.AsyncClient that returns predefined responses."""

    def __init__(
        self,
        post_response: httpx.Response | None = None,
        stream_response: FakeStreamResponse | None = None,
    ):
        self._post_response = post_response
        self._stream_response = stream_response
        self.post_calls: list[tuple[str, dict]] = []
        self.stream_calls: list[tuple[str, str]] = []
        self.built_requests: list[tuple[str, str, dict]] = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post_response

    def stream(self, method: str, url: str, **kwargs):
        self.stream_calls.append((method, url))
        return self._stream_response

    def build_request(self, method: str, url: str, **kwargs):
        self.built_requests.append((method, url, kwargs))
        return httpx.Request(method, url)

    async def send(self, request, **kwargs):
        return self._stream_response

    async def aclose(self):
        self.closed = True


class FakeRequest:
    """Fake FastAPI Request object."""

    async def is_disconnected(self):
        return False


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_chinese_chars_split(self):
        tokens = _tokenize("你好世界")
        assert tokens == ["你", "好", "世", "界"]

    def test_english_words_grouped(self):
        tokens = _tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_mixed(self):
        tokens = _tokenize("hi你好")
        assert "hi" in tokens
        assert "你" in tokens
        assert "好" in tokens

    def test_empty_string(self):
        tokens = _tokenize("")
        assert tokens == [""]


class TestSseLine:
    def test_format(self):
        line = _sse_line({"message": "hi", "type": 4})
        assert line.startswith("data: ")
        assert line.endswith("\n\n")
        data = json.loads(line[6:].strip())
        assert data["message"] == "hi"
        assert data["type"] == 4

    def test_chinese_not_escaped(self):
        line = _sse_line({"message": "你好"})
        assert "你好" in line


class TestBuildBase:
    def test_fields(self):
        req = make_request()
        base = _build_base(req)
        assert base["linkId"] == "req-001"
        assert base["sessionId"] == "sess-001"
        assert base["userId"] == 1
        assert base["functionId"] == 1
        assert base["XAPIVersion"] == 1


class TestFormatToolEvent:
    def test_tool_started(self):
        result = _format_tool_event({"event": "tool.started", "tool": "search"})
        assert result == "[工具] 调用: search"

    def test_tool_completed(self):
        result = _format_tool_event({"event": "tool.completed", "tool": "search"})
        assert result == "[工具] 完成: search"

    def test_tool_completed_with_error(self):
        result = _format_tool_event({"event": "tool.completed", "tool": "search", "error": "timeout"})
        assert "失败" in result

    def test_unknown_event(self):
        result = _format_tool_event({"event": "message.delta"})
        assert result is None


class TestInjectDownloadUrls:
    def test_bold_wrapped_file_path_is_linked(self):
        text = "文件路径是：**/tmp/openclaw_rl_test.txt**"

        result = _inject_download_urls(text, "sess-1")

        assert "**[openclaw_rl_test.txt](" in result
        assert "sessionId=sess-1" in result
        assert "path=/tmp/openclaw_rl_test.txt" in result


# ---------------------------------------------------------------------------
# Resolve hermes URL tests
# ---------------------------------------------------------------------------

class TestResolveHermesUrl:
    @pytest.mark.asyncio
    async def test_dev_url_takes_priority(self, monkeypatch):
        from app.config import settings
        from app.routes import model_chat

        monkeypatch.setattr(settings, "dev_openclaw_url", "http://dev-hermes:9999/")
        url = await model_chat._resolve_hermes_url("session-dev")
        assert url == "http://dev-hermes:9999"
        assert model_chat._session_container_map["session-dev"] == "http://dev-hermes:9999"

    @pytest.mark.asyncio
    async def test_session_affinity_reuses_previous_container(self, monkeypatch):
        from app.config import settings
        from app.routes import model_chat

        monkeypatch.setattr(settings, "dev_openclaw_url", "")
        model_chat._session_container_map["session-a"] = "http://hermes-innovation-03:18080"
        model_chat._busy_containers.clear()

        url = await model_chat._resolve_hermes_url("session-a")

        assert url == "http://hermes-innovation-03:18080"
        assert model_chat._busy_containers[url] == "session-a"

    @pytest.mark.asyncio
    async def test_round_robin_assigns_container_for_new_session(self, monkeypatch):
        from app.config import settings
        from app.routes import model_chat

        monkeypatch.setattr(settings, "dev_openclaw_url", "")
        model_chat._busy_containers.clear()
        model_chat._session_container_map.pop("session-new", None)
        model_chat._rr_index[0] = 0

        url = await model_chat._resolve_hermes_url("session-new")

        assert url == "http://hermes-innovation-00:18080"
        assert model_chat._session_container_map["session-new"] == url


# ---------------------------------------------------------------------------
# SSE stream integration tests
# ---------------------------------------------------------------------------

class TestModelChatStream:
    """Test the full SSE stream generation by calling the route handler directly."""

    @pytest.mark.asyncio
    async def test_normal_conversation_stream(self, monkeypatch):
        from app.routes import model_chat

        hermes_events = [
            named_sse_block("hermes.tool.progress", {"tool": "search", "status": "running"}),
            named_sse_block("hermes.tool.progress", {"tool": "search", "status": "completed"}),
            sse_block({"choices": [{"delta": {"content": "你好"}, "finish_reason": None}]}),
            sse_block({"choices": [{"delta": {"content": "世界"}, "finish_reason": "stop"}]}),
        ]

        client_instances = []

        def fake_client_factory(**kwargs):
            client = FakeAsyncClient(stream_response=FakeStreamResponse(hermes_events))
            client_instances.append(client)
            return client

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

        async def fake_resolve(session_id):
            return "http://fake"
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        req = make_request(messages=[{"role": "user", "content": "hello"}])
        request = FakeRequest()

        response = await model_chat.model_chat(request, req)

        collected = []
        async for chunk in response.body_iterator:
            collected.append(chunk)

        events = []
        for chunk in collected:
            for line in chunk.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        reasoning_msgs = [e.get("reasoningMessage", "") for e in events if e.get("reasoningMessage")]
        assert any("search" in r for r in reasoning_msgs)

        messages = [e.get("message", "") for e in events if e.get("message") and e["message"] != "[stop]"]
        assert len(messages) > 0

        last_event = events[-1]
        assert last_event["message"] == "[stop]"
        method, url, kwargs = client_instances[0].built_requests[0]
        assert method == "POST"
        assert url == "http://fake/v1/chat/completions"
        assert kwargs["json"]["messages"] == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_split_file_path_download_link_is_not_corrupted(self, monkeypatch):
        from app.routes import model_chat

        hermes_events = [
            sse_block({"choices": [{"delta": {"content": "已创建 /opt/hermes/README"}, "finish_reason": None}]}),
            sse_block({"choices": [{"delta": {"content": ".md，内容为当前时间"}, "finish_reason": "stop"}]}),
        ]

        def fake_client_factory(**kwargs):
            return FakeAsyncClient(stream_response=FakeStreamResponse(hermes_events))

        async def fake_resolve(session_id):
            return "http://fake"

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        response = await model_chat.model_chat(FakeRequest(), make_request(sessionId="split-path"))

        events = []
        async for chunk in response.body_iterator:
            for line in chunk.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        text = "".join(
            event["message"]
            for event in events
            if isinstance(event.get("message"), str) and event["message"] != "[stop]"
        )
        assert "[README.md](" in text
        assert "sessionId=split-path" in text
        assert "path=/opt/hermes/README.md" in text
        assert "READMEodel/chat/file" not in text

    @pytest.mark.asyncio
    async def test_trace_capture_disabled_writes_no_local_trace(self, monkeypatch, tmp_path):
        from app.routes import model_chat

        hermes_events = [
            sse_block({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}),
        ]

        def fake_client_factory(**kwargs):
            return FakeAsyncClient(stream_response=FakeStreamResponse(hermes_events))

        async def fake_resolve(session_id):
            return "http://fake"

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)
        monkeypatch.setattr(model_chat.settings, "training_trace_enabled", False, raising=False)
        monkeypatch.setattr(model_chat.settings, "training_trace_dir", str(tmp_path), raising=False)

        response = await model_chat.model_chat(FakeRequest(), make_request())

        async for _ in response.body_iterator:
            pass

        assert list(tmp_path.glob("*.jsonl")) == []

    @pytest.mark.asyncio
    async def test_trace_capture_enabled_writes_sanitized_local_trace(self, monkeypatch, tmp_path):
        from app.routes import model_chat

        hermes_events = [
            named_sse_block(
                "hermes.tool.progress",
                {"tool": "ddi", "status": "running", "label": "Bearer tool-secret"},
            ),
            named_sse_block("hermes.tool.progress", {"tool": "ddi", "status": "completed"}),
            sse_block({"choices": [{"delta": {"content": "safe "}, "finish_reason": None}]}),
            sse_block({
                "choices": [
                    {"delta": {"content": "answer with Bearer live-token-123"}, "finish_reason": "stop"}
                ]
            }),
        ]

        def fake_client_factory(**kwargs):
            return FakeAsyncClient(stream_response=FakeStreamResponse(hermes_events))

        async def fake_resolve(session_id):
            return "http://fake"

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)
        monkeypatch.setattr(model_chat.settings, "training_trace_enabled", True, raising=False)
        monkeypatch.setattr(model_chat.settings, "training_trace_dir", str(tmp_path), raising=False)
        monkeypatch.setattr(model_chat.settings, "training_trace_hash_salt", "salt", raising=False)

        req = make_request(
            linkId="trace-link",
            sessionId="trace-session",
            functionId=9,
            messages=[
                {"role": "user", "content": "check sk-test-abcdefghijklmnopqrstuvwxyz"},
            ],
        )

        response = await model_chat.model_chat(FakeRequest(), req)

        async for _ in response.body_iterator:
            pass

        trace_files = list(tmp_path.glob("*.jsonl"))
        assert len(trace_files) == 1
        record = json.loads(trace_files[0].read_text(encoding="utf-8").splitlines()[0])
        encoded = json.dumps(record, ensure_ascii=False)
        assert record["source"] == "model_chat"
        assert record["run_id"] == ""
        assert record["runtime"] == "hermes"
        assert record["model"] == "hermes-agent"
        assert record["status"] == "completed"
        assert record["request"]["link_id"] == "trace-link"
        assert record["request"]["function_id"] == 9
        assert record["final_output"] == "safe answer with [REDACTED]"
        assert [event["event"] for event in record["tool_events"]] == [
            "tool.running",
            "tool.completed",
        ]
        assert "sk-test" not in encoded
        assert "tool-secret" not in encoded
        assert "live-token-123" not in encoded

    @pytest.mark.asyncio
    async def test_abort_request(self, monkeypatch):
        from app.routes import model_chat

        model_chat._session_run_map["sess-abort"] = "run-to-abort"

        stop_response = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("POST", "http://fake/v1/runs/run-to-abort/stop"),
        )

        stop_calls = []

        def fake_client_factory(**kwargs):
            client = FakeAsyncClient(post_response=stop_response)
            original_post = client.post
            async def tracking_post(url, **kw):
                stop_calls.append(url)
                return await original_post(url, **kw)
            client.post = tracking_post
            return client

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

        async def fake_resolve(session_id):
            return "http://fake"
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        req = make_request(sessionId="sess-abort", type=-1)
        request = FakeRequest()

        result = await model_chat.model_chat(request, req)

        assert result["ok"] is True
        assert any("stop" in url for url in stop_calls)
        assert "sess-abort" not in model_chat._session_run_map

    @pytest.mark.asyncio
    async def test_chat_completion_failure_sends_stop(self, monkeypatch):
        from app.routes import model_chat

        def fake_client_factory(**kwargs):
            return FakeAsyncClient(stream_response=FakeStreamResponse([], status_code=500))

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

        async def fake_resolve(session_id):
            return "http://fake"
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        req = make_request()
        request = FakeRequest()

        response = await model_chat.model_chat(request, req)

        collected = []
        async for chunk in response.body_iterator:
            collected.append(chunk)

        events = []
        for chunk in collected:
            for line in chunk.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        assert events[-1]["message"] == "[stop]"

    @pytest.mark.asyncio
    async def test_reasoning_event_forwarded(self, monkeypatch):
        from app.routes import model_chat

        hermes_events = [
            named_sse_block("hermes.reasoning.delta", {"text": "让我思考一下..."}),
            sse_block({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
        ]

        def fake_client_factory(**kwargs):
            return FakeAsyncClient(stream_response=FakeStreamResponse(hermes_events))

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

        async def fake_resolve(session_id):
            return "http://fake"
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        req = make_request()
        request = FakeRequest()

        response = await model_chat.model_chat(request, req)

        collected = []
        async for chunk in response.body_iterator:
            collected.append(chunk)

        events = []
        for chunk in collected:
            for line in chunk.strip().split("\n"):
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        reasoning = [e for e in events if e.get("reasoningMessage") and e["reasoningMessage"] != ""]
        assert any("思考" in e["reasoningMessage"] for e in reasoning)

    @pytest.mark.asyncio
    async def test_missing_linkid_raises_400(self):
        from app.routes import model_chat

        req = make_request(linkId="")
        request = FakeRequest()

        with pytest.raises(Exception) as exc_info:
            await model_chat.model_chat(request, req)
        assert "400" in str(exc_info.value.status_code) or exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_messages_raises_400(self):
        from app.routes import model_chat

        req = make_request(messages=[])
        request = FakeRequest()

        with pytest.raises(Exception) as exc_info:
            await model_chat.model_chat(request, req)
        assert exc_info.value.status_code == 400


class TestModelChatMultiTurn:
    """Test multi-turn conversation handling."""

    @pytest.mark.asyncio
    async def test_full_messages_sent_to_chat_completions(self, monkeypatch):
        from app.routes import model_chat

        captured_json: list[dict] = []

        class CapturingClient:
            def build_request(self, method, url, **kwargs):
                captured_json.append(kwargs["json"])
                return httpx.Request(method, url)

            async def send(self, request, **kwargs):
                return FakeStreamResponse([
                    sse_block({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}),
                ])

            async def aclose(self):
                return None

        def fake_client_factory(**kwargs):
            return CapturingClient()

        monkeypatch.setattr(httpx, "AsyncClient", fake_client_factory)

        async def fake_resolve(session_id):
            return "http://fake"
        monkeypatch.setattr(model_chat, "_resolve_hermes_url", fake_resolve)

        req = make_request(
            messages=[
                {"role": "user", "content": "第一个问题"},
                {"role": "assistant", "content": "第一个回答"},
                {"role": "user", "content": "第二个问题"},
            ]
        )
        request = FakeRequest()

        response = await model_chat.model_chat(request, req)

        async for _ in response.body_iterator:
            pass

        assert len(captured_json) == 1
        payload = captured_json[0]
        assert payload["messages"] == [
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "第二个问题"},
        ]
