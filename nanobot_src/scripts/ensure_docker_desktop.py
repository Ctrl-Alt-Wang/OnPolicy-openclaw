#!/usr/bin/env python3
"""Ensure Docker is usable from WSL, starting Docker Desktop through PowerShell if needed."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Sequence


ENV_SHIM_DIR = "NANOBOT_DOCKER_SHIM_DIR"
ENV_DOCKER_DESKTOP_EXE = "NANOBOT_DOCKER_DESKTOP_EXE"
DEFAULT_SHIM_DIR = Path(tempfile.gettempdir()) / "nanobot-docker-bin"


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class EnsureResult:
    ok: bool
    docker_cmd: str = "docker"
    started_desktop: bool = False
    path_to_prepend: str | None = None
    error: str = ""


Runner = Callable[..., CommandResult]
Which = Callable[[str], str | None]
Sleeper = Callable[[float], None]


def _run(cmd: Sequence[str], **kwargs) -> CommandResult:
    result = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _is_wsl(environ: Mapping[str, str]) -> bool:
    if environ.get("WSL_DISTRO_NAME") or environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _docker_info(docker_cmd: str, runner: Runner) -> CommandResult:
    try:
        return runner([docker_cmd, "info"], timeout=20)
    except (FileNotFoundError, OSError) as exc:
        return CommandResult(127, "", str(exc))


def _powershell_command(which: Which) -> str:
    return which("powershell.exe") or which("powershell") or "powershell.exe"


def _default_shim_dir(environ: Mapping[str, str]) -> Path:
    return Path(environ.get(ENV_SHIM_DIR) or DEFAULT_SHIM_DIR)


def _find_windows_docker_exe(runner: Runner, powershell_cmd: str) -> str:
    script = "$ErrorActionPreference='Stop'; (Get-Command docker.exe).Source"
    try:
        result = runner(
            [
                powershell_cmd,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            timeout=20,
        )
    except (FileNotFoundError, OSError):
        return "docker.exe"
    if result.returncode != 0:
        return "docker.exe"
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "docker.exe"


def _windows_path_to_wsl_path(windows_path: str, runner: Runner) -> str:
    if not windows_path or ":" not in windows_path:
        return windows_path or "docker.exe"
    try:
        result = runner(["wslpath", "-u", windows_path], timeout=10)
    except (FileNotFoundError, OSError):
        return "docker.exe"
    if result.returncode != 0:
        return "docker.exe"
    return result.stdout.strip() or "docker.exe"


def _write_docker_shim(shim_dir: Path, docker_exe: str) -> Path:
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_path = shim_dir / "docker"
    shim_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f'exec "{docker_exe}" "$@"\n',
        encoding="utf-8",
    )
    shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim_path


def _start_docker_desktop(
    runner: Runner,
    powershell_cmd: str,
    environ: Mapping[str, str],
) -> CommandResult:
    configured_desktop = environ.get(ENV_DOCKER_DESKTOP_EXE, "").strip()
    script = (
        "$ErrorActionPreference='Stop'; "
        "$desktop = $Env:NANOBOT_DOCKER_DESKTOP_EXE; "
        "if ($desktop -and (Test-Path $desktop)) { Start-Process -FilePath $desktop; exit } "
        "$cmd = Get-Command 'Docker Desktop.exe' -ErrorAction SilentlyContinue; "
        "if ($cmd) { Start-Process -FilePath $cmd.Source; exit } "
        "Start-Process -FilePath 'Docker Desktop'"
    )
    command_env = None
    if configured_desktop:
        command_env = dict(os.environ)
        command_env[ENV_DOCKER_DESKTOP_EXE] = configured_desktop
    try:
        return runner(
            [
                powershell_cmd,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            timeout=20,
            env=command_env,
        )
    except (FileNotFoundError, OSError) as exc:
        return CommandResult(127, "", str(exc))


def apply_path_to_environment(
    path_to_prepend: str | None,
    *,
    environ: MutableMapping[str, str] = os.environ,
) -> None:
    if not path_to_prepend:
        return
    parts = [part for part in environ.get("PATH", "").split(os.pathsep) if part]
    parts = [part for part in parts if part != path_to_prepend]
    environ["PATH"] = os.pathsep.join([path_to_prepend, *parts])


def ensure_docker_desktop(
    *,
    runner: Callable[..., CommandResult] = _run,
    which: Which = shutil.which,
    environ: Mapping[str, str] = os.environ,
    shim_dir: Path | None = None,
    timeout_seconds: int = 120,
    poll_interval_seconds: float = 2.0,
    sleep: Sleeper = time.sleep,
    is_wsl: bool | None = None,
) -> EnsureResult:
    current = _docker_info("docker", runner)
    if current.returncode == 0:
        return EnsureResult(ok=True, docker_cmd="docker")

    if is_wsl is None:
        is_wsl = _is_wsl(environ)
    if not is_wsl:
        return EnsureResult(
            ok=False,
            error=(current.stderr or current.stdout or "Docker is not available").strip(),
        )

    powershell_cmd = _powershell_command(which)
    resolved_shim_dir = shim_dir or _default_shim_dir(environ)
    docker_cmd = "docker"
    path_to_prepend = None
    if not which("docker"):
        windows_docker = _find_windows_docker_exe(runner, powershell_cmd)
        docker_exe = _windows_path_to_wsl_path(windows_docker, runner)
        shim_path = _write_docker_shim(resolved_shim_dir, docker_exe)
        docker_cmd = str(shim_path)
        path_to_prepend = str(resolved_shim_dir)

    start_result = _start_docker_desktop(runner, powershell_cmd, environ)
    if start_result.returncode != 0:
        return EnsureResult(
            ok=False,
            docker_cmd=docker_cmd,
            path_to_prepend=path_to_prepend,
            error=(
                start_result.stderr
                or start_result.stdout
                or "failed to start Docker Desktop"
            ).strip(),
        )

    deadline = time.monotonic() + timeout_seconds
    last = current
    while time.monotonic() <= deadline:
        last = _docker_info(docker_cmd, runner)
        if last.returncode == 0:
            return EnsureResult(
                ok=True,
                docker_cmd=docker_cmd,
                started_desktop=True,
                path_to_prepend=path_to_prepend,
            )
        sleep(poll_interval_seconds)

    return EnsureResult(
        ok=False,
        docker_cmd=docker_cmd,
        started_desktop=True,
        path_to_prepend=path_to_prepend,
        error=(last.stderr or last.stdout or "Docker Desktop did not become ready").strip(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start Docker Desktop from WSL through PowerShell and wait for docker info.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="seconds to wait for Docker")
    parser.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    parser.add_argument(
        "--shim-dir",
        type=Path,
        default=None,
        help=f"docker shim directory; defaults to ${ENV_SHIM_DIR} or system temp",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = ensure_docker_desktop(
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.interval,
        shim_dir=args.shim_dir or _default_shim_dir(os.environ),
    )
    if result.path_to_prepend:
        apply_path_to_environment(result.path_to_prepend)

    if not args.quiet:
        if result.ok:
            print(f"Docker is ready via {result.docker_cmd}")
            if result.path_to_prepend:
                print(f'For this shell, run: export PATH="{result.path_to_prepend}:$PATH"')
        else:
            print(result.error or "Docker is not ready", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
