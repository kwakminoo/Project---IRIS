"""마이크 입력 장치 선택과 검증."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_LOOPBACK_NAME_PARTS = (
    "stereo mix",
    "what u hear",
    "wave out",
    "loopback",
    "monitor of",
    "speaker",
    "speakers",
    "output",
    "cable output",
)

_VIRTUAL_INPUT_NAME_PARTS = (
    "aggregate",
    "blackhole",
    "cable input",
    "cable-a",
    "cable-b",
    "cable-c",
    "cable-d",
    "camo",
    "elgato wave link",
    "krisp",
    "manycam",
    "mapper",
    "nvidia broadcast",
    "obs",
    "primary sound capture",
    "snap camera",
    "soundflower",
    "streaming microphone",
    "vb-audio",
    "vb-cable",
    "virtual",
    "voicemod",
    "voicemeeter",
)


@dataclass(frozen=True)
class InputDeviceChoice:
    device: int | None
    name: str


@dataclass(frozen=True)
class PhysicalInputDevice:
    index: int
    name: str


def _default_input_index(sd: Any) -> int | None:
    default_device = getattr(sd, "default", None)
    raw = getattr(default_device, "device", None)
    if isinstance(raw, (list, tuple)) and raw:
        try:
            return int(raw[0])
        except (TypeError, ValueError):
            return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_loopback_name(name: str) -> bool:
    low = name.lower()
    return any(part in low for part in _LOOPBACK_NAME_PARTS)


def _is_virtual_input_name(name: str) -> bool:
    low = name.lower()
    return any(part in low for part in _VIRTUAL_INPUT_NAME_PARTS)


def _device_channels(info: Any) -> int:
    try:
        return int(info.get("max_input_channels") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _device_name(info: Any, index: int) -> str:
    try:
        return str(info.get("name") or f"device {index}")
    except AttributeError:
        return f"device {index}"


def is_physical_microphone_name(name: str) -> bool:
    """
    Windows가 입력 장치로 노출한 목록에서 실제 마이크가 아닌 가상/루프백 계열을 거른다.
    """
    return not _is_loopback_name(name) and not _is_virtual_input_name(name)


def is_physical_microphone_info(info: Any, index: int) -> bool:
    """
    설정창과 녹음 실행이 같은 기준으로 물리 마이크 후보만 허용하도록 공용 검증을 제공한다.
    """
    if _device_channels(info) < 1:
        return False
    return is_physical_microphone_name(_device_name(info, index))


def list_physical_input_devices(sd: Any) -> list[PhysicalInputDevice]:
    """sounddevice가 현재 PC에서 인식한 물리 마이크 후보만 반환한다."""
    try:
        devices: Any = sd.query_devices()
    except Exception:
        return []

    options: list[PhysicalInputDevice] = []
    for index, info in enumerate(devices):
        if is_physical_microphone_info(info, index):
            options.append(PhysicalInputDevice(index=index, name=_device_name(info, index)))
    return options


def resolve_input_device(sd: Any, configured_device: int | None) -> tuple[InputDeviceChoice | None, str]:
    """
    sounddevice 입력 장치 검증.

    명시 장치가 있으면 그 장치를 사용하고, 없으면 Windows 기본 입력 장치를 사용한다.
    출력/루프백/가상 입력 계열은 스피커 소리나 소프트웨어 출력을 명령처럼 받을 수 있어 거부한다.
    """
    index = configured_device if configured_device is not None else _default_input_index(sd)
    if index is None or index < 0:
        return None, "사용 가능한 기본 마이크 입력 장치를 찾지 못했습니다."

    try:
        info = sd.query_devices(index, "input")
    except Exception as exc:
        return None, f"마이크 입력 장치를 열 수 없습니다: {exc}"

    name = _device_name(info, index)
    channels = _device_channels(info)
    if channels < 1:
        return None, f"입력 채널이 없는 장치입니다: {name}"
    if _is_loopback_name(name):
        return None, f"스피커/루프백 계열 입력은 사용할 수 없습니다: {name}"
    if _is_virtual_input_name(name):
        return None, f"가상 입력 장치는 기본 마이크로 사용할 수 없습니다: {name}"
    return InputDeviceChoice(device=index, name=name), "ok"
