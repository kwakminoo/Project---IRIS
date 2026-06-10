from iris.audio.input_device import (
    default_input_device_index,
    list_physical_input_devices,
    probe_input_device,
    resolve_input_device,
    scan_available_input_devices,
)


class FakeDefault:
    device = [4, None]


class FakeInputStream:
    def __init__(self, *, device: int, **_kwargs: object) -> None:
        self._device = device

    def __enter__(self) -> "FakeInputStream":
        if self._device == 0:
            raise OSError("device busy")
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeSoundDevice:
    default = FakeDefault()
    InputStream = FakeInputStream

    def __init__(self) -> None:
        self.devices = [
            {"name": "Microphone Array (Realtek(R) Audio)", "max_input_channels": 2},
            {"name": "CABLE Output (VB-Audio Virtual Cable)", "max_input_channels": 2},
            {"name": "OBS Virtual Microphone", "max_input_channels": 1},
            {"name": "Speakers (Realtek(R) Audio)", "max_input_channels": 0},
            {"name": "USB PnP Audio Device", "max_input_channels": 1},
        ]

    def query_devices(self, index=None, kind=None):  # noqa: ANN001, ANN201, ARG002
        if index is None:
            return self.devices
        return self.devices[index]


def test_list_physical_input_devices_filters_virtual_and_output_devices() -> None:
    devices = list_physical_input_devices(FakeSoundDevice())

    assert [device.name for device in devices] == [
        "Microphone Array (Realtek(R) Audio)",
        "USB PnP Audio Device",
    ]


def test_resolve_input_device_rejects_virtual_microphone() -> None:
    choice, reason = resolve_input_device(FakeSoundDevice(), 2)

    assert choice is None
    assert "가상 입력 장치" in reason


def test_default_input_device_index_reads_sounddevice_default() -> None:
    assert default_input_device_index(FakeSoundDevice()) == 4


def test_probe_input_device_reports_open_failure() -> None:
    ok, reason = probe_input_device(FakeSoundDevice(), 0)
    assert ok is False
    assert "busy" in reason

    ok, reason = probe_input_device(FakeSoundDevice(), 4)
    assert ok is True
    assert reason == "ok"


def test_scan_available_input_devices_filters_unopenable_devices() -> None:
    result = scan_available_input_devices(FakeSoundDevice())

    assert result.default_index == 4
    assert result.default_name == "USB PnP Audio Device"
    assert [device.index for device in result.devices] == [4]
    assert result.devices[0].is_system_default is True
