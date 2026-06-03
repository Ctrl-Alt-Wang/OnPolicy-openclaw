#!/usr/bin/env python3
"""Benchmark the blank-spot mining workflow through OpenClaw-compatible APIs."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import statistics
import subprocess
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_PROMPT = (
    "请使用 medical-research-agent 对“结直肠癌类器官用于化疗耐药机制研究”做一次空白点挖掘。\n"
    "必须实际调用该技能的 scripts/search.py 进行文献检索；为评估端到端速度，请只做一次调用，"
    "传入 6-8 个关键词并使用 --output 保存结果。\n"
    "不要读取完整 JSON，优先使用命令行摘要生成简版 Markdown 报告："
    "3 个研究方向、3 个知识缺口、3 条参考文献线索。\n"
    "禁止读取或抽查输出 JSON，也不要额外运行统计脚本；用一次检索命令返回的 compact summary 完成。\n"
    "不要仅凭常识直接回答；若检索失败，也要说明已尝试的检索命令和失败原因。"
)
DEFAULT_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "http://localhost:8080")
DEFAULT_OUTPUT_DIR = Path(os.getenv("NANOBOT_BENCHMARK_DIR", ".hermes/benchmarks"))
FULL_CHAIN_TOOL_MARKERS = (
    "medical-research-agent",
    "scripts/search.py",
    "search.py",
    "searchdocument",
    "infox-med",
)
FULL_CHAIN_REPORT_REQUIRED_MARKERS = ("研究方向", "知识缺口")
FULL_CHAIN_REFERENCE_MARKERS = ("参考文献", "reference", "references")


@dataclasses.dataclass
class BenchmarkStep:
    name: str
    elapsed_ms: float
    state: str | None = None
    event: str | None = None
    text_chars: int = 0
    usage: dict[str, int] | None = None
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }
        if self.state:
            payload["state"] = self.state
        if self.event:
            payload["event"] = self.event
        if self.text_chars:
            payload["text_chars"] = self.text_chars
        if self.usage:
            payload["usage"] = self.usage
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclasses.dataclass
class BenchmarkResult:
    run_id: str
    backend_label: str
    runtime_mode: str
    startup_state: str
    status: str
    total_ms: float
    auth_ms: float | None = None
    send_ms: float | None = None
    first_event_ms: float | None = None
    first_visible_delta_ms: float | None = None
    prewarm_ms: float | None = None
    first_tool_ms: float | None = None
    last_tool_ms: float | None = None
    completion_ms: float | None = None
    final_output: str = ""
    final_output_chars: int = 0
    event_count: int = 0
    usage: dict[str, int] | None = None
    estimated_cost_usd: float | None = None
    session_key: str = ""
    platform_run_id: str = ""
    prompt_hash: str = ""
    model: str = ""
    provider: str = ""
    base_url: str = ""
    started_at: str = ""
    full_chain: bool = False
    chain_checks: dict[str, Any] | None = None
    steps: list[BenchmarkStep] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["total_ms"] = round(self.total_ms, 1)
        for key in (
            "auth_ms",
            "send_ms",
            "first_event_ms",
            "first_visible_delta_ms",
            "prewarm_ms",
            "first_tool_ms",
            "last_tool_ms",
            "completion_ms",
        ):
            if payload[key] is not None:
                payload[key] = round(payload[key], 1)
        if self.steps is not None:
            payload["steps"] = [step.to_dict() for step in self.steps]
        return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any] | list[Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=request_headers, method=method)
    transient_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body)
            except json.JSONDecodeError:
                detail = {"detail": body or f"HTTP {exc.code}"}
            raise RuntimeError(f"request failed ({exc.code}): {detail}") from exc
        except (ConnectionResetError, TimeoutError, URLError, OSError) as exc:
            transient_error = exc
            if attempt == 2:
                break
            time.sleep(0.5)
    raise RuntimeError(f"request failed (transport): {transient_error}") from transient_error


def register_or_login(
    *,
    base_url: str,
    username: str,
    password: str,
    runtime_mode: str,
) -> str:
    email = f"{username}@benchmark.local"
    try:
        _json_request(
            f"{base_url.rstrip('/')}/api/auth/register",
            method="POST",
            payload={
                "username": username,
                "email": email,
                "password": password,
                "runtime_mode": runtime_mode,
            },
        )
    except RuntimeError:
        pass

    login = _json_request(
        f"{base_url.rstrip('/')}/api/auth/login",
        method="POST",
        payload={"username": username, "password": password},
    )
    if not isinstance(login, dict) or not login.get("access_token"):
        raise RuntimeError(f"login did not return access_token: {login}")
    return str(login["access_token"])


def build_session_key(agent_id: str = "main") -> str:
    return f"agent:{agent_id}:bench-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def _message_text_chars(message: Any) -> int:
    if isinstance(message, str):
        return len(message)
    if not isinstance(message, dict):
        return 0
    content = message.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                total += len(item["text"])
        return total
    return 0


def _truncate_detail(value: Any, *, limit: int = 4000) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "...[truncated]"
    return value


def _event_detail(payload: dict[str, Any], inner: dict[str, Any]) -> dict[str, Any] | None:
    detail: dict[str, Any] = {}
    for source in (payload, inner):
        for key in (
            "status",
            "error",
            "detail",
            "tool",
            "preview",
            "duration",
            "toolCallId",
            "tool_call_id",
            "name",
        ):
            value = source.get(key)
            if value:
                detail[key] = _truncate_detail(value)
    output = inner.get("output") or payload.get("output")
    output_chars = _message_text_chars(output)
    if output_chars:
        detail["output_chars"] = output_chars
        if isinstance(output, str):
            detail["output"] = output
        elif isinstance(output, dict):
            content = output.get("content")
            if isinstance(content, str):
                detail["output"] = content
    elif isinstance(output, str) and output:
        detail["output_chars"] = len(output)
        detail["output"] = output
    return detail or None


def _probe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _step_probe_text(step: BenchmarkStep) -> str:
    return "\n".join(
        part
        for part in (
            step.name,
            step.event or "",
            _probe_text(step.detail),
        )
        if part
    )


def _is_user_session_step(step: BenchmarkStep) -> bool:
    detail = step.detail if isinstance(step.detail, dict) else {}
    return step.name == "session.user" or (
        step.name.startswith("session.") and str(detail.get("role") or "").lower() == "user"
    )


def _chain_probe_text(step: BenchmarkStep) -> str:
    if _is_user_session_step(step):
        return ""
    return _step_probe_text(step)


def _looks_like_completed_status(value: Any) -> bool:
    status = str(value or "").strip().lower()
    return status in {"ok", "complete", "completed", "success", "succeeded", "done"}


def _looks_like_error_status(value: Any) -> bool:
    status = str(value or "").strip().lower()
    return status in {"error", "failed", "failure", "cancelled", "canceled"}


def analyze_full_chain(steps: list[BenchmarkStep]) -> dict[str, Any]:
    """Check whether the benchmark observed the full medical research workflow."""
    tool_steps = [
        step
        for step in steps
        if "tool" in step.name.lower() or "tool" in (step.event or "").lower()
    ]
    terminal_steps = [
        step
        for step in tool_steps
        if "terminal" in _step_probe_text(step).lower()
        or "process" in _step_probe_text(step).lower()
    ]
    probe = "\n".join(_chain_probe_text(step) for step in steps)
    lower_probe = probe.lower()
    output_probe = "\n".join(
        _probe_text((step.detail or {}).get("output"))
        for step in steps
        if isinstance(step.detail, dict) and not _is_user_session_step(step)
    )
    lower_output_probe = output_probe.lower()
    run_completed = any(step.name == "run.completed" for step in steps)
    search_tool_evidence = any(marker in lower_probe for marker in FULL_CHAIN_TOOL_MARKERS)
    pending_search_tools = 0
    search_tool_success = False
    for step in tool_steps:
        step_text = _step_probe_text(step).lower()
        step_name = step.name.lower()
        detail = step.detail if isinstance(step.detail, dict) else {}
        has_error = bool(detail.get("error"))
        is_search_command = "search.py" in step_text
        if is_search_command and "tool.completed" in step_name:
            search_tool_success = search_tool_success or not has_error
            continue
        if is_search_command:
            pending_search_tools += 1
            continue
        if pending_search_tools and "tool.completed" in step_name:
            pending_search_tools -= 1
            search_tool_success = search_tool_success or not has_error
    transcript_search_success = search_tool_evidence and any(
        marker in lower_output_probe
        for marker in (
            "检索成功",
            "结果：",
            "去重文献",
            "pmid",
            "search results",
            "references",
        )
    )
    report_shape_evidence = all(
        marker in output_probe for marker in FULL_CHAIN_REPORT_REQUIRED_MARKERS
    ) and any(marker.lower() in output_probe.lower() for marker in FULL_CHAIN_REFERENCE_MARKERS)

    missing = []
    if not run_completed:
        missing.append("run.completed")
    if not search_tool_evidence:
        missing.append("search_tool_evidence")
    if not (search_tool_success or transcript_search_success):
        missing.append("search_tool_success")
    if not report_shape_evidence:
        missing.append("report_shape_evidence")

    first_tool_ms = min((step.elapsed_ms for step in tool_steps), default=None)
    last_tool_ms = max((step.elapsed_ms for step in tool_steps), default=None)
    return {
        "full_chain": not missing,
        "run_completed": run_completed,
        "tool_events": len(tool_steps),
        "terminal_tool_events": len(terminal_steps),
        "search_tool_evidence": search_tool_evidence,
        "search_tool_success": search_tool_success or transcript_search_success,
        "raw_tool_success": search_tool_success,
        "transcript_search_success": transcript_search_success,
        "report_shape_evidence": report_shape_evidence,
        "first_tool_ms": round(first_tool_ms, 1) if first_tool_ms is not None else None,
        "last_tool_ms": round(last_tool_ms, 1) if last_tool_ms is not None else None,
        "missing": missing,
    }


def extract_usage(payload: Any) -> dict[str, int]:
    if isinstance(payload, dict):
        candidate = payload.get("usage")
        if isinstance(candidate, dict):
            usage = {
                key: int(value)
                for key, value in candidate.items()
                if key.endswith("_tokens") and isinstance(value, int | float)
            }
            if usage:
                return usage
        for value in payload.values():
            usage = extract_usage(value)
            if usage:
                return usage
    elif isinstance(payload, list):
        for item in payload:
            usage = extract_usage(item)
            if usage:
                return usage
    return {}


def merge_usage(items: Iterable[dict[str, int] | None]) -> dict[str, int]:
    merged: dict[str, int] = defaultdict(int)
    for item in items:
        if not item:
            continue
        for key, value in item.items():
            merged[key] += int(value)
    return dict(merged)


def classify_sse_payload(payload: dict[str, Any], *, elapsed_ms: float) -> dict[str, Any]:
    event_name = str(payload.get("event") or payload.get("type") or "event")
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    state = inner.get("state") if isinstance(inner, dict) else None
    message = inner.get("message") if isinstance(inner, dict) else None
    text_chars = _message_text_chars(message)
    if isinstance(inner, dict) and text_chars == 0:
        delta = inner.get("delta")
        if isinstance(delta, str):
            text_chars = len(delta)
    if isinstance(inner, dict) and text_chars == 0:
        output = inner.get("output")
        if isinstance(output, str):
            text_chars = len(output)
        else:
            text_chars = _message_text_chars(output)
    usage = extract_usage(payload)

    name = event_name
    if isinstance(state, str) and state:
        name = f"{event_name}.{state}"
    elif event_name == "message.delta":
        name = "chat.delta"
    elif event_name == "message.completed":
        name = "chat.final"

    return BenchmarkStep(
        name=name,
        elapsed_ms=elapsed_ms,
        state=state if isinstance(state, str) else None,
        event=event_name,
        text_chars=text_chars,
        usage=usage or None,
        detail=_event_detail(payload, inner) if isinstance(inner, dict) else None,
    ).to_dict()


def _parse_sse_block(lines: list[str]) -> dict[str, Any] | None:
    data_lines = [line[5:].lstrip() for line in lines if line.startswith("data:")]
    if not data_lines:
        return None
    data = "\n".join(data_lines)
    if data == "[DONE]":
        return {"type": "done"}
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {"type": "text", "data": data}
    return payload if isinstance(payload, dict) else {"type": "data", "data": payload}


def _is_visible_delta(step: dict[str, Any]) -> bool:
    return str(step.get("name", "")).endswith(".delta") and int(step.get("text_chars") or 0) > 0


def _is_terminal_step(step: dict[str, Any]) -> bool:
    state = str(step.get("state") or "")
    name = str(step.get("name") or "")
    return state in {"final", "error", "aborted"} or name in {
        "run.completed",
        "run.failed",
        "run.cancelled",
        "chat.final",
    }


def _step_from_dict(step_dict: dict[str, Any]) -> BenchmarkStep:
    return BenchmarkStep(
        name=str(step_dict["name"]),
        elapsed_ms=float(step_dict["elapsed_ms"]),
        state=step_dict.get("state"),
        event=step_dict.get("event"),
        text_chars=int(step_dict.get("text_chars") or 0),
        usage=step_dict.get("usage"),
        detail=step_dict.get("detail"),
    )


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    content = value.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts)
    return ""


def _step_output(step: BenchmarkStep) -> str:
    detail = step.detail if isinstance(step.detail, dict) else {}
    output = detail.get("output")
    return output if isinstance(output, str) else ""


def _is_assistant_session_step(step: BenchmarkStep) -> bool:
    detail = step.detail if isinstance(step.detail, dict) else {}
    return step.name == "session.assistant" or (
        step.name.startswith("session.") and str(detail.get("role") or "").lower() == "assistant"
    )


def _assistant_session_outputs(steps: list[BenchmarkStep]) -> list[str]:
    outputs = []
    for step in steps:
        output = _step_output(step)
        if _is_assistant_session_step(step) and output:
            outputs.append(output)
    return outputs


def _report_shape_in_text(text: str) -> bool:
    return all(marker in text for marker in FULL_CHAIN_REPORT_REQUIRED_MARKERS) and any(
        marker.lower() in text.lower() for marker in FULL_CHAIN_REFERENCE_MARKERS
    )


def _final_output(steps: list[BenchmarkStep]) -> str:
    for step in reversed(steps):
        if step.name == "run.completed":
            output = _step_output(step)
            if output:
                return output
    for step in reversed(steps):
        if _is_assistant_session_step(step):
            output = _step_output(step)
            if output:
                return output
    for step in reversed(steps):
        output = _step_output(step)
        if output:
            return output
    return ""


def _session_signature(steps: list[BenchmarkStep]) -> str:
    payload = "\n\n".join(_step_output(step) for step in steps if _step_output(step))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{len(steps)}:{digest}"


def _session_completion_candidate(
    session_steps: list[BenchmarkStep],
    *,
    elapsed_ms: float,
) -> list[BenchmarkStep] | None:
    assistant_outputs = _assistant_session_outputs(session_steps)
    final_output = assistant_outputs[-1] if assistant_outputs else ""
    if not final_output or not _report_shape_in_text(final_output):
        return None

    transcript = "\n\n---\n\n".join(assistant_outputs)
    detail: dict[str, Any] = {
        "status": "session_transcript",
        "output": final_output,
        "output_chars": len(final_output),
        "assistant_messages": len(assistant_outputs),
        "assistant_transcript_chars": len(transcript),
    }
    if transcript and transcript != final_output:
        detail["assistant_transcript"] = _truncate_detail(transcript, limit=12_000)
    candidate = session_steps + [
        BenchmarkStep(
            name="run.completed",
            elapsed_ms=elapsed_ms,
            event="run.completed",
            text_chars=len(final_output),
            detail=detail,
        )
    ]
    if analyze_full_chain(candidate)["full_chain"]:
        return candidate
    return None


def stream_run_steps(
    *,
    base_url: str,
    token: str,
    runtime_mode: str,
    run_id: str,
    started_at: float,
    max_wait_seconds: int,
) -> tuple[list[BenchmarkStep], str]:
    path = (
        "/api/shared-openclaw/runs/{run_id}/events"
        if runtime_mode == "shared"
        else "/api/openclaw/runs/{run_id}/events"
    )
    url = f"{base_url.rstrip('/')}{path.format(run_id=run_id)}?{urlencode({'token': token})}"
    request = Request(url, headers={"Accept": "text/event-stream"})
    steps: list[BenchmarkStep] = []
    status = "timeout"
    deadline = time.time() + max_wait_seconds

    with urlopen(request, timeout=max_wait_seconds + 10) as response:
        lines: list[str] = []
        while time.time() < deadline:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line:
                lines.append(line)
                continue
            payload = _parse_sse_block(lines)
            lines = []
            if payload is None:
                continue
            if payload.get("type") == "done":
                status = "completed"
                break
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            step_dict = classify_sse_payload(payload, elapsed_ms=elapsed_ms)
            step = _step_from_dict(step_dict)
            steps.append(step)
            if _is_terminal_step(step_dict):
                name = str(step_dict.get("name") or "")
                if step_dict.get("state") == "error" or name in {"run.failed", "run.cancelled"}:
                    status = "error"
                else:
                    status = "completed"
                break
    return steps, status


def steps_from_wait_payload(
    payload: dict[str, Any] | list[Any] | str,
    *,
    elapsed_ms: float,
) -> tuple[list[BenchmarkStep], str]:
    events: list[Any] = []
    if isinstance(payload, dict):
        for key in ("events", "steps"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                events = candidate
                break
    elif isinstance(payload, list):
        events = payload

    steps: list[BenchmarkStep] = []
    for event in events:
        if isinstance(event, dict):
            steps.append(_step_from_dict(classify_sse_payload(event, elapsed_ms=elapsed_ms)))

    status_value = payload.get("status") if isinstance(payload, dict) else ""
    error_value = payload.get("error") if isinstance(payload, dict) else None
    completed = _looks_like_completed_status(status_value)
    failed = bool(error_value) or _looks_like_error_status(status_value)
    if isinstance(payload, dict) and not completed and not failed:
        completed = bool(payload.get("endedAt") or payload.get("ended_at"))

    if completed or failed:
        event_name = "run.failed" if failed else "run.completed"
        output = ""
        if isinstance(payload, dict):
            output = _message_content(payload.get("message"))
            if not output:
                output = _message_content(payload.get("output"))
        completion_payload = {
            "event": event_name,
            "status": status_value,
            "error": error_value,
        }
        if output:
            completion_payload["output"] = output
        if not any(step.name in {"run.completed", "run.failed", "run.cancelled"} for step in steps):
            steps.append(
                _step_from_dict(classify_sse_payload(completion_payload, elapsed_ms=elapsed_ms))
            )

    if failed:
        return steps, "error"
    if completed:
        return steps, "completed"
    return steps, "timeout"


def wait_run_steps(
    *,
    base_url: str,
    token: str,
    runtime_mode: str,
    run_id: str,
    started_at: float,
    max_wait_seconds: int,
) -> tuple[list[BenchmarkStep], str]:
    path = (
        "/api/shared-openclaw/runs/{run_id}/wait"
        if runtime_mode == "shared"
        else "/api/openclaw/runs/{run_id}/wait"
    )
    deadline = time.perf_counter() + max_wait_seconds
    last_steps: list[BenchmarkStep] = []
    last_status = "timeout"

    while time.perf_counter() < deadline:
        remaining_seconds = max(0.001, deadline - time.perf_counter())
        timeout_ms = max(1, min(30_000, int(remaining_seconds * 1000)))
        payload = _json_request(
            f"{base_url.rstrip('/')}{path.format(run_id=quote(run_id, safe=''))}"
            f"?{urlencode({'timeoutMs': timeout_ms})}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=math.ceil(timeout_ms / 1000) + 10,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        steps, status = steps_from_wait_payload(payload, elapsed_ms=elapsed_ms)
        if steps:
            last_steps = steps
        last_status = status
        if status != "timeout":
            return steps, status
        time.sleep(min(0.5, remaining_seconds))

    return last_steps, last_status


def fetch_session_steps(
    *,
    base_url: str,
    token: str,
    runtime_mode: str,
    session_key: str,
    elapsed_ms: float,
) -> list[BenchmarkStep]:
    path = (
        "/api/shared-openclaw/sessions/{session_key}"
        if runtime_mode == "shared"
        else "/api/openclaw/sessions/{session_key}"
    )
    payload = _json_request(
        f"{base_url.rstrip('/')}{path.format(session_key=quote(session_key, safe=''))}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return []

    steps: list[BenchmarkStep] = []
    for message in payload["messages"]:
        if not isinstance(message, dict):
            continue
        content = _message_content(message)
        role = str(message.get("role") or "message")
        detail: dict[str, Any] = {"role": role}
        if content:
            detail["output"] = content
            detail["output_chars"] = len(content)
        if message.get("timestamp"):
            detail["timestamp"] = str(message["timestamp"])
        steps.append(
            BenchmarkStep(
                name=f"session.{role}",
                elapsed_ms=elapsed_ms,
                event="session.message",
                text_chars=len(content),
                detail=detail,
            )
        )
    return steps


def poll_session_completion_steps(
    *,
    base_url: str,
    token: str,
    runtime_mode: str,
    session_key: str,
    started_at: float,
    max_wait_seconds: int,
) -> tuple[list[BenchmarkStep], str]:
    deadline = time.perf_counter() + max_wait_seconds
    last_steps: list[BenchmarkStep] = []
    stable_signature = ""

    while time.perf_counter() < deadline:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        session_steps = fetch_session_steps(
            base_url=base_url,
            token=token,
            runtime_mode=runtime_mode,
            session_key=session_key,
            elapsed_ms=elapsed_ms,
        )
        if session_steps:
            last_steps = session_steps
            candidate = _session_completion_candidate(session_steps, elapsed_ms=elapsed_ms)
            if candidate:
                signature = _session_signature(session_steps)
                if signature == stable_signature:
                    return candidate, "completed"
                stable_signature = signature
            else:
                stable_signature = ""
        time.sleep(1.0)

    return last_steps, "timeout"


def prewarm_runtime(*, base_url: str, token: str, runtime_mode: str) -> float:
    path = (
        "/api/shared-openclaw/runtime/prewarm"
        if runtime_mode == "shared"
        else "/api/openclaw/runtime/prewarm"
    )
    started = time.perf_counter()
    _json_request(
        f"{base_url.rstrip('/')}{path}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    )
    return (time.perf_counter() - started) * 1000


def send_message(
    *,
    base_url: str,
    token: str,
    runtime_mode: str,
    session_key: str | None,
    prompt: str,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    if runtime_mode == "shared":
        path = "/api/shared-openclaw/chat"
        payload = {"message": prompt}
        if session_key:
            payload["session_key"] = session_key
    else:
        if not session_key:
            raise RuntimeError("dedicated runtime requires a session key")
        path = f"/api/openclaw/sessions/{session_key}/messages"
        payload = {"message": prompt}
    response = _json_request(
        f"{base_url.rstrip('/')}{path}",
        method="POST",
        payload=payload,
        headers=headers,
        timeout=180,
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"send message returned non-object response: {response}")
    return response


def estimate_cost_usd(
    usage: dict[str, int],
    *,
    input_price_per_1m: float,
    output_price_per_1m: float,
) -> float | None:
    if not usage or (input_price_per_1m <= 0 and output_price_per_1m <= 0):
        return None
    input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
    return round(
        (input_tokens / 1_000_000 * input_price_per_1m)
        + (output_tokens / 1_000_000 * output_price_per_1m),
        8,
    )


def _completion_ms(steps: list[BenchmarkStep]) -> float | None:
    if not steps:
        return None
    return round(max(step.elapsed_ms for step in steps), 1)


def run_one_benchmark(args: argparse.Namespace, *, run_index: int, prompt: str) -> BenchmarkResult:
    username = args.username or f"bench-{args.backend_label}-{args.runtime_mode}"
    started_at_iso = _now_iso()
    steps: list[BenchmarkStep] = []
    prewarm_ms = None
    auth_ms = None
    session_key = ""

    overall_started = time.perf_counter()
    try:
        auth_started = time.perf_counter()
        token = register_or_login(
            base_url=args.base_url,
            username=username,
            password=args.password,
            runtime_mode=args.runtime_mode,
        )
        auth_ms = (time.perf_counter() - auth_started) * 1000
        session_key = build_session_key(args.agent_id)
        if args.runtime_mode == "shared":
            session_key = ""

        if args.prewarm:
            prewarm_ms = prewarm_runtime(
                base_url=args.base_url,
                token=token,
                runtime_mode=args.runtime_mode,
            )
            steps.append(BenchmarkStep(name="runtime.prewarm", elapsed_ms=prewarm_ms))

        send_started = time.perf_counter()
        send_result = send_message(
            base_url=args.base_url,
            token=token,
            runtime_mode=args.runtime_mode,
            session_key=session_key,
            prompt=prompt,
        )
        send_ms = (time.perf_counter() - send_started) * 1000
        steps.append(BenchmarkStep(name="send_message", elapsed_ms=send_ms))

        platform_run_id = str(send_result.get("runId") or send_result.get("run_id") or "")
        effective_session_key = str(
            send_result.get("session_key") or send_result.get("sessionKey") or session_key
        )
        run_steps: list[BenchmarkStep] = []
        status = "no_run_id"
        if platform_run_id:
            use_sse_stream = args.backend_label != "openclaw"
            if use_sse_stream:
                run_steps, status = stream_run_steps(
                    base_url=args.base_url,
                    token=token,
                    runtime_mode=args.runtime_mode,
                    run_id=platform_run_id,
                    started_at=send_started,
                    max_wait_seconds=args.max_wait_seconds,
                )
            needs_wait_fallback = status != "completed" or not run_steps
            if needs_wait_fallback and not use_sse_stream and effective_session_key:
                session_steps, session_status = poll_session_completion_steps(
                    base_url=args.base_url,
                    token=token,
                    runtime_mode=args.runtime_mode,
                    session_key=effective_session_key,
                    started_at=send_started,
                    max_wait_seconds=args.max_wait_seconds,
                )
                if session_steps:
                    run_steps = session_steps
                if session_status == "completed":
                    status = "completed"
                    needs_wait_fallback = False
                else:
                    status = session_status
                    needs_wait_fallback = False
            if needs_wait_fallback and not run_steps and effective_session_key:
                session_steps, session_status = poll_session_completion_steps(
                    base_url=args.base_url,
                    token=token,
                    runtime_mode=args.runtime_mode,
                    session_key=effective_session_key,
                    started_at=send_started,
                    max_wait_seconds=args.max_wait_seconds,
                )
                if session_status == "completed":
                    run_steps = session_steps
                    status = "completed"
                    needs_wait_fallback = False
            if needs_wait_fallback:
                wait_steps, wait_status = wait_run_steps(
                    base_url=args.base_url,
                    token=token,
                    runtime_mode=args.runtime_mode,
                    run_id=platform_run_id,
                    started_at=send_started,
                    max_wait_seconds=args.max_wait_seconds,
                )
                if wait_steps:
                    if run_steps:
                        run_steps.extend(wait_steps)
                    else:
                        run_steps = wait_steps
                if wait_status != "timeout" or status == "timeout":
                    status = wait_status
            if effective_session_key:
                chain_preview = analyze_full_chain(run_steps)
                has_visible_output = any(step.text_chars > 0 for step in run_steps)
                if not has_visible_output or not chain_preview["report_shape_evidence"]:
                    session_elapsed_ms = (time.perf_counter() - send_started) * 1000
                    session_steps = fetch_session_steps(
                        base_url=args.base_url,
                        token=token,
                        runtime_mode=args.runtime_mode,
                        session_key=effective_session_key,
                        elapsed_ms=session_elapsed_ms,
                    )
                    if session_steps:
                        run_steps.extend(session_steps)
            steps.extend(run_steps)

        step_dicts = [step.to_dict() for step in run_steps]
        first_event_ms = run_steps[0].elapsed_ms if run_steps else None
        visible_steps = [
            step
            for step, data in zip(run_steps, step_dicts, strict=False)
            if _is_visible_delta(data)
        ]
        first_visible_delta_ms = visible_steps[0].elapsed_ms if visible_steps else None
        has_visible_output = any(step.text_chars > 0 for step in run_steps)
        if status == "completed" and not has_visible_output:
            status = "completed_no_output"
        chain_checks = analyze_full_chain(run_steps)
        full_chain = bool(chain_checks["full_chain"])
        if status == "completed" and args.require_full_chain and not full_chain:
            status = "incomplete_chain"
        usage = merge_usage(step.usage for step in steps)
        total_ms = (time.perf_counter() - overall_started) * 1000
        first_tool_ms = chain_checks.get("first_tool_ms")
        last_tool_ms = chain_checks.get("last_tool_ms")
        final_output = _final_output(run_steps)

        return BenchmarkResult(
            run_id=f"{args.backend_label}-{args.runtime_mode}-{args.startup_state}-{run_index}",
            backend_label=args.backend_label,
            runtime_mode=args.runtime_mode,
            startup_state=args.startup_state,
            status=status,
            total_ms=total_ms,
            auth_ms=auth_ms,
            send_ms=send_ms,
            first_event_ms=first_event_ms,
            first_visible_delta_ms=first_visible_delta_ms,
            prewarm_ms=prewarm_ms,
            first_tool_ms=first_tool_ms,
            last_tool_ms=last_tool_ms,
            completion_ms=_completion_ms(run_steps),
            final_output=final_output,
            final_output_chars=len(final_output),
            event_count=len(run_steps),
            usage=usage or None,
            estimated_cost_usd=estimate_cost_usd(
                usage,
                input_price_per_1m=args.input_price_per_1m,
                output_price_per_1m=args.output_price_per_1m,
            ),
            session_key=effective_session_key,
            platform_run_id=platform_run_id,
            prompt_hash=prompt_hash(prompt),
            model=args.model,
            provider=args.provider,
            base_url=args.base_url,
            started_at=started_at_iso,
            full_chain=full_chain,
            chain_checks=chain_checks,
            steps=steps,
        )
    except Exception as exc:
        return BenchmarkResult(
            run_id=f"{args.backend_label}-{args.runtime_mode}-{args.startup_state}-{run_index}",
            backend_label=args.backend_label,
            runtime_mode=args.runtime_mode,
            startup_state=args.startup_state,
            status="error",
            total_ms=(time.perf_counter() - overall_started) * 1000,
            auth_ms=auth_ms,
            prewarm_ms=prewarm_ms,
            session_key=session_key,
            prompt_hash=prompt_hash(prompt),
            model=args.model,
            provider=args.provider,
            base_url=args.base_url,
            started_at=started_at_iso,
            steps=steps,
            error=str(exc),
        )


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if percentile == 50:
        return round(float(statistics.median(values)), 1)
    index = max(0, min(len(values) - 1, math.ceil(len(values) * percentile / 100) - 1))
    return round(float(values[index]), 1)


def summarize_results(results: list[BenchmarkResult]) -> dict[tuple[str, str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[BenchmarkResult]] = defaultdict(list)
    for result in results:
        grouped[(result.backend_label, result.runtime_mode, result.startup_state)].append(result)

    summary: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, rows in grouped.items():
        completed = [row for row in rows if row.status == "completed"]
        full_chain = [row for row in completed if row.full_chain]
        total_tokens = sum((row.usage or {}).get("total_tokens", 0) for row in rows)
        summary[key] = {
            "runs": len(rows),
            "completed": len(completed),
            "full_chain": len(full_chain),
            "total_ms_p50": _percentile([row.total_ms for row in completed], 50),
            "total_ms_p90": _percentile([row.total_ms for row in completed], 90),
            "auth_ms_p50": _percentile(
                [row.auth_ms for row in completed if row.auth_ms is not None],
                50,
            ),
            "prewarm_ms_p50": _percentile(
                [row.prewarm_ms for row in completed if row.prewarm_ms is not None],
                50,
            ),
            "send_ms_p50": _percentile(
                [row.send_ms for row in completed if row.send_ms is not None],
                50,
            ),
            "first_event_ms_p50": _percentile(
                [row.first_event_ms for row in completed if row.first_event_ms is not None],
                50,
            ),
            "first_visible_delta_ms_p50": _percentile(
                [
                    row.first_visible_delta_ms
                    for row in completed
                    if row.first_visible_delta_ms is not None
                ],
                50,
            ),
            "first_tool_ms_p50": _percentile(
                [row.first_tool_ms for row in completed if row.first_tool_ms is not None],
                50,
            ),
            "last_tool_ms_p50": _percentile(
                [row.last_tool_ms for row in completed if row.last_tool_ms is not None],
                50,
            ),
            "completion_ms_p50": _percentile(
                [row.completion_ms for row in completed if row.completion_ms is not None],
                50,
            ),
            "total_tokens": total_tokens,
        }
    return summary


def write_jsonl(path: Path, results: list[BenchmarkResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def write_markdown_report(path: Path, results: list[BenchmarkResult], *, prompt_hash: str) -> None:
    summary = summarize_results(results)
    lines = [
        "# Blank Spot Benchmark",
        "",
        f"- Generated at: {_now_iso()}",
        f"- Git commit: `{current_git_commit()}`",
        f"- Prompt hash: `{prompt_hash}`",
        "",
        "## Timing Definitions",
        "",
        "- `total_ms`: harness end-to-end wall time, including auth/login, optional prewarm, "
        "send, wait/poll, and final evidence fetch.",
        "- `auth_ms`, `prewarm_ms`, and `send_ms`: direct request durations.",
        "- `first_event_ms`, `first_visible_delta_ms`, `first_tool_ms`, `last_tool_ms`, and "
        "`completion_ms`: elapsed time from message send start.",
        "- `full chain`: completed runs with observed search-tool evidence and "
        "report-shape evidence.",
        "",
        "## Summary",
        "",
        "| backend | runtime | startup | runs | completed | full chain | total p50 ms | "
        "total p90 ms | auth p50 ms | prewarm p50 ms | send p50 ms | first event p50 ms | "
        "first visible p50 ms | first tool p50 ms | last tool p50 ms | "
        "completion p50 ms | tokens |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        "---: | ---: | ---: | ---: | ---: |",
    ]
    for (backend, runtime, startup), row in sorted(summary.items()):
        lines.append(
            "| "
            + " | ".join(
                [
                    backend,
                    runtime,
                    startup,
                    _format_cell(row["runs"]),
                    _format_cell(row["completed"]),
                    _format_cell(row["full_chain"]),
                    _format_cell(row["total_ms_p50"]),
                    _format_cell(row["total_ms_p90"]),
                    _format_cell(row["auth_ms_p50"]),
                    _format_cell(row["prewarm_ms_p50"]),
                    _format_cell(row["send_ms_p50"]),
                    _format_cell(row["first_event_ms_p50"]),
                    _format_cell(row["first_visible_delta_ms_p50"]),
                    _format_cell(row["first_tool_ms_p50"]),
                    _format_cell(row["last_tool_ms_p50"]),
                    _format_cell(row["completion_ms_p50"]),
                    _format_cell(row["total_tokens"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Run Phase Details",
            "",
            "| run | backend | runtime | startup | status | total ms | auth ms | prewarm ms | "
            "send ms | first event ms | first visible ms | first tool ms | last tool ms | "
            "completion ms | events | full chain | final chars | tokens |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.run_id}`",
                    result.backend_label,
                    result.runtime_mode,
                    result.startup_state,
                    result.status,
                    _format_cell(result.total_ms),
                    _format_cell(result.auth_ms),
                    _format_cell(result.prewarm_ms),
                    _format_cell(result.send_ms),
                    _format_cell(result.first_event_ms),
                    _format_cell(result.first_visible_delta_ms),
                    _format_cell(result.first_tool_ms),
                    _format_cell(result.last_tool_ms),
                    _format_cell(result.completion_ms),
                    _format_cell(result.event_count),
                    str(result.full_chain).lower(),
                    _format_cell(result.final_output_chars),
                    _format_cell((result.usage or {}).get("total_tokens")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Runs", ""])
    for result in results:
        lines.append(
            f"- `{result.run_id}` status={result.status} total_ms={result.total_ms:.1f} "
            f"auth_ms={_format_cell(result.auth_ms)} "
            f"prewarm_ms={_format_cell(result.prewarm_ms)} "
            f"send_ms={_format_cell(result.send_ms)} "
            f"first_event_ms={_format_cell(result.first_event_ms)} "
            f"first_visible_delta_ms={_format_cell(result.first_visible_delta_ms)} "
            f"first_tool_ms={_format_cell(result.first_tool_ms)} "
            f"last_tool_ms={_format_cell(result.last_tool_ms)} "
            f"completion_ms={_format_cell(result.completion_ms)} "
            f"final_output_chars={_format_cell(result.final_output_chars)} "
            f"events={result.event_count} full_chain={str(result.full_chain).lower()}"
        )
        missing = (result.chain_checks or {}).get("missing")
        if missing:
            lines.append(f"  - missing: `{','.join(str(item) for item in missing)}`")
        if result.error:
            lines.append(f"  - error: `{result.error}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return args.prompt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--backend-label",
        default="hermes",
        choices=["hermes", "openclaw", "other"],
    )
    parser.add_argument("--runtime-mode", default="dedicated", choices=["dedicated", "shared"])
    parser.add_argument("--startup-state", default="warm", choices=["cold", "warm"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default=os.getenv("NANOBOT_BENCH_PASSWORD", "bench123456"))
    parser.add_argument("--agent-id", default="main")
    parser.add_argument("--model", default=os.getenv("NANOBOT_BENCH_MODEL", ""))
    parser.add_argument("--provider", default=os.getenv("NANOBOT_BENCH_PROVIDER", ""))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-wait-seconds", type=int, default=300)
    parser.add_argument("--input-price-per-1m", type=float, default=0.0)
    parser.add_argument("--output-price-per-1m", type=float, default=0.0)
    parser.add_argument("--prewarm", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-full-chain", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    if args.prewarm is None:
        args.prewarm = args.startup_state == "warm"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prompt = load_prompt(args)
    run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir / run_stamp
    results = [
        run_one_benchmark(args, run_index=index + 1, prompt=prompt)
        for index in range(max(1, args.runs))
    ]
    jsonl_path = output_dir / "runs.jsonl"
    report_path = output_dir / "report.md"
    write_jsonl(jsonl_path, results)
    write_markdown_report(report_path, results, prompt_hash=prompt_hash(prompt))
    print(f"jsonl={jsonl_path}")
    print(f"report={report_path}")
    failed = [result for result in results if result.status != "completed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
