#!/usr/bin/env python3
"""
model/chat 文件下载功能测试脚本

流程:
  1. 发送 /api/model/chat 请求，触发 agent 生成文件
  2. 解析 SSE 流，提取正文中的 markdown 下载链接
  3. 逐个请求下载链接，验证文件是否可以正常下载

依赖: pip install aiohttp
"""

import argparse
import asyncio
import json
import re
import time
import uuid
from datetime import datetime

import aiohttp

# 匹配正文中被替换后的 markdown 下载链接: [filename](/api/model/chat/file?sessionId=xxx&path=xxx)
_DOWNLOAD_LINK_RE = re.compile(
    r'\[([^\]]+)\]\((/api/model/chat/file\?[^)]+)\)'
)


def _ts() -> str:
    """返回当前时间戳字符串"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def run_chat_and_extract_links(
    base_url: str,
    prompt: str,
    timeout: int,
    print_stream: bool,
) -> tuple[str, str, list[tuple[str, str]]]:
    """发送 chat 请求，返回 (完整正文, reasoning, [(filename, url), ...])"""
    session_id = f"dl-test-{uuid.uuid4().hex[:8]}"
    link_id = f"dl-link-{uuid.uuid4().hex[:6]}"

    payload = {
        "linkId": link_id,
        "sessionId": session_id,
        "userId": 1,
        "functionId": 1,
        "messages": [{"role": "user", "content": prompt}],
        "type": 0,
        "attachment": {},
        "callTools": True,
        "XAPIVersion": 1,
    }

    contents = []
    reasoning_parts = []
    chat_url = f"{base_url}/api/model/chat"

    print(f"[{_ts()}] [1/3] 发送请求")
    print(f"[{_ts()}]       sessionId: {session_id}")
    print(f"[{_ts()}]       linkId:    {link_id}")
    print(f"[{_ts()}]       prompt:    {prompt}")
    print(f"[{_ts()}]       url:       {chat_url}")
    print(f"[{_ts()}]       payload:")
    for line in json.dumps(payload, ensure_ascii=False, indent=2).splitlines():
        print(f"[{_ts()}]         {line}")
    print()

    start = time.time()
    first_token_time = None
    chunk_count = 0

    async with aiohttp.ClientSession() as session:
        async with session.post(
            chat_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            print(f"[{_ts()}]   HTTP 状态: {resp.status}")
            print(f"[{_ts()}]   响应头:")
            for k, v in resp.headers.items():
                print(f"[{_ts()}]     {k}: {v}")
            print()

            if resp.status != 200:
                body = await resp.text()
                print(f"[{_ts()}]   请求失败: HTTP {resp.status}")
                print(f"[{_ts()}]   响应体:\n{body[:1000]}")
                return "", "", []

            print(f"[{_ts()}]   连接成功，开始接收 SSE 流...")
            print()

            async for line in resp.content:
                raw = line.decode("utf-8", errors="replace")
                stripped = raw.strip()

                if not stripped or not stripped.startswith("data: "):
                    if stripped:
                        print(f"[{_ts()}] [SSE] 非 data 行: {stripped[:200]!r}")
                    continue

                data = stripped[6:]
                if data == "[DONE]":
                    print(f"[{_ts()}] [SSE] [DONE] 结束标记")
                    break

                chunk_count += 1
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as e:
                    print(f"[{_ts()}] [SSE] JSON 解析失败: {e}")
                    print(f"[{_ts()}] [SSE] 原始数据: {data[:300]!r}")
                    continue

                if not isinstance(chunk, dict):
                    print(f"[{_ts()}] [SSE] chunk 类型不是 dict: {type(chunk)}")
                    continue

                print(f"[{_ts()}] [SSE] chunk #{chunk_count} keys={list(chunk.keys())}")
                for k, v in chunk.items():
                    v_repr = repr(v)[:200] + ("..." if len(repr(v)) > 200 else "")
                    print(f"[{_ts()}] [SSE]   {k}: {v_repr}")

                msg = chunk.get("message", "")
                rmsg = chunk.get("reasoningMessage", "")

                if msg and msg != "[stop]":
                    if isinstance(msg, str) and first_token_time is None:
                        first_token_time = time.time() - start
                        print(f"[{_ts()}]   首 token 到达: {first_token_time:.2f}s")
                    if isinstance(msg, str):
                        contents.append(msg)
                    if isinstance(msg, str) and print_stream:
                        print(msg, end="", flush=True)
                if rmsg:
                    reasoning_parts.append(rmsg)
                    if print_stream:
                        print(f"\n[{_ts()}] \033[90m[reasoning] {rmsg}\033[0m", flush=True)

    elapsed = time.time() - start
    full_content = "".join(contents)
    full_reasoning = "".join(reasoning_parts)

    if print_stream and contents:
        print()
    print()
    print(f"[{_ts()}]   流完成统计:")
    print(f"[{_ts()}]     总耗时:      {elapsed:.1f}s")
    print(f"[{_ts()}]     chunk 数量:  {chunk_count}")
    print(f"[{_ts()}]     正文长度:    {len(full_content)} 字符")
    print(f"[{_ts()}]     reasoning:   {len(full_reasoning)} 字符")
    print()

    # 打印完整正文内容
    print(f"[{_ts()}]   完整正文内容:")
    print(f"[{_ts()}]   {'-' * 50}")
    for line in full_content.splitlines():
        print(f"[{_ts()}]   {line}")
    print(f"[{_ts()}]   {'-' * 50}")
    print()

    # 打印完整 reasoning 内容
    if full_reasoning:
        print(f"[{_ts()}]   完整 reasoning 内容:")
        print(f"[{_ts()}]   {'-' * 50}")
        for line in full_reasoning.splitlines():
            print(f"[{_ts()}]   {line}")
        print(f"[{_ts()}]   {'-' * 50}")
        print()

    # 提取下载链接并打印匹配过程
    print(f"[{_ts()}]   正则匹配尝试:")
    print(f"[{_ts()}]     正则: {_DOWNLOAD_LINK_RE.pattern}")
    links = _DOWNLOAD_LINK_RE.findall(full_content)
    if links:
        print(f"[{_ts()}]     匹配成功: {len(links)} 个链接")
        for name, url in links:
            print(f"[{_ts()}]       - name={name!r}, url={url!r}")
    else:
        print(f"[{_ts()}]     未匹配到链接")
        # 尝试找出正文中的任何 markdown 链接或文件路径
        all_md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', full_content)
        if all_md_links:
            print(f"[{_ts()}]     但发现其他 markdown 链接:")
            for name, url in all_md_links:
                print(f"[{_ts()}]       - name={name!r}, url={url!r}")
        all_paths = re.findall(r'/api/model/chat/file\?[^\s\)\]]+', full_content)
        if all_paths:
            print(f"[{_ts()}]     发现可能的文件路径:")
            for p in all_paths:
                print(f"[{_ts()}]       - {p!r}")
    print()

    return full_content, full_reasoning, links


async def test_download_links(
    base_url: str,
    links: list[tuple[str, str]],
):
    """逐个测试下载链接"""
    if not links:
        print(f"\n[{_ts()}] [2/3] 未在正文中发现下载链接")
        print(f"[{_ts()}]       可能原因:")
        print(f"[{_ts()}]         - Agent 没有生成文件")
        print(f"[{_ts()}]         - 文件路径格式未被正则匹配到")
        print(f"[{_ts()}]         - prompt 未触发文件生成")
        return

    print(f"\n[{_ts()}] [2/3] 发现 {len(links)} 个下载链接:")
    for i, (name, url) in enumerate(links):
        print(f"[{_ts()}]       [{i+1}] {name} → {url}")

    print(f"\n[{_ts()}] [3/3] 测试下载...")
    async with aiohttp.ClientSession() as session:
        for i, (name, rel_url) in enumerate(links):
            full_url = f"{base_url}{rel_url}"
            print(f"\n[{_ts()}]   [{i+1}/{len(links)}] 下载: {name}")
            print(f"[{_ts()}]       URL: {full_url}")

            try:
                start = time.time()
                async with session.get(
                    full_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    elapsed = time.time() - start
                    status_code = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    content_disp = resp.headers.get("Content-Disposition", "")
                    body = await resp.read()
                    size = len(body)

                    if status_code == 200:
                        print(f"[{_ts()}]       OK: {status_code} | {size:,} bytes | {content_type} | {elapsed:.2f}s")
                        if content_disp:
                            print(f"[{_ts()}]       Content-Disposition: {content_disp}")
                        if size == 0:
                            print(f"[{_ts()}]       WARNING: 文件大小为 0")
                        elif size < 100:
                            print(f"[{_ts()}]       WARNING: 文件很小 ({size} bytes)，可能不是有效文件")
                    else:
                        error_text = body.decode("utf-8", errors="replace")[:200]
                        print(f"[{_ts()}]       FAIL: HTTP {status_code} | {error_text}")

            except asyncio.TimeoutError:
                print(f"[{_ts()}]       FAIL: 超时")
            except Exception as e:
                print(f"[{_ts()}]       FAIL: {e}")


async def run_test(args):
    base_url = args.url.rstrip("/")
    test_start = time.time()

    print(f"[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]       文件下载功能测试")
    print(f"[{_ts()}] {'=' * 55}")

    # Step 1: 发送 chat 请求并提取链接
    full_content, reasoning, links = await run_chat_and_extract_links(
        base_url=base_url,
        prompt=args.prompt,
        timeout=args.timeout,
        print_stream=args.print_stream,
    )

    if not full_content and not links:
        print(f"\n[{_ts()}] 测试终止: 未获取到任何内容")
        return

    # Step 2 & 3: 测试下载
    await test_download_links(base_url, links)

    # 汇总
    total_time = time.time() - test_start
    print(f"\n[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]       测试汇总")
    print(f"[{_ts()}] {'=' * 55}")
    print(f"[{_ts()}]   总耗时:     {total_time:.1f}s")
    print(f"[{_ts()}]   正文长度:   {len(full_content)} 字符")
    print(f"[{_ts()}]   reasoning:  {len(reasoning)} 字符")
    print(f"[{_ts()}]   下载链接数: {len(links)}")
    for name, url in links:
        print(f"[{_ts()}]     - {name}")
    print(f"[{_ts()}] {'=' * 55}")


def main():
    parser = argparse.ArgumentParser(
        description="model/chat 文件下载功能测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认测试（触发空白点挖掘，生成报告文件）
  python start_test_download.py

  # 打印SSE流内容
  python start_test_download.py -p

  # 自定义prompt
  python start_test_download.py --prompt "帮我分析肺癌免疫治疗的空白点"

  # 指定服务地址
  python start_test_download.py --url http://10.0.0.1:8080
        """
    )
    parser.add_argument("--url", type=str,
                        default="https://innovation.yifuzhishi.com",
                        help="服务基础地址（不含 /api/...），默认 https://innovation.yifuzhishi.com")
    parser.add_argument("--prompt", type=str,
                        default="帮我挖掘肺癌免疫治疗领域的研究空白点，生成报告文件",
                        help="测试 prompt（应能触发 agent 生成文件）")
    parser.add_argument("--timeout", type=int, default=300,
                        help="请求超时秒数，默认300（agent生成报告较慢）")
    parser.add_argument("-p", "--print-stream", action="store_true",
                        help="实时打印 SSE 流内容")

    args = parser.parse_args()
    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
