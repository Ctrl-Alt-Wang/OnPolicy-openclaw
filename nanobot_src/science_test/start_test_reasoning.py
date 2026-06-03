#!/usr/bin/env python3
"""测试 reasoning 内容是否正确转发到前端。

发送一个需要思考的问题，检查 SSE 流中是否包含 reasoningMessage 字段。
"""

import argparse
import json
import sys
import time

import httpx

DEFAULT_URL = "http://localhost:8080/api/science/chat"

QUESTION = "请先思考一下，然后回答：327 是质数吗？请展示你的思考过程。"


def send_chat_collect(url: str, session_id: str, question: str, link_id: str) -> dict:
    """发送请求并收集 message 和 reasoningMessage。"""
    payload = {
        "linkId": link_id,
        "sessionId": session_id,
        "userId": 1,
        "functionId": 319,
        "messages": [{"role": "user", "content": question}],
        "type": 0,
        "attachment": {},
        "callTools": True,
        "XAPIVersion": 1,
    }
    full_message = ""
    full_reasoning = ""
    reasoning_chunks = []
    with httpx.stream("POST", url, json=payload, timeout=120) as resp:
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            msg = data.get("message", "")
            reasoning = data.get("reasoningMessage", "")
            if msg == "[stop]":
                break
            if isinstance(msg, str) and msg:
                full_message += msg
            if reasoning:
                full_reasoning += reasoning
                reasoning_chunks.append(reasoning)
    return {
        "message": full_message,
        "reasoning": full_reasoning,
        "reasoning_chunks": reasoning_chunks,
    }


def main():
    parser = argparse.ArgumentParser(description="测试 /api/science/chat reasoningMessage 转发")
    parser.add_argument("--url", default=DEFAULT_URL, help="API 地址，默认 http://localhost:8080/api/science/chat")
    args = parser.parse_args()

    session_id = f"reasoning-test-{int(time.time())}"
    print("=== Reasoning 转发测试 ===")
    print(f"URL: {args.url}")
    print(f"SessionID: {session_id}\n")

    print(f"问题: {QUESTION}")
    result = send_chat_collect(args.url, session_id, QUESTION, "link-1")

    print("\n--- 最终回答 (message) ---")
    print(result["message"][:500] if result["message"] else "(空)")

    print("\n--- 思考内容 (reasoningMessage) ---")
    print(result["reasoning"][:1000] if result["reasoning"] else "(空)")

    print(f"\n--- reasoning chunks 数量: {len(result['reasoning_chunks'])} ---")
    for i, chunk in enumerate(result["reasoning_chunks"][:10]):
        preview = chunk[:80].replace("\n", " ")
        print(f"  [{i}] {preview}")

    # 判断结果
    has_message = bool(result["message"].strip())
    has_reasoning = bool(result["reasoning"].strip())

    print("\n=== 测试结果 ===")
    print(f"message 有内容: {'✅' if has_message else '❌'}")
    print(f"reasoningMessage 有内容: {'✅' if has_reasoning else '❌'}")

    if has_message and has_reasoning:
        print("✅ Reasoning 转发生效！前端同时收到了 message 和 reasoningMessage。")
        return 0
    elif has_message and not has_reasoning:
        print("⚠️ 只收到了 message，没有 reasoningMessage。")
        print("   可能原因：模型未产生 reasoning 内容，或 Hermes 未转发。")
        return 1
    else:
        print("❌ 未收到有效内容。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
