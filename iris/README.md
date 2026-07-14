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
- App launcher index / 앱 런처 (시작 메뉴·App Paths 스캔, 설치 완료 감지, 설정에서 수동 감지)
- Risk-based automation / 위험도 기반 자동화

## 웹 검색

- 기본: DuckDuckGo (`ddgs` 패키지, `pip install -r requirements.txt`에 포함, API 키·Docker 불필요)
- DuckDuckGo 실패 시 Playwright Google SERP 폴백 (`IRIS_SEARCH_PLAYWRIGHT_FALLBACK=1`)
- 참고: `html.duckduckgo.com` 직접 HTML 파싱은 봇 차단(HTTP 202)으로 동작하지 않아 `ddgs` 라이브러리를 사용합니다.

## 앱 런처

설정 창의 **앱 런처** 섹션에서 PC에 등록된 실행 파일 목록을 확인·수동 추가할 수 있습니다.

- **앱 런처 감지**: 시작 메뉴 shortcut과 Windows App Paths 레지스트리를 스캔해 신규 앱만 DB에 추가합니다.
- **자동 등록**: 새 앱 설치 후 시작 메뉴에 shortcut이 생기면 백그라운드에서 인덱스에 반영합니다 (24시간 주기 전체 스캔 없음).
- `메모장 켜줘` 같은 요청은 인덱스의 `launch_app` 경로로 실행됩니다 (`run_shell` 폴백 최소화).

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

- **Python 3.11 권장** (3.12도 CI에서 검증). 시스템 기본이 3.13이면 venv는 `py -3.11`로 만드세요.
- **Primary supported development platform: Windows 11**
- Required CI platform: Windows (`test / windows-py311`, `test / windows-py312`, `test / windows-integration`)
- Linux CI: experimental / deferred — `linux-experimental.yml` 수동 실행

자세한 테스트 정책: [docs/testing/windows-ci-policy.md](../docs/testing/windows-ci-policy.md)

## 설치

PowerShell에서 앱 루트(`iris` 폴더)로 이동한 뒤:

```powershell
cd iris
.\install.ps1
```

`install.ps1`은 가능하면 **Python 3.11**로 `.venv`를 만들고 `requirements.txt`를 설치합니다.

`.env` 파일에서 Ollama/LM Studio 주소와 모델명을 맞춥니다. (없으면 `iris` 폴더에 `.env`를 새로 만드세요.)

Chromium(Playwright):

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 실행

앱 폴더(`IRIS\iris`)에서:

```powershell
cd iris   # 저장소 루트(IRIS)에서 iris 앱 폴더로 이동
.\.venv\Scripts\python.exe -m iris
```

또는 `run.bat` 더블클릭.

### 실행이 안 될 때

`ImportError: DLL load failed while importing QtGui` / `QtCore` 가 나오면:

1. **원인:** `.venv`의 PyQt6 Qt 바이너리(`PyQt6\Qt6`)가 빠졌거나, **Python 3.13 venv**·깨진 pip·OneDrive 불완전 동기화로 패키지가 손상된 경우가 많습니다.
2. **복구 (권장):**

```powershell
cd iris
# 깨진 venv 백업 후 3.11로 재생성
Rename-Item .venv .venv.broken -ErrorAction SilentlyContinue
py -3.11 -m venv .venv
.\install.ps1
.\.venv\Scripts\python.exe -m iris
```

3. 버전 확인: `.\.venv\Scripts\python.exe -c "import sys; print(sys.version)"` → `3.11.x` 인지 확인.

OneDrive 동기화를 쓰지 않을 때는 저장소 루트에서 `.\scripts\ensure-local-project.ps1`로  
`%USERPROFILE%\Projects\IRIS`에 로컬 미러를 만든 뒤, Cursor는 그 경로를 엽니다.

## Iris IDE (내장 Theia)

IDE는 구현되어 있습니다. 좌측 사이드바 **IDE** 버튼으로 Theia 작업공간으로 전환합니다.

**최초 1회** (`iris` 폴더 또는 저장소 루트 `IRIS` 폴더에서):

```powershell
.\scripts\setup-iris-ide.ps1
.\scripts\build-iris-ide.ps1
```

`iris` 폴더에서 실행하면 `iris/scripts/` 래퍼가 저장소 루트의 스크립트를 호출합니다.

**빌드 실패 (`EBUSY`, `drivelist.node`)** — Iris를 완전히 종료한 뒤 다시 `build-iris-ide.ps1`을 실행하세요. Iris IDE 백엔드가 `.node` 파일을 잡고 있으면 webpack이 덮어쓰지 못합니다. `Failed to resolve module: @theia/electron` 경고는 Browser 앱에서는 무시해도 됩니다.

추가 Python 패키지:

```powershell
pip install PyQt6-WebEngine
```

Node.js 18+와 Yarn이 필요합니다. Yarn이 없으면 setup 스크립트가 `npm install -g yarn`을 시도합니다.

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

## Chrome 확장 (URL 규칙 · YouTube DOM 등)

확장 팝업에서 **사이트(URL) 규칙**을 켜세요 (예: YouTube 전체). 탭마다 허용할 필요 없습니다.
Iris가 검색 URL을 연 뒤 확장이 `/watch?v=` 링크·제목을 수집하면 DOM 경로로 재생합니다.
Netflix·Google·Naver 규칙도 동일 ingest를 사용합니다 (미디어 플로우는 플랫폼별 지원 범위 따름).

자세한 설치: `docs/chrome-extension-setup-ko.md`

## 검증

```powershell
python -m compileall iris -q
python -m pytest -q
```
