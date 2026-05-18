# Iris XTTS-v2 설정 가이드

Iris는 **선택적으로** Coqui [XTTS-v2](https://github.com/coqui-ai/TTS) 로컬 TTS를 사용할 수 있습니다.  
설치하지 않아도 Edge TTS / pyttsx3 폴백으로 정상 동작합니다.

## 라이선스·윤리

- **상업 배포 전** Coqui TTS / XTTS-v2 라이선스(CPML 등)를 반드시 검토하세요.
- **참조 음성**은 본인 목소리 또는 **명시적 사용 허가**를 받은 음성만 사용하세요.
- 유명인·타인의 목소리를 **무단 복제**하는 용도로 Iris를 사용하지 마세요.
- Iris는 사용자 몰래 녹음하거나 타인 음성을 수집하는 기능을 제공하지 않습니다.

## 요구 사항

- **Python 3.9 ~ 3.11** (Coqui `TTS` 패키지가 **3.12·3.13 미지원**)
- Iris 본체는 3.11+ 권장이나, XTTS만 쓸 때는 **3.11 전용 venv**를 만드는 것이 가장 안전합니다.
- (권장) NVIDIA GPU + CUDA — CPU만으로도 동작하지만 합성이 느릴 수 있습니다.
- 디스크: 모델 다운로드에 수 GB 여유 공간

## 설치

터미널 기본이 **Python 3.13**이면 `pip install TTS`가 실패합니다. **3.11**을 사용하세요.

Windows (시스템에 3.11이 있을 때):

```powershell
cd iris
py -3.11 -m venv .venv-tts
.\.venv-tts\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
pip install -r requirements-tts.txt
python -m iris
```

프로젝트 루트 `iris/`에서 (이미 3.11 venv 활성화된 경우):

```bash
pip install -r requirements.txt
pip install -r requirements-tts.txt
```

`torch`는 환경에 맞는 빌드를 [PyTorch 공식 안내](https://pytorch.org/)에 따라 설치하는 것이 좋습니다.

예시 (CPU):

```bash
pip install TTS torch torchaudio soundfile pydub
```

## 참조 음성 준비

1. **6~15초** 정도의 깨끗한 한국어 음성 WAV를 준비합니다.
2. 배경 소음·음악·다른 사람 목소리가 없어야 합니다.
3. 파일을 다음 경로에 둡니다:

```
iris/assets/voices/iris_reference.wav
```

4. 본인 또는 허가받은 화자만 사용했는지 다시 확인합니다.

## .env 설정

`iris/.env` 예시:

```env
TTS_PROVIDER=xtts
TTS_FALLBACK_PROVIDER=edge
TTS_VOICE_PRESET=iris_default
TTS_ENABLE_SPEECH_FORMATTER=true
TTS_ENABLE_VOICE_FX=true
TTS_MAX_SPOKEN_SENTENCES=3

XTTS_MODEL_NAME=tts_models/multilingual/multi-dataset/xtts_v2
XTTS_LANGUAGE=ko
XTTS_REFERENCE_WAV=assets/voices/iris_reference.wav
XTTS_DEVICE=auto
XTTS_SPEED=1.0
XTTS_ENABLE_CACHE=true
XTTS_CACHE_DIR=.cache/tts
```

- `XTTS_DEVICE=auto`: `torch.cuda.is_available()`이면 CUDA, 아니면 CPU
- 참조 파일이 없으면 Iris는 안내 후 **fallback TTS**로 재생합니다.

## 음성 프리셋

`iris/config/voice_presets.json`:

| 프리셋 | 설명 |
|--------|------|
| `iris_default` | 차분한 기본 아이리스 음성 + 약한 FX |
| `iris_jarvis` | 약한 기계 질감·잔향 |
| `iris_clean` | FX 없음 |

`.env`의 `TTS_VOICE_PRESET`으로 선택합니다.

## UI 상태 표시

메인 창에 TTS 상태가 표시됩니다.

- **XTTS Ready** — 준비 완료
- **Loading XTTS…** — 첫 합성 시 모델 로드 중
- **Using fallback** — Edge/pyttsx3 사용
- **Reference voice missing** — 참조 WAV 없음
- **TTS: Error** — 합성 실패 후 폴백

비주얼라이저: 합성 중 `PROCESSING`, 재생 중 `RESPONDING`.

## 문제 해결

| 증상 | 조치 |
|------|------|
| `XTTS 미설치` | `pip install -r requirements-tts.txt` |
| 매우 느림 | GPU 드라이버·CUDA 확인, 문장 길이는 SpeechFormatter가 자동 축약 |
| 참조 없음 | `iris_reference.wav` 경로·`.env`의 `XTTS_REFERENCE_WAV` 확인 |
| 합성 실패 | 로그 확인 후 `TTS_FALLBACK_PROVIDER=edge`로 폴백 |

## 테스트

```bash
cd iris
python -m compileall iris -q
python -m pytest tests/test_tts_manager.py tests/test_voice_fx.py tests/test_speech_formatter.py -q
```
