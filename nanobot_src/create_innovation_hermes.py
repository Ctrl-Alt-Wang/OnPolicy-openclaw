#!/usr/bin/env python3
"""创建/管理 10 个空白点专用 Hermes 容器。"""

import argparse
import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTAINER_COUNT = 10
CONTAINER_PREFIX = "hermes-innovation"
IMAGE = "nanobot-hermes-agent:latest"
NETWORK = "openclaw-internal"
INTERNAL_PORT = 18080
AGENT_PROFILE = "innovation"
AGENT_DIR = os.path.join(PROJECT_DIR, "deploy_copy", "Agents", "innovation")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"▸ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)


def _load_env() -> dict[str, str]:
    env_path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(env_path):
        return {}
    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


ENV = _load_env()
DEFAULT_MODEL = ENV.get("INNOVATION_MODEL", "openai/gpt-5.4")
OPENAI_API_KEY = ENV.get("OPENAI_API_KEY", "")
OPENAI_API_BASE = ENV.get("OPENAI_API_BASE", "")


def _container_name(idx: int) -> str:
    return f"{CONTAINER_PREFIX}-{idx:02d}"


def _data_volume_name(idx: int) -> str:
    return f"{CONTAINER_PREFIX}-data-{idx:02d}"


def _inject_agent_config(name: str, volume: str):
    """将 innovation agent 配置写入容器。"""
    if not os.path.isdir(AGENT_DIR):
        print(f"⚠ agent 配置目录不存在: {AGENT_DIR}")
        return

    # SOUL.md → /opt/data/SOUL.md（hermes 从 HERMES_HOME 加载主身份）
    soul = os.path.join(AGENT_DIR, "SOUL.md")
    if os.path.isfile(soul):
        _run(["docker", "cp", soul, f"{name}:/opt/data/SOUL.md"])

    # AGENTS.md, IDENTITY.md → /opt/data/workspace/
    _run(["docker", "exec", name, "mkdir", "-p", "/opt/data/workspace"])
    for f in ("AGENTS.md", "IDENTITY.md"):
        path = os.path.join(AGENT_DIR, f)
        if os.path.isfile(path):
            _run(["docker", "cp", path, f"{name}:/opt/data/workspace/{f}"])

    # USER.md → /opt/data/memories/（hermes memory 系统从此目录加载）
    _run(["docker", "exec", name, "mkdir", "-p", "/opt/data/memories"])
    user_md = os.path.join(AGENT_DIR, "USER.md")
    if os.path.isfile(user_md):
        _run(["docker", "cp", user_md, f"{name}:/opt/data/memories/USER.md"])

    # 修复权限。这里不用 docker exec 依赖主容器状态，避免入口脚本因权限问题
    # 重启时无法进入容器修复 volume。
    r = _run([
        "docker", "run", "--rm",
        "-v", f"{volume}:/opt/data",
        "--entrypoint", "chown",
        IMAGE,
        "-R", "hermes:hermes",
        "/opt/data/SOUL.md", "/opt/data/workspace/", "/opt/data/memories/",
    ])
    if r.returncode != 0:
        print(f"修复权限失败 {name}: {r.stderr}")
        sys.exit(1)
    print(f"  注入 agent 配置: {AGENT_PROFILE}")


