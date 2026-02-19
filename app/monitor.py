"""
monitor.py — System monitoring: CPU, RAM, disk, GPU.
"""

import asyncio
import json
import logging
import shutil

import psutil

logger = logging.getLogger(__name__)


async def get_system_status() -> dict:
    """Return a JSON-serialisable snapshot of system resources."""

    cpu_percent = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    status = {
        "cpu_percent": cpu_percent,
        "ram": {
            "total_gb": round(ram.total / (1024 ** 3), 2),
            "used_gb": round(ram.used / (1024 ** 3), 2),
            "percent": ram.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_gb": round(disk.used / (1024 ** 3), 2),
            "percent": disk.percent,
        },
        "gpu": await _get_gpu_info(),
    }

    logger.info(
        "System status fetched — CPU %.1f%%, RAM %.1f%%, Disk %.1f%%",
        cpu_percent,
        ram.percent,
        disk.percent,
    )
    return status


async def _get_gpu_info() -> dict | None:
    """Query nvidia-smi for GPU stats; returns None if unavailable."""

    if not shutil.which("nvidia-smi"):
        logger.warning("nvidia-smi not found — GPU monitoring disabled")
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        if proc.returncode != 0:
            logger.error("nvidia-smi failed: %s", stderr.decode().strip())
            return None

        parts = [p.strip() for p in stdout.decode().strip().split(",")]
        if len(parts) < 5:
            return None

        return {
            "name": parts[0],
            "utilization_percent": int(parts[1]),
            "memory_used_mb": int(parts[2]),
            "memory_total_mb": int(parts[3]),
            "temperature_c": int(parts[4]),
        }

    except asyncio.TimeoutError:
        logger.error("nvidia-smi timed out")
        return None
    except Exception as exc:
        logger.error("GPU info error: %s", exc)
        return None
