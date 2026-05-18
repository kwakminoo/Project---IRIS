"""Computer Use Perception 요약 타입 (원문 스크린샷·전체 OCR 저장 없음)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

PerceptionSource = Literal["uia", "ocr", "hybrid", "vlm", "unknown"]


@dataclass
class PerceptionObservation:
    """한 스텝 시점의 PC 상태 요약."""

    active_window: str = ""
    open_windows_summary: str = ""
    summary: str = ""
    perception_source: PerceptionSource = "unknown"
    monitor_hint: str = ""
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_detail_json(self) -> str:
        """도구 result.detail용 JSON (2KB 이하 권장)."""
        payload = {
            "perception_source": self.perception_source,
            "active_window": self.active_window[:200],
            "summary": self.summary[:1800],
            "monitor_hint": self.monitor_hint[:200],
            "captured_at": self.captured_at,
        }
        return json.dumps(payload, ensure_ascii=False)

    def to_observation_string(self, *, max_summary: int = 400) -> str:
        """ComputerUseAgent observation 한 줄."""
        summ = self.summary[:max_summary]
        return (
            f"perceive: {self.perception_source} | "
            f"{self.active_window[:120]} | {summ}"
        )
