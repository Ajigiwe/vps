"""Async subprocess helpers for monitoring collectors."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


async def run_command(
    *args: str,
    timeout: float = 10.0,
    cwd: str | Path | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess asynchronously and return (code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


def resolve_binary(name: str, override: str | None = None) -> str | None:
    """Resolve binary path from override or PATH."""
    if override:
        return override
    return shutil.which(name)
