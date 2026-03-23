#!/usr/bin/env python3
"""System profiling — hardware detection and model recommendations."""

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))


def detect_hardware() -> dict:
    profile = {
        "cpu": {"cores": os.cpu_count(), "arch": platform.machine()},
        "ram": {},
        "disk": {},
        "gpu": None,
    }

    # RAM
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if "MemTotal" in line:
                    profile["ram"]["total_mb"] = int(line.split()[1]) // 1024
                elif "MemAvailable" in line:
                    profile["ram"]["available_mb"] = int(line.split()[1]) // 1024
    except FileNotFoundError:
        pass

    # Disk
    total, used, free = shutil.disk_usage("/")
    profile["disk"] = {
        "total_gb": round(total / (1024**3), 1),
        "free_gb": round(free / (1024**3), 1),
    }

    # GPU
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            profile["gpu"] = {"type": "nvidia", "info": result.stdout.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        profile["gpu"] = {"type": "apple_silicon", "info": "Unified memory"}

    # Model recommendation based on available RAM
    ram = profile["ram"].get("total_mb", 0)
    if ram >= 32000:
        profile["recommended_model"] = "qwen2.5-coder:32b"
    elif ram >= 16000:
        profile["recommended_model"] = "qwen2.5-coder:14b"
    elif ram >= 8000:
        profile["recommended_model"] = "qwen2.5-coder:7b"
    elif ram >= 4000:
        profile["recommended_model"] = "qwen2.5-coder:3b"
    else:
        profile["recommended_model"] = "qwen2.5-coder:1.5b"

    return profile


def save_profile(profile: dict) -> Path:
    out_path = JARVIS / "database" / "system_profile.json"
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = detect_hardware()
    print(f"CPU: {p['cpu']['cores']} cores ({p['cpu']['arch']})")
    print(
        f"RAM: {p['ram'].get('total_mb', '?')}MB total, "
        f"{p['ram'].get('available_mb', '?')}MB available"
    )
    print(f"Disk: {p['disk']['free_gb']}GB free / {p['disk']['total_gb']}GB total")
    print(f"GPU: {p['gpu']['info'] if p['gpu'] else 'None detected'}")
    print(f"Recommended Tier C model: {p['recommended_model']}")
    out = save_profile(p)
    print(f"Saved: {out}")
