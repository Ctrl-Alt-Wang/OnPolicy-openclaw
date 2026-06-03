"""Tests for internal training trace ingestion API."""

import json

import pytest
from app.routes import training_traces
from fastapi import HTTPException


def configure_ingest(monkeypatch, tmp_path, *, enabled=True, token="ingest-secret"):
    monkeypatch.setattr(training_traces.settings, "training_trace_ingest_enabled", enabled, raising=False)
    monkeypatch.setattr(training_traces.settings, "training_trace_ingest_token", token, raising=False)
    monkeypatch.setattr(training_traces.settings, "training_trace_dir", str(tmp_path), raising=False)


@pytest.mark.asyncio
async def test_training_trace_ingest_rejects_when_disabled(monkeypatch, tmp_path):
    configure_ingest(monkeypatch, tmp_path, enabled=False)

    with pytest.raises(HTTPException) as exc:
        await training_traces.ingest_training_trace(
            training_traces.TrainingTraceIngestRequest(trace={"trace_id": "trace-disabled"}),
            authorization="Bearer ingest-secret",
        )

    assert exc.value.status_code == 403
    assert list(tmp_path.glob("*.jsonl")) == []


@pytest.mark.asyncio
async def test_training_trace_ingest_requires_internal_bearer_token(monkeypatch, tmp_path):
    configure_ingest(monkeypatch, tmp_path)
    request = training_traces.TrainingTraceIngestRequest(trace={"trace_id": "trace-auth"})

    with pytest.raises(HTTPException) as missing:
        await training_traces.ingest_training_trace(request, authorization="")
    with pytest.raises(HTTPException) as invalid:
        await training_traces.ingest_training_trace(request, authorization="Bearer wrong")

    assert missing.value.status_code == 401
    assert invalid.value.status_code == 401
    assert list(tmp_path.glob("*.jsonl")) == []


@pytest.mark.asyncio
async def test_training_trace_ingest_writes_redacted_jsonl_record(monkeypatch, tmp_path):
    configure_ingest(monkeypatch, tmp_path)

    result = await training_traces.ingest_training_trace(
        training_traces.TrainingTraceIngestRequest(
            privacy_level="L1",
            trace={
                "trace_id": "trace-api",
                "source": "model_chat",
                "status": "completed",
                "messages": [
                    {
                        "role": "user",
                        "content": "check sk-test-abcdefghijklmnopqrstuvwxyz",
                    }
                ],
                "final_output": "answer with Bearer live-token-123",
                "privacy": {"raw_user_identity_stored": False},
            },
        ),
        authorization="Bearer ingest-secret",
    )

    assert result == {"ok": True, "trace_id": "trace-api", "stored": True}
    trace_files = list(tmp_path.glob("training_trace_ingest-*.jsonl"))
    assert len(trace_files) == 1
    record = json.loads(trace_files[0].read_text(encoding="utf-8").splitlines()[0])
    encoded = json.dumps(record, ensure_ascii=False)
    assert record["trace_id"] == "trace-api"
    assert record["privacy"]["ingest_privacy_level"] == "L1"
    assert record["privacy"]["raw_user_identity_stored"] is False
    assert record["ingest"]["interface"] == "api.training_traces"
    assert "sk-test" not in encoded
    assert "live-token-123" not in encoded


@pytest.mark.asyncio
async def test_training_trace_ingest_rejects_raw_identity_trace(monkeypatch, tmp_path):
    configure_ingest(monkeypatch, tmp_path)

    with pytest.raises(HTTPException) as exc:
        await training_traces.ingest_training_trace(
            training_traces.TrainingTraceIngestRequest(
                trace={
                    "trace_id": "trace-raw-identity",
                    "privacy": {"raw_user_identity_stored": True},
                },
            ),
            authorization="Bearer ingest-secret",
        )

    assert exc.value.status_code == 400
    assert list(tmp_path.glob("*.jsonl")) == []