def _ensure_network():
    result = subprocess.run(
        ["docker", "network", "inspect", NETWORK],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        r = _run(["docker", "network", "create", NETWORK, "-d", "bridge"])
        if r.returncode != 0:
            print(f"创建网络失败: {r.stderr}")
        else:
            print(f"创建网络: {NETWORK}")


def create():
    _ensure_network()
    for i in range(CONTAINER_COUNT):
        name = _container_name(i)
        vol = _data_volume_name(i)

        # 移除旧容器
        _run(["docker", "rm", "-f", name])

        # 创建数据卷
        _run(["docker", "volume", "create", vol])

        env_args = [
            "-e", "API_SERVER_ENABLED=true",
            "-e", f"API_SERVER_PORT={INTERNAL_PORT}",
            "-e", "API_SERVER_HOST=0.0.0.0",
            "-e", "API_SERVER_KEY=dev-hermes-bridge-key",
            "-e", f"API_SERVER_MODEL_NAME={DEFAULT_MODEL}",
            "-e", "HERMES_API_TOOLSETS=terminal,file,skills",
            "-e", "HERMES_REASONING_EFFORT=none",
            "-e", "TZ=Asia/Shanghai",
            "-e", "PYTHONUNBUFFERED=1",
            "-e", "GATEWAY_ALLOW_ALL_USERS=true",
            "-e", "NANOBOT_PROXY__URL=http://gateway:8080/llm/v1",
            "-e", "NANOBOT_PROXY__TOKEN=shared-openclaw-system-token",
            "-e", f"NANOBOT_AGENTS__DEFAULTS__MODEL={DEFAULT_MODEL}",
            "-e", f"HERMES_ACTIVE_AGENT={AGENT_PROFILE}",
        ]
        if OPENAI_API_KEY:
            env_args.extend(["-e", f"OPENAI_API_KEY={OPENAI_API_KEY}"])
        if OPENAI_API_BASE:
            env_args.extend(["-e", f"OPENAI_API_BASE={OPENAI_API_BASE}"])

        cmd = [
            "docker", "run", "-d",
            "--name", name,
            "--network", NETWORK,
            "--restart", "unless-stopped",
            "--memory", "2g",
            "--shm-size", "1g",
            "--cpus", "4",
            "--pids-limit", "1024",
            "-v", f"{vol}:/opt/data",
            *env_args,
            IMAGE,
            "gateway", "run",
        ]
        r = _run(cmd)
        if r.returncode != 0:
            print(f"创建容器失败 {name}: {r.stderr}")
            sys.exit(1)
        print(f"创建容器: {name} ({r.stdout.strip()[:12]})")
        _inject_agent_config(name, vol)

    print(f"\n✅ {CONTAINER_COUNT} 个 Hermes 空白点容器已创建（agent: {AGENT_PROFILE}）")
    for i in range(CONTAINER_COUNT):
        print(f"  http://{_container_name(i)}:{INTERNAL_PORT}")


def destroy(remove_volumes: bool = False):
    for i in range(CONTAINER_COUNT):
        name = _container_name(i)
        vol = _data_volume_name(i)
        _run(["docker", "rm", "-f", name])
        print(f"移除容器: {name}")
        if remove_volumes:
            _run(["docker", "volume", "rm", "-f", vol])
            print(f"  移除数据卷: {vol}")
    if remove_volumes:
        print(f"\n✅ 已清理 {CONTAINER_COUNT} 个容器及数据卷")
    else:
        print(f"\n✅ 已清理 {CONTAINER_COUNT} 个 Hermes 空白点容器")


def status():
    print(f"{'名称':<25} {'状态':<12} {'容器ID':<14}")
    print("-" * 55)
    for i in range(CONTAINER_COUNT):
        name = _container_name(i)
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}} {{.Id}}", name],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split()
            status_str = parts[0]
            cid = parts[1][:12] if len(parts) > 1 else "-"
            print(f"{name:<25} {status_str:<12} {cid:<14}")
        else:
            print(f"{name:<25} {'不存在':<12} {'-'}")


def main():
    parser = argparse.ArgumentParser(description="管理空白点 Hermes 容器")
    parser.add_argument("--create", action="store_true", help="创建 10 个容器")
    parser.add_argument("--destroy", action="store_true", help="销毁 10 个容器")
    parser.add_argument("--remove-volumes", action="store_true", help="销毁时同时删除数据卷（清除旧配置缓存）")
    parser.add_argument("--status", action="store_true", help="查看容器状态")
    args = parser.parse_args()

    if args.create:
        create()
    elif args.destroy:
        destroy(remove_volumes=args.remove_volumes)
    elif args.status:
        status()
    else:
        status()


if __name__ == "__main__":
    main()
