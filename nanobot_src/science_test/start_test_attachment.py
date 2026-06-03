#!/usr/bin/env python3
"""
测试 /api/science/chat 接口的附件读取与拼接功能

验证 _extract_content_text() 对 multi-content 格式的处理：
  - content 为数组，包含 type=text 和 type=file 的 block
  - type=file 的 block 会下载 .docx 并提取文本拼接到消息中
  - attachment 字段也包含文件信息

依赖: pip install httpx
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime
from urllib.parse import quote

import httpx

# 测试用的 docx 文件 URL（与用户提供的请求一致）
DOCX_URL = (
    "https://infoxmed20.infox-med.com/infoxmed20/"
    "1779420968885-pc-【修改后清咳】呼吸道感染咳嗽咳痰中西医结合临床典型病例问卷调研（清咳 长问卷）(3).docx"
)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def build_payload(
    session_id: str,
    link_id: str,
    user_text: str,
    file_url: str,
) -> dict:
    """构建 multi-content 格式的请求体，模拟前端发送的附件消息。"""
    return {
        "linkId": link_id,
        "sessionId": session_id,
        "userId": 1,
        "functionId": 1,
        "type": 0,
        "attachment": {
            "filetype": "file",
            "url": file_url,
        },
        "messages": [
            {
                "role": "user",
                "content": [
                    {"text": user_text, "type": "text"},
                    {"type": "file", "url": file_url},
                ],
            }
        ],
        "callTools": True,
        "XAPIVersion": 1,
    }


async def send_chat_and_collect(
    base_url: str,
    payload: dict,
    timeout: int,
    print_stream: bool,
) -> tuple[str, str, dict]:
    """发送 chat 请求，收集完整回复。返回 (full_text, reasoning, last_chunk)。

    使用 aiter_bytes() + 手动行缓冲实现真正的流式读取，
    与服务端 _stream() 的 SSE 解析逻辑保持一致。
    """
    chat_url = f"{base_url}/api/science/chat"

    print(f"[{_ts()}] 发送请求到: {chat_url}")
    print(f"[{_ts()}] payload:")
    for line in json.dumps(payload, ensure_ascii=False, indent=2).splitlines():
        print(f"[{_ts()}]   {line}")
    print()

    contents: list[str] = []
    reasoning_parts: list[str] = []
    last_chunk: dict = {}
    chunk_count = 0
    start = time.time()
    first_token_time = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream("POST", chat_url, json=payload) as resp:
            print(f"[{_ts()}] HTTP 状态: {resp.status_code}")
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"[{_ts()}] 请求失败: {body.decode(errors='replace')[:500]}")
                return "", "", {}

            print(f"[{_ts()}] 开始接收 SSE 流...\n")

            # 使用 aiter_bytes() + 手动行缓冲，实现真正的实时流式输出
            # httpx 的 aiter_lines() 内部有额外缓冲，无法逐 token 到达即输出
            buffer = ""
            async for raw_bytes in resp.aiter_bytes():
                buffer += raw_bytes.decode("utf-8", errors="ignore")
                while "\n\n" in buffer:
                    raw_block, buffer = buffer.split("\n\n", 1)

                    # 提取 event 类型（如 event: hermes.tool.progress）
                    current_event = ""
                    for line in raw_block.splitlines():
                        if line.startswith("event:"):
                            current_event = line[6:].strip()

                    # 提取 data 行
                    data_lines = [
                        line[5:].strip()
                        for line in raw_block.splitlines()
                        if line.startswith("data:")
                    ]
                    if not data_lines:
                        continue
                    data_str = "\n".join(data_lines)
                    if data_str == "[DONE]":
                        break

                    chunk_count += 1
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue

                    last_chunk = chunk
                    msg = chunk.get("message", "")
                    rmsg = chunk.get("reasoningMessage", "")

                    if msg == "[stop]":
                        break

                    # --- 实时流式打印 ---
                    if isinstance(msg, str) and msg:
                        if first_token_time is None:
                            first_token_time = time.time() - start
                        contents.append(msg)
                        if print_stream:
                            sys.stdout.write(msg)
                            sys.stdout.flush()

                    if isinstance(rmsg, str) and rmsg:
                        reasoning_parts.append(rmsg)
                        if print_stream:
                            sys.stdout.write(f"\n[{_ts()}] \033[90m[reasoning] {rmsg}\033[0m\n")
                            sys.stdout.flush()

    elapsed = time.time() - start
    full_text = "".join(contents)
    full_reasoning = "".join(reasoning_parts)

    if print_stream and contents:
        sys.stdout.write("\n")
        sys.stdout.flush()

    print(f"\n[{_ts()}] 流完成:")
    print(f"[{_ts()}]   总耗时:       {elapsed:.1f}s")
    if first_token_time is not None:
        print(f"[{_ts()}]   首token:      {first_token_time:.2f}s")
    print(f"[{_ts()}]   chunk 数量:   {chunk_count}")
    print(f"[{_ts()}]   正文长度:     {len(full_text)} 字符")
    print(f"[{_ts()}]   reasoning:    {len(full_reasoning)} 字符")

    return full_text, full_reasoning, last_chunk


async def test_attachment_extraction(
    base_url: str,
    timeout: int,
    print_stream: bool,
    file_url: str,
    user_text: str,
):
    """核心测试：验证附件 .docx 被正确下载并提取文本拼接到消息中。"""
    session_id = f"attach-test-{uuid.uuid4().hex[:8]}"
    link_id = f"attach-link-{uuid.uuid4().hex[:6]}"

    print(f"[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]   附件读取与拼接测试")
    print(f"[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}] sessionId: {session_id}")
    print(f"[{_ts()}] linkId:    {link_id}")
    print(f"[{_ts()}] 用户文本:  {user_text}")
    print(f"[{_ts()}] 附件URL:   {file_url}")
    print()

    # Step 1: 发送带附件的请求
    print(f"[{_ts()}] [1/2] 发送带附件请求（multi-content 格式）...")
    payload = build_payload(session_id, link_id, user_text, file_url)
    full_text, reasoning, last_chunk = await send_chat_and_collect(
        base_url, payload, timeout, print_stream,
    )

    if not full_text:
        print(f"\n[{_ts()}] ❌ 测试失败: 未收到任何回复内容")
        return False

    # Step 2: 验证结果
    print(f"\n[{_ts()}] [2/2] 验证结果...")
    print(f"[{_ts()}]   完整回复内容:")
    print(f"[{_ts()}]   {'-' * 50}")
    for line in full_text.splitlines():
        print(f"[{_ts()}]   {line}")
    print(f"[{_ts()}]   {'-' * 50}")

    # 对照：发送纯文本（不带附件）的请求，对比回复
    print(f"\n[{_ts()}]   对照测试：发送纯文本请求（无附件）...")
    session_id2 = f"attach-test-{uuid.uuid4().hex[:8]}"
    link_id2 = f"attach-link-{uuid.uuid4().hex[:6]}"
    plain_payload = {
        "linkId": link_id2,
        "sessionId": session_id2,
        "userId": 1,
        "functionId": 1,
        "type": 0,
        "attachment": {},
        "messages": [{"role": "user", "content": user_text}],
        "callTools": True,
        "XAPIVersion": 1,
    }
    plain_text, _, _ = await send_chat_and_collect(
        base_url, plain_payload, timeout, print_stream,
    )

    print(f"\n[{_ts()}]   纯文本回复长度: {len(plain_text)} 字符")
    print(f"[{_ts()}]   带附件回复长度: {len(full_text)} 字符")

    # 简单判断：带附件的回复应该包含更多上下文信息
    # 如果附件提取成功，回复通常会提到问卷、调研、咳嗽等相关内容
    attachment_keywords = ["问卷", "调研", "咳嗽", "呼吸道", "清咳", "咳痰"]
    found_keywords = [kw for kw in attachment_keywords if kw in full_text]

    print(f"\n[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]   测试汇总")
    print(f"[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]   带附件回复长度: {len(full_text)} 字符")
    print(f"[{_ts()}]   纯文本回复长度: {len(plain_text)} 字符")
    print(f"[{_ts()}]   附件关键词命中: {found_keywords if found_keywords else '无'}")

    if found_keywords:
        print(f"[{_ts()}] ✅ 附件内容成功拼接到消息中（回复包含附件关键词）")
        return True
    elif len(full_text) > len(plain_text) * 1.2:
        print(f"[{_ts()}] ⚠️  附件可能已拼接（回复明显更长），但未命中预期关键词")
        return True
    else:
        print(f"[{_ts()}] ⚠️  无法确认附件是否成功拼接，请检查 hermes 日志")
        return False


async def test_content_formats(base_url: str, timeout: int):
    """测试不同的 content 格式都能正确处理。"""
    session_id = f"fmt-test-{uuid.uuid4().hex[:8]}"

    test_cases = [
        {
            "name": "纯字符串 content",
            "messages": [{"role": "user", "content": "say hello in one word"}],
        },
        {
            "name": "multi-content (仅 text)",
            "messages": [{"role": "user", "content": [{"text": "say hello in one word", "type": "text"}]}],
        },
    ]

    print(f"\n[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]   Content 格式兼容性测试")
    print(f"[{_ts()}] {'=' * 55}")

    all_ok = True
    for i, tc in enumerate(test_cases):
        print(f"\n[{_ts()}] [{i+1}/{len(test_cases)}] {tc['name']}")
        payload = {
            "linkId": f"fmt-link-{i}",
            "sessionId": f"{session_id}-{i}",
            "userId": 1,
            "functionId": 1,
            "type": 0,
            "attachment": {},
            "messages": tc["messages"],
            "callTools": True,
            "XAPIVersion": 1,
        }
        full_text, _, _ = await send_chat_and_collect(base_url, payload, timeout, False)
        if full_text:
            print(f"[{_ts()}]   ✅ 成功 (回复 {len(full_text)} 字符)")
        else:
            print(f"[{_ts()}]   ❌ 失败: 无回复")
            all_ok = False

    return all_ok


async def run_tests(args):
    base_url = args.url.rstrip("/")
    test_start = time.time()

    print(f"[{_ts()}] 测试目标: {base_url}")
    print(f"[{_ts()}] 超时设置: {args.timeout}s")
    print()

    # 先做格式兼容性测试
    await test_content_formats(base_url, args.timeout)

    # 核心：附件提取测试
    result = await test_attachment_extraction(
        base_url=base_url,
        timeout=args.timeout,
        print_stream=args.print_stream,
        file_url=args.file_url,
        user_text=args.prompt,
    )

    total_time = time.time() - test_start
    print(f"\n[{_ts()}] 总耗时: {total_time:.1f}s")
    print(f"[{_ts()}] 最终结果: {'✅ 通过' if result else '⚠️ 需人工确认'}")

    return 0 if result else 1


def main():
    parser = argparse.ArgumentParser(
        description="测试 /api/science/chat 附件读取与拼接功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认测试
  python start_test_attachment.py

  # 打印SSE流
  python start_test_attachment.py -p

  # 自定义服务地址
  python start_test_attachment.py --url http://localhost:8080

  # 自定义 prompt 和附件
  python start_test_attachment.py --prompt "分析这份文档" --file-url "https://example.com/doc.docx"
        """,
    )
    parser.add_argument(
        "--url", type=str,
        default="https://scienceapi.yifuzhishi.com",
        help="服务基础地址，默认 https://scienceapi.yifuzhishi.com",
    )
    parser.add_argument(
        "--prompt", type=str,
        default="分析这份文档的内容",
        help="用户文本内容",
    )
    parser.add_argument(
        "--file-url", type=str,
        default=DOCX_URL,
        help="附件 docx 文件 URL",
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="请求超时秒数，默认120",
    )
    parser.add_argument(
        "-p", "--print-stream", action="store_true",
        help="实时打印 SSE 流内容",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(run_tests(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
