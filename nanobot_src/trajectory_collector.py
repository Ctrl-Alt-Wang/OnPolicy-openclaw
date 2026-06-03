"""
trajectory_collector.py
启动一个 Hermes run，订阅 events，把整条轨迹存成 JSONL。
"""
import urllib.request
import json
import sys
import time
from pathlib import Path

HERMES_URL = "http://shared-openclaw:8080"
TOKEN = "dev-hermes-bridge-key"
OUTPUT_DIR = Path("/tmp/trajectories")
OUTPUT_DIR.mkdir(exist_ok=True)


def run_and_collect(prompt: str, model: str = "hermes-agent"):
    """发起一个 run，订阅 events，把所有事件存到 JSONL 文件"""
    
    # 第 1 步：提交 run
    req = urllib.request.Request(
        f"{HERMES_URL}/v1/runs",
        data=json.dumps({"model": model, "input": prompt}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    resp = urllib.request.urlopen(req, timeout=30)
    run_data = json.loads(resp.read())
    run_id = run_data["run_id"]
    print(f"[*] Run started: {run_id}")

    # 第 2 步：准备落盘
    output_file = OUTPUT_DIR / f"trajectory_{run_id}.jsonl"
    print(f"[*] Saving trajectory to {output_file}")
    
    # 把 prompt 和 run_id 作为元数据先记一行
    metadata = {
        "type": "metadata",
        "run_id": run_id,
        "prompt": prompt,
        "model": model,
        "start_time": time.time(),
    }
    
    # 第 3 步：订阅 events 并落盘
    events_req = urllib.request.Request(
        f"{HERMES_URL}/v1/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    events_resp = urllib.request.urlopen(events_req, timeout=300)
    
    event_count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        # 写元数据头
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        
        # 写所有事件
        for raw_line in events_resp:
            line = raw_line.decode().rstrip()
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            event_count += 1
            
            # 在终端实时显示一行简短描述
            event_type = payload.get("event", "?")
            if event_type == "tool.started":
                print(f"  [{event_count}] 🔧 tool started: {payload.get('tool')}")
            elif event_type == "tool.completed":
                error = payload.get("error", False)
                icon = "❌" if error else "✅"
                print(f"  [{event_count}] {icon} tool done: {payload.get('tool')} ({payload.get('duration'):.2f}s)")
            elif event_type == "reasoning.available":
                snippet = payload.get("text", "")[:60].replace("\n", " ")
                print(f"  [{event_count}] 🧠 reasoning: {snippet}...")
            elif event_type == "run.completed":
                usage = payload.get("usage", {})
                print(f"  [{event_count}] 🎉 RUN COMPLETED (tokens: {usage.get('total_tokens')})")
    
    print(f"\n[✓] Saved {event_count} events to {output_file}")
    return output_file


if __name__ == "__main__":
    # 从命令行读 prompt，默认给一个示例
    prompt = sys.argv[1] if len(sys.argv) > 1 else "查找PD-1抑制剂在肝癌治疗中的最新3篇文献"
    run_and_collect(prompt)
