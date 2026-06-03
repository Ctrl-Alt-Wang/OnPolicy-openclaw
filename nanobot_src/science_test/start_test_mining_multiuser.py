#!/usr/bin/env python3
"""
OpenClaw /api/science/chat 多用户并发测试脚本
- 并发数 = 用户数 = 总请求数（每个并发发1个请求）
- 支持打印模型返回的 SSE 流内容
- 统计耗时、成功率

依赖: pip install aiohttp
"""

import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List

import aiohttp


@dataclass
class RequestResult:
    user_id: int
    session_id: str
    link_id: str
    success: bool
    status_code: int = 0
    error: str = ""
    first_token_latency: float = 0.0
    total_time: float = 0.0
    content: str = ""          # 模型返回的完整内容
    reasoning: str = ""        # reasoningMessage 内容(工具调用等)
    start_time: float = 0.0


@dataclass
class TestStats:
    total: int = 0
    success: int = 0
    fail: int = 0
    first_token_latencies: List[float] = field(default_factory=list)
    total_times: List[float] = field(default_factory=list)
    errors: defaultdict = field(default_factory=lambda: defaultdict(int))

    def print_report(self):
        print("\n" + "=" * 60)
        print("                    并发测试报告")
        print("=" * 60)
        print(f"  总请求数:  {self.total}")
        print(f"  成功:      {self.success}")
        print(f"  失败:      {self.fail}")
        print(f"  成功率:    {self.success / self.total * 100:.2f}%" if self.total else "  成功率:    0.00%")
        if self.total_times:
            avg = sum(self.total_times) / len(self.total_times)
            print(f"  平均耗时:  {avg:.3f}s")
        if self.first_token_latencies:
            avg_ft = sum(self.first_token_latencies) / len(self.first_token_latencies)
            print(f"  首token:   {avg_ft:.3f}s")
        if self.errors:
            print("  错误分布:")
            for err, cnt in sorted(self.errors.items(), key=lambda x: -x[1]):
                print(f"    [{cnt}] {err}")
        print("=" * 60)


async def send_chat_request(
    session: aiohttp.ClientSession,
    url: str,
    user_id: int,
    session_id: str,
    link_id: str,
    content: str,
    timeout: int,
    print_content: bool,
) -> RequestResult:

    result = RequestResult(
        user_id=user_id,
        session_id=session_id,
        link_id=link_id,
        success=False,
        start_time=time.time(),
    )

    payload = {
        "linkId": link_id,
        "sessionId": session_id,
        "userId": user_id,
        "functionId": 1,
        "messages": [{"role": "user", "content": content}],
        "type": 0,
        "attachment": {},
        "callTools": True,
        "XAPIVersion": 1,
    }

    first_token = False
    contents = []
    reasoning_parts = []

    try:
        async with session.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            result.status_code = resp.status

            if resp.status != 200:
                body = await resp.text()
                result.error = f"HTTP {resp.status}: {body[:200]}"
                return result

            async for line in resp.content:
                line = line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue

                data = line[6:]
                if data == "[DONE]":
                    break

                if not first_token:
                    result.first_token_latency = time.time() - result.start_time
                    first_token = True

                try:
                    chunk = json.loads(data)
                    if isinstance(chunk, dict):
                        text = ""
                        # OpenClaw 格式: {"message": "...", "reasoningMessage": "...", "type": 4}
                        if "message" in chunk:
                            msg = chunk["message"]
                            if isinstance(msg, str) and msg and msg != "[stop]":
                                text = msg
                        # 提取 reasoningMessage (工具调用进度等)
                        rmsg = chunk.get("reasoningMessage", "")
                        if rmsg:
                            reasoning_parts.append(rmsg)
                        # OpenAI 格式: {"choices": [{"delta": {"content": "..."}}]}
                        if not text and "choices" in chunk:
                            delta = chunk["choices"][0].get("delta", {})
                            text = delta.get("content", "")
                            # OpenAI reasoning_content (o1/o3 等模型)
                            rc = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                            if rc:
                                reasoning_parts.append(rc)
                        # 兼容格式: {"content": "..."}
                        if not text and "content" in chunk:
                            text = chunk["content"]
                        if text:
                            contents.append(text)
                    elif isinstance(chunk, str):
                        if chunk != "[DONE]":
                            contents.append(chunk)
                except json.JSONDecodeError:
                    if data != "[DONE]":
                        contents.append(data)

            result.total_time = time.time() - result.start_time
            result.content = "".join(contents)
            result.reasoning = "".join(reasoning_parts)
            result.success = True

    except asyncio.TimeoutError:
        result.total_time = time.time() - result.start_time
        result.error = "Timeout"
    except Exception as e:
        result.total_time = time.time() - result.start_time
        result.error = str(e)[:200]

    if print_content:
        tag = "OK" if result.success else "FAIL"
        print(f"\n--- [{tag}] user={user_id} session={session_id} time={result.total_time:.3f}s ---")
        if result.success:
            if result.reasoning:
                print(f"[reasoning] {result.reasoning}")
            print(result.content if result.content else "(无内容)")
        else:
            print(f"错误: {result.error}")

    return result


