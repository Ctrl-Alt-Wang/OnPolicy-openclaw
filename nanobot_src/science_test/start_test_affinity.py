#!/usr/bin/env python3
"""测试会话亲和性：同一session连续两次对话，第二次问第一次问了什么。

验证session affinity机制：两次请求应路由到同一个容器，容器内有对话历史。
"""

import argparse
import json
import sys
import time

import httpx

DEFAULT_URL = "http://localhost:8080/api/science/chat"

QUESTION_1 = "我最喜欢的颜色是蓝色，请记住这一点。"
QUESTION_2 = "我刚才说我最喜欢的颜色是什么？请直接回答颜色名称。"


def send_chat(url: str, session_id: str, question: str, link_id: str) -> str:
    """发送请求并提取完整回复文本。"""
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
    full_text = ""
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
            if msg == "[stop]":
                break
            if isinstance(msg, str) and msg:
                full_text += msg
    return full_text


def main():
    parser = argparse.ArgumentParser(description="测试 /api/science/chat 会话亲和性")
    parser.add_argument("--url", default=DEFAULT_URL, help="API 地址，默认 http://localhost:8080/api/science/chat")
    args = parser.parse_args()

    session_id = f"affinity-test-{int(time.time())}"
    print("=== 会话亲和性测试 ===")
    print(f"URL: {args.url}")
    print(f"SessionID: {session_id}\n")

    # 第一轮
    print("=== 1. 第一轮对话 ===")
    print(f"问题: {QUESTION_1}")
    answer1 = send_chat(args.url, session_id, QUESTION_1, "link-1")
    print(f"回答: {answer1}")
    print("=== 第一轮完成 ===\n")

    time.sleep(2)

    # 第二轮
    print("=== 2. 第二轮对话（验证会话记忆） ===")
    print(f"问题: {QUESTION_2}")
    answer2 = send_chat(args.url, session_id, QUESTION_2, "link-2")
    print(f"回答: {answer2}")
    print("=== 第二轮完成 ===\n")

    # 判断结果
    if "蓝" in answer2:
        print("✅ 会话亲和性生效！第二次回答中包含「蓝」，说明两次请求路由到了同一个容器。")
        return 0
    else:
        print("❌ 会话亲和性可能未生效，第二次回答中未包含「蓝」。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
