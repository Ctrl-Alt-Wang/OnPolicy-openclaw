"""Tests for local training trace capture helpers."""

import json

from app.db.models import User
from app.training_trace import (
    append_jsonl_trace,
    build_model_chat_trace_record,
    redact_text,
    stable_scope_hash,
)


def make_user() -> User:
    return User(
        id="raw-user-id",
        username="raw-user-name",
        email="raw@example.com",
        password_hash="x",
        runtime_mode="dedicated",
        is_active=True,
    )


def test_redact_text_masks_common_secret_shapes():
    text = "api key sk-test-abcdefghijklmnopqrstuvwxyz and Bearer live-token-123"

    redacted = redact_text(text)

    assert "sk-test" not in redacted
    assert "live-token-123" not in redacted
    assert "[REDACTED]" in redacted


def test_stable_scope_hash_hides_raw_value_but_is_stable():
    first = stable_scope_hash("raw-user-id", salt="salt")
    second = stable_scope_hash("raw-user-id", salt="salt")

    assert first == second
    assert first != "raw-user-id"
    assert len(first) == 16


def test_build_model_chat_trace_record_sanitizes_identity_and_content():
    record = build_model_chat_trace_record(
        link_id="link-1",
        session_id="session-1",
        request_user_id=7,
        function_id=3,
        messages=[
            {"role": "user", "content": "check sk-test-abcdefghijklmnopqrstuvwxyz"},
            {"role": "assistant", "content": "previous answer"},
        ],
        user=make_user(),
        run_id="run-1",
        model="innovation",
        runtime="hermes",
        tool_events=[
            {"event": "tool.started", "tool": "ddi", "arguments": "Bearer tool-secret"},
        ],
        final_output="safe final answer with sk-test-abcdefghijklmnopqrstuvwxyz",
        status="completed",
        trace_hash_salt="salt",
    )

    encoded = json.dumps(record, ensure_ascii=False)
    assert record["source"] == "model_chat"
    assert record["runtime"] == "hermes"
    assert record["run_id"] == "run-1"
    assert record["status"] == "completed"
    assert record["user_scope"] != "raw-user-id"
    assert record["session_scope"] != "session-1"
    assert record["request"]["link_id"] == "link-1"
    assert record["request"]["function_id"] == 3
    assert record["model"] == "innovation"
    assert record["final_output"] == "safe final answer with [REDACTED]"
    assert "sk-test" not in encoded
    assert "tool-secret" not in encoded
    assert "raw-user-id" not in encoded
    assert "raw-user-name" not in encoded
    assert "raw@example.com" not in encoded


def test_append_jsonl_trace_writes_one_record(tmp_path):
    record = {"trace_id": "trace-1", "source": "model_chat"}

    path = append_jsonl_trace(tmp_path, record)

    assert path.parent == tmp_path
    assert path.name.startswith("model_chat-")
    assert path.suffix == ".jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record
