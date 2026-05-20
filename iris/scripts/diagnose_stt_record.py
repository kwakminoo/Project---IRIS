"""3초 마이크 녹음 후 STT (실제 오디오 경로 테스트)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import numpy as np

from iris.audio.input_device import resolve_input_device
from iris.audio.stt_engine import SttEngine
from iris.config.settings import load_settings


def main() -> None:
    import sounddevice as sd

    s = load_settings()
    choice, reason = resolve_input_device(sd, s.always_listen_input_device)
    if choice is None:
        print(f"device FAIL: {reason}")
        return
    sr = s.always_listen_sample_rate
    sec = 3.0
    print(f"Recording {sec}s from device {choice.device} ({choice.name})...")
    print("(말해 주세요: 아이리스 테스트)")
    audio = sd.rec(
        int(sr * sec),
        samplerate=sr,
        channels=1,
        dtype="float32",
        device=choice.device,
    )
    sd.wait()
    mono = np.asarray(audio[:, 0], dtype=np.float32)
    rms = float(np.sqrt(np.mean(np.square(mono))))
    print(f"RMS={rms:.4f} (speech threshold={s.always_listen_speech_rms})")

    engine = SttEngine(s)
    t0 = time.perf_counter()
    engine.warmup()
    print(f"warmup done in {time.perf_counter() - t0:.2f}s")
    t1 = time.perf_counter()
    text = engine.transcribe_audio(mono, sr)
    elapsed = time.perf_counter() - t1
    print(f"transcribe: {elapsed:.2f}s")
    print(f"text: {text!r}")

    from iris.audio.voice_gate import VoiceCommandGate

    gate = VoiceCommandGate(
        wake_words=s.voice_wake_words,
        require_wake_word=s.voice_require_wake_word,
        followup_seconds=s.voice_followup_seconds,
    )
    if text:
        g = gate.filter(text)
        print(f"gate: accepted={g.accepted} reason={g.reject_reason!r} cmd={g.command_text!r}")


if __name__ == "__main__":
    main()
