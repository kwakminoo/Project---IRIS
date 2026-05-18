"""시스템 사양 수집 — psutil 우선, 없으면 Windows WMI/보조 subprocess (순수 함수)."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from typing import Any

# Windows 콘솔 창 숨김 (로컬 비서 UX)
_SUBPROCESS_FLAGS: int = 0
if sys.platform == "win32":
    _SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_cmd(args: list[str], *, timeout: float = 8.0) -> str:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_SUBPROCESS_FLAGS,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _parse_wmic_value(block: str, key: str) -> str:
    for line in block.splitlines():
        line = line.strip()
        if line.lower().startswith(key.lower() + "="):
            return line.split("=", 1)[-1].strip()
    return ""


def _windows_wmic_fallback() -> dict[str, Any]:
    """psutil 없을 때 WMIC/systeminfo 제한 조회 (개인 경로 미사용)."""
    out: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": "",
        "memory_total_gb": 0.0,
        "memory_available_gb": 0.0,
        "gpu": "",
        "disks": [],
    }
    cpu_block = _run_cmd(["wmic", "cpu", "get", "Name", "/value"], timeout=6.0)
    name = _parse_wmic_value(cpu_block, "Name")
    if name:
        out["cpu"] = name

    mem_block = _run_cmd(
        ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"],
        timeout=6.0,
    )
    raw_mem = _parse_wmic_value(mem_block, "TotalPhysicalMemory")
    if raw_mem.isdigit():
        total = int(raw_mem) / (1024**3)
        out["memory_total_gb"] = round(total, 2)
        out["memory_available_gb"] = round(total * 0.85, 2)  # 세부 없음 시 대략치

    gpu_block = _run_cmd(
        ["wmic", "path", "win32_VideoController", "get", "Name", "/value"],
        timeout=6.0,
    )
    names = re.findall(r"Name=(.+)", gpu_block, flags=re.I)
    if names:
        out["gpu"] = names[0].strip()

    disk_block = _run_cmd(
        ["wmic", "logicaldisk", "get", "DeviceID,Size,FreeSpace", "/value"],
        timeout=8.0,
    )
    # WMIC /value 블록 단위 파싱
    chunks = re.split(r"\r?\n\r?\n", disk_block.strip())
    for ch in chunks:
        did = _parse_wmic_value(ch, "DeviceID")
        if not did or len(did) > 3:
            continue
        sz = _parse_wmic_value(ch, "Size")
        free = _parse_wmic_value(ch, "FreeSpace")
        if sz.isdigit() and free.isdigit():
            total_b = int(sz)
            free_b = int(free)
            used_pct = round(100.0 * (1.0 - free_b / total_b), 1) if total_b > 0 else 0.0
            out["disks"].append(
                {
                    "mount": did,
                    "total_gb": round(total_b / (1024**3), 2),
                    "used_percent": used_pct,
                }
            )

    if not out["cpu"] or out["memory_total_gb"] <= 0:
        si = _run_cmd(["systeminfo"], timeout=12.0)
        if si:
            m = re.search(r"OS Name:\s*(.+)", si, re.I)
            if m:
                out["os"] = m.group(1).strip()[:120]
            m = re.search(r"Processor\(s\):\s*(.+)", si, re.I)
            if m and not out["cpu"]:
                out["cpu"] = m.group(1).strip()[:200]
            m = re.search(r"Total Physical Memory:\s*([\d,]+)\s*MB", si, re.I)
            if m and out["memory_total_gb"] <= 0:
                mb = int(m.group(1).replace(",", ""))
                out["memory_total_gb"] = round(mb / 1024, 2)
                out["memory_available_gb"] = round(mb / 1024 * 0.85, 2)

    return out


def collect_system_info() -> dict[str, Any]:
    """CPU/RAM/GPU/디스크/OS 요약 dict (JSON 직렬화 가능)."""
    try:
        import psutil as ps  # type: ignore[import-untyped]
    except ImportError:
        ps = None

    if ps is not None:
        vm = ps.virtual_memory()
        disks: list[dict[str, Any]] = []
        try:
            for part in ps.disk_partitions(all=False):
                if not part.mountpoint:
                    continue
                try:
                    u = ps.disk_usage(part.mountpoint)
                except OSError:
                    continue
                disks.append(
                    {
                        "mount": part.mountpoint,
                        "total_gb": round(u.total / (1024**3), 2),
                        "used_percent": round(u.percent, 1),
                    }
                )
        except Exception:
            pass

        gpu = ""
        try:
            import shutil

            if shutil.which("wmic") and sys.platform == "win32":
                gpu_block = _run_cmd(
                    ["wmic", "path", "win32_VideoController", "get", "Name", "/value"],
                    timeout=5.0,
                )
                names = re.findall(r"Name=(.+)", gpu_block, flags=re.I)
                if names:
                    gpu = names[0].strip()
        except Exception:
            pass

        freq = ""
        try:
            f = ps.cpu_freq()
            if f and f.current:
                freq = f"{round(f.current, 0)} MHz"
        except Exception:
            pass

        logical_n = int(ps.cpu_count() or 0)
        phys_n = ps.cpu_count(logical=False)
        brand = (platform.processor() or "").strip()
        if not brand and sys.platform == "win32":
            cpu_block = _run_cmd(["wmic", "cpu", "get", "Name", "/value"], timeout=5.0)
            brand = _parse_wmic_value(cpu_block, "Name").strip()
        cpu_line = brand or "CPU"
        cpu_line += f" ({logical_n} 논리 코어"
        if phys_n:
            cpu_line += f", 물리 {phys_n}"
        cpu_line += ")"
        if freq:
            cpu_line += f", {freq}"

        return {
            "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "cpu": cpu_line.strip(),
            "memory_total_gb": round(vm.total / (1024**3), 2),
            "memory_available_gb": round(vm.available / (1024**3), 2),
            "gpu": gpu,
            "disks": disks[:8],
        }

    if sys.platform == "win32":
        return _windows_wmic_fallback()

    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "unknown",
        "memory_total_gb": 0.0,
        "memory_available_gb": 0.0,
        "gpu": "",
        "disks": [],
    }


def verify_system_info_nonempty(info: dict[str, Any]) -> bool:
    """Tier 1 검증: OS·CPU·메모리 중 최소 하나는 비어 있지 않아야 함."""
    os_s = str(info.get("os") or "").strip()
    cpu = str(info.get("cpu") or "").strip()
    mem = float(info.get("memory_total_gb") or 0.0)
    if os_s and len(os_s) >= 2:
        return True
    if cpu and len(cpu) >= 2:
        return True
    if mem > 0:
        return True
    disks = info.get("disks") or []
    return bool(disks)


def system_info_to_json(info: dict[str, Any]) -> str:
    return json.dumps(info, ensure_ascii=False)


def system_info_brief_korean(info: dict[str, Any]) -> str:
    """채팅·TTS 원문용 한 줄 요약 (speech_formatter가 후처리)."""
    os_s = str(info.get("os") or "").strip() or "알 수 없음"
    cpu = str(info.get("cpu") or "").strip() or "알 수 없음"
    mem_t = float(info.get("memory_total_gb") or 0.0)
    mem_a = float(info.get("memory_available_gb") or 0.0)
    mem_part = ""
    if mem_t > 0:
        mem_part = f" RAM은 전체 약 {mem_t:.1f}기가바이트, 여유 약 {mem_a:.1f}기가바이트예요."
    gpu = str(info.get("gpu") or "").strip()
    gpu_part = f" 그래픽은 {gpu}예요." if gpu else ""
    disk = ""
    disks = info.get("disks") or []
    if isinstance(disks, list) and disks:
        d0 = disks[0]
        if isinstance(d0, dict):
            mount = str(d0.get("mount") or "")
            pct = d0.get("used_percent")
            if mount and isinstance(pct, (int, float)):
                disk = f" 주 디스크 {mount} 사용률은 약 {pct}%예요."
    return f"운영체제는 {os_s}, CPU는 {cpu}.{mem_part}{gpu_part}{disk}".strip()
