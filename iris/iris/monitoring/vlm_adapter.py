"""경량 VLM 연결용 인터페이스 (현재 스텁)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VlmAdapter(Protocol):
    """추후 SmolVLM2 등 연결."""

    def describe_scene(self, image_rgb: bytes, width: int, height: int) -> str:
        """장면 설명 텍스트."""
        ...


class StubVlmAdapter:
    """VLM 미연결 시."""

    def describe_scene(self, image_rgb: bytes, width: int, height: int) -> str:
        return ""
