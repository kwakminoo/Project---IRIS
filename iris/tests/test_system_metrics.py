"""시스템 메트릭 테스트."""

from __future__ import annotations

from iris.system.gpu_provider import read_gpu_utilization
from iris.system.metrics_snapshot import MetricsSnapshot


def test_cpu_memory_use_real_provider_contract() -> None:
    try:
        import psutil
    except ImportError:
        return
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    snap = MetricsSnapshot(cpu_percent=cpu, memory_percent=mem, gpu_percent=None, gpu_label="N/A")
    assert 0.0 <= snap.cpu_percent <= 100.0
    assert 0.0 <= snap.memory_percent <= 100.0


def test_gpu_unavailable_displays_na() -> None:
    # nvidia-smi·PDH 없는 환경에서도 None 또는 유효 float
    value, label = read_gpu_utilization()
    if value is None:
        assert label == "N/A"
    else:
        assert 0.0 <= value <= 100.0


def test_metrics_snapshot_frozen() -> None:
    snap = MetricsSnapshot(10.0, 20.0, None, "N/A")
    assert snap.cpu_percent == 10.0
