"""음성 파이프라인 진단: VAD 종료 조건, STT, VoiceGate 분기 확인."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# iris 패키지 루트
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

from iris.audio.stt_engine import SttEngine, cuda_runtime_ready, resolve_stt_device_compute
from iris.audio.voice_gate import VoiceCommandGate
from iris.audio.voice_session import VoiceSessionState
from iris.config.settings import load_settings


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def test_settings() -> None:
    _section("1. 설정")
    s = load_settings()
    print(f"  USE_WHISPER={s.use_whisper}")
    print(f"  STT_MODEL={s.stt_model}  STT_DEVICE={s.stt_device}  COMPUTE={s.stt_compute_type}")
    print(f"  cuda_runtime_ready={cuda_runtime_ready()}")
    device, compute = resolve_stt_device_compute(s)
    print(f"  resolved STT -> device={device}, compute_type={compute}")
    print(f"  ALWAYS_LISTEN_ENABLED={s.always_listen_enabled}")
    print(f"  ALWAYS_LISTEN_INPUT_DEVICE={s.always_listen_input_device}")
    print(f"  speech_rms={s.always_listen_speech_rms}  silence_rms={s.always_listen_silence_rms}")
    print(f"  silence_ms={s.always_listen_silence_ms}  min_speech_ms={s.always_listen_min_speech_ms}")
    print(f"  max_seconds={s.always_listen_max_seconds}")
    print(f"  voice_require_wake_word={s.voice_require_wake_word}")
    print(f"  voice_wake_words={s.voice_wake_words}")
    print(f"  STT_NO_SPEECH_THRESHOLD={s.stt_no_speech_threshold}")
    print(f"  STT_MIN_AVG_LOGPROB={s.stt_min_avg_logprob}")
    print(f"  STT_CONDITION_ON_PREVIOUS_TEXT={s.stt_condition_on_previous_text}")
    print(f"  VOICE_RESUME_DELAY_MS={s.voice_resume_delay_ms}")
    print(f"  VOICE_VAD_AUTO_CALIBRATE={s.voice_vad_auto_calibrate}")
    print(f"  BARGE_IN_GRACE_MS={s.barge_in_grace_ms}")
    print(f"  VoiceSession states: {[st.value for st in VoiceSessionState]}")


def test_sounddevice() -> bool:
    _section("2. sounddevice / 마이크 장치")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"  FAIL: sounddevice import — {exc}")
        return False

    s = load_settings()
    print(f"  default device: {sd.default.device}")
    try:
        devs = sd.query_devices()
        idx = s.always_listen_input_device
        if idx is not None:
            d = devs[idx]
            print(f"  configured device [{idx}]: {d['name']} (in={d['max_input_channels']})")
        else:
            print("  ALWAYS_LISTEN_INPUT_DEVICE not set — default input used")
    except Exception as exc:
        print(f"  FAIL: query_devices — {exc}")
        return False

    from iris.audio.input_device import resolve_input_device

    choice, reason = resolve_input_device(sd, s.always_listen_input_device)
    if choice is None:
        print(f"  FAIL: resolve_input_device — {reason}")
        return False
    print(f"  OK: {choice.name} - {reason}")
    return True


def test_stt_warmup_and_transcribe() -> str:
    """반환: ok | slow | fail | hang_risk"""
    _section("3. STT (Whisper) 워밍업 + 짧은 오디오 transcribe")
    s = load_settings()
    engine = SttEngine(s)

    t0 = time.perf_counter()
    engine.warmup()
    warmup_s = time.perf_counter() - t0
    model_ok = engine._model is not None and engine._model is not False
    print(f"  warmup: {warmup_s:.2f}s  model_loaded={model_ok}")
    if not model_ok:
        print("  FAIL: 모델 로드 실패 (_model=False)")
        return "fail"

    # 1초 무음 + 0.5초 440Hz 톤 (발화 시뮬)
    sr = s.always_listen_sample_rate
    silence = np.zeros(int(sr * 0.3), dtype=np.float32)
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    tone = (0.15 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    samples = np.concatenate([silence, tone, silence])

    t1 = time.perf_counter()
    result = engine.transcribe(samples, sr)
    transcribe_s = time.perf_counter() - t1
    print(
        f"  transcribe: {transcribe_s:.2f}s  text={result.text!r} "
        f"no_speech={result.no_speech} reason={result.reject_reason!r}"
    )
    text = result.text

    if transcribe_s > 30:
        return "hang_risk"
    if transcribe_s > 8:
        return "slow"
    if text is None and transcribe_s < 5:
        return "fail"
    return "ok"


def test_voice_gate() -> None:
    _section("4. VoiceGate (웨이크워드 분기)")
    s = load_settings()
    gate = VoiceCommandGate(
        wake_words=s.voice_wake_words,
        require_wake_word=s.voice_require_wake_word,
        followup_seconds=s.voice_followup_seconds,
    )
    cases = [
        "아이리스 오늘 날씨 알려줘",
        "아이리스",
        "오늘 날씨 알려줘",
        "",
        "iris what time is it",
    ]
    for raw in cases:
        r = gate.filter(raw)
        print(
            f"  {raw!r:40} → accepted={r.accepted} "
            f"prompt_only={r.prompt_only} reason={r.reject_reason!r} cmd={r.command_text!r}"
        )


def test_vad_finalize_logic() -> None:
    """RMS 시퀀스로 finalize 여부 시뮬."""
    _section("5. VAD 침묵 종료 시뮬 (로직만)")
    s = load_settings()
    speech_rms = s.always_listen_speech_rms
    silence_rms = s.always_listen_silence_rms
    silence_ms = s.always_listen_silence_ms

    def simulate(rms_series: list[float], dt_ms: float = 100) -> str:
        in_speech = False
        silence_started: float | None = None
        t = 0.0
        for rms in rms_series:
            if not in_speech:
                if rms >= speech_rms:
                    in_speech = True
                    silence_started = None
            else:
                if rms < silence_rms:
                    if silence_started is None:
                        silence_started = t
                    elif (t - silence_started) * 1000 >= silence_ms:
                        return "finalize"
                else:
                    silence_started = None
            t += dt_ms
        return "no_finalize" if in_speech else "never_started"

    # 말하고 침묵
    speech_then_silence = [0.02] * 5 + [0.003] * 5
    # 말하는 동안 배경 소음
    noisy = [0.02] * 3 + [0.012] * 20
    print(f"  speech→silence: {simulate(speech_then_silence)}")
    print(f"  noisy (rms~0.012 > silence_rms={silence_rms}): {simulate(noisy)}")
    print(f"  → 배경이 silence_rms({silence_rms}) 위면 '인식 중'으로 안 넘어갈 수 있음")


def main() -> int:
    print("Iris voice pipeline diagnostic")
    test_settings()
    sd_ok = test_sounddevice()
    stt_result = test_stt_warmup_and_transcribe()
    test_voice_gate()
    test_vad_finalize_logic()

    _section("요약")
    issues: list[str] = []
    if not sd_ok:
        issues.append("A: 마이크 장치 문제 (sounddevice/ALWAYS_LISTEN_INPUT_DEVICE)")
    if stt_result == "fail":
        issues.append("B: STT 모델 로드/변환 실패 → utterance_failed 또는 인식 중 정지")
    elif stt_result in ("slow", "hang_risk"):
        issues.append(
            f"C: STT 매우 느림 ({stt_result}) → '인식 중…'에서 오래 대기 (medium+CPU 가능)"
        )
    elif stt_result == "ok":
        print("  STT: 정상 속도로 완료")

    s = load_settings()
    if s.voice_require_wake_word:
        issues.append(
            "D: VOICE_REQUIRE_WAKE_WORD=true — 호출어 없으면 텍스트가 채팅에 안 뜸 (Iris 안내만)"
        )

    if issues:
        for i, msg in enumerate(issues, 1):
            print(f"  [{i}] {msg}")
    else:
        print("  명확한 실패 없음 — 실제 마이크/VAD는 런타임 녹음 필요")

    return 1 if any("fail" in x or "마이크" in x for x in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