async def worker(
    session: aiohttp.ClientSession,
    url: str,
    user_id: int,
    content: str,
    timeout: int,
    print_content: bool,
    semaphore: asyncio.Semaphore,
    results: List[RequestResult],
):
    async with semaphore:
        session_id = f"stress-{user_id:03d}-{uuid.uuid4().hex[:6]}"
        link_id = f"link-{user_id:03d}"
        result = await send_chat_request(
            session, url, user_id, session_id, link_id, content, timeout, print_content
        )
        results.append(result)


async def run_test(args) -> TestStats:
    stats = TestStats()
    results: List[RequestResult] = []
    semaphore = asyncio.Semaphore(args.concurrency)

    print(f"启动测试: URL={args.url}")
    print(f"  并发数(=用户数=总请求数)={args.concurrency}")
    print(f"  Prompt='{args.prompt}'")
    print(f"  超时={args.timeout}s")
    print("-" * 60)

    test_start = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = [
            worker(session, args.url, i + 1, args.prompt, args.timeout,
                   args.print_content, semaphore, results)
            for i in range(args.concurrency)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    stats.total = len(results)
    stats.success = sum(1 for r in results if r.success)
    stats.fail = stats.total - stats.success
    stats.total_times = [r.total_time for r in results if r.success]
    stats.first_token_latencies = [r.first_token_latency for r in results if r.success and r.first_token_latency > 0]
    for r in results:
        if not r.success:
            stats.errors[r.error or "Unknown"] += 1

    print(f"\n测试完成，总耗时: {time.time() - test_start:.3f}s")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw 多用户并发测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 5用户并发测试
  python start_test_mining_multiuser.py -c 5

  # 20并发压测 + 打印返回内容
  python start_test_mining_multiuser.py -c 20 -p

  # 自定义 prompt
  python start_test_mining_multiuser.py -c 10 --prompt "写一段Python快排代码"
        """
    )
    parser.add_argument("-c", "--concurrency", type=int, default=5,
                        help="并发数(=用户数=总请求数)，默认5")
    parser.add_argument("--url", type=str,
                        default="http://localhost:8080/api/science/chat",
                        help="API地址")
    parser.add_argument("--prompt", type=str,
                        default="say hello in one word",
                        help="测试prompt")
    parser.add_argument("--timeout", type=int, default=60,
                        help="请求超时秒数，默认60")
    parser.add_argument("-p", "--print-content", action="store_true",
                        help="打印模型返回的内容")
    parser.add_argument("--stop", action="store_true",
                        help="发送停止会话请求")

    args = parser.parse_args()

    if args.stop:
        print("=== 停止会话测试 ===")
        async def stop_test():
            async with aiohttp.ClientSession() as session:
                for i in range(args.concurrency):
                    payload = {
                        "linkId": f"l{i}",
                        "sessionId": f"s{i}",
                        "messages": [],
                        "type": -1,
                    }
                    async with session.post(args.url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                        body = await resp.text()
                        print(f"  [{i}] HTTP {resp.status}: {body[:100]}")
        asyncio.run(stop_test())
        return

    stats = asyncio.run(run_test(args))
    stats.print_report()


if __name__ == "__main__":
    main()
