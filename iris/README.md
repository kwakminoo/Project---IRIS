# Iris

Windows용 로컬 우선 개인 AI 비서 Iris입니다.

Iris is a local-first personal AI assistant for Windows.

- 한국어 설명: Iris는 Gemma 4 로컬 API, PyQt6 UI, 음성 입력/출력, 웹 검색, 위험도 기반 자동화를 포함합니다.

## 주요 기능

- Text chat / 텍스트 대화
- Voice input and response / 음성 입력과 응답
- Gemma 4 local model / Gemma 4 로컬 모델
- App launching / 앱 실행
- Window control / 창 제어
- Web search through Playwright / Playwright 웹 검색
- Monitoring dashboard / 모니터링 대시보드
- Settings dialog / 설정 창
- Risk-based automation / 위험도 기반 자동화

## 권한 정책

Iris uses risk-based permission control.

- 한국어 설명: Iris는 위험도에 따라 자동 실행 또는 승인 필요로 나눕니다.

- LOW_RISK, MEDIUM_RISK, HIGH_RISK: auto-allowed.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행될 수 있습니다.
- CRITICAL_RISK: approval required.
  - 한국어: 4단계 작업은 사용자 승인이 필요합니다.

CRITICAL_RISK examples:

- Shell commands / 셸 명령
- File deletion / 파일 삭제
- Payment / 결제
- Password input / 비밀번호 입력
- Personal information submission / 개인정보 제출
- System setting changes / 시스템 설정 변경
- Sensitive browser actions / 민감한 브라우저 조작

## 요구 사항

- Python 3.11+
- Windows

## 설치

PowerShell에서 앱 루트(`iris` 폴더)로 이동한 뒤:

```powershell
.\install.ps1
```

`.env.example`을 복사해 `.env`를 만들고 Ollama/LM Studio 주소와 모델명을 맞춥니다.

Chromium(Playwright):

```powershell
python -m playwright install chromium
```

## 실행

```powershell
cd "C:\Users\kwakm\OneDrive\Desktop\Cusor-Project\IRIS\iris"
.\.venv\Scripts\python.exe -m iris
```

또는 `run.bat` 더블클릭.

## 설정

우측 상단 설정 아이콘에서 다음을 바꿀 수 있습니다.

- AI model selection / AI 모델 선택
- AI model add/delete / AI 모델 추가와 삭제
- Input microphone selection / 입력 마이크 선택

## 음성 대화

- 기본: 상시 음성 대기 (`ALWAYS_LISTEN_ENABLED=true`)
- 호출어: `아이리스`, `iris`, `이리스`
- TTS 재생·처리 중에는 마이크 수집을 잠시 멈춰 스피커 에코를 줄입니다.
- Barge-in(TTS 중 끊기)은 기본 꺼짐 (`BARGE_IN_ENABLED=false`)

## 검증

```powershell
python -m compileall iris -q
python -m pytest -q
```
