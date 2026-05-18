from iris.audio.input_device import list_physical_input_devices, resolve_input_device


class FakeDefault:
    device = [0, None]


class FakeSoundDevice:
    default = FakeDefault()

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
