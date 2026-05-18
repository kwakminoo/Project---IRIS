import numpy as np

from iris.audio.voice_fx import apply_voice_fx


def test_voice_fx_disabled_passthrough() -> None:
    audio = np.linspace(-0.5, 0.5, 1000, dtype=np.float32)
    out = apply_voice_fx(audio, {"enabled": False}, global_enabled=True)
    np.testing.assert_allclose(out, audio, atol=1e-5)


def test_voice_fx_subtle_change_when_enabled() -> None:
    audio = np.sin(np.linspace(0, 8 * np.pi, 2400)).astype(np.float32) * 0.4
    fx = {"enabled": True, "reverb": 0.08, "chorus": 0.04, "robotic_texture": 0.03}
    out = apply_voice_fx(audio, fx, global_enabled=True)
    assert out.shape == audio.shape
    assert not np.allclose(out, audio)
