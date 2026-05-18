# Iris Safety Policy / Iris 안전 정책

## 1. Core Rule / 핵심 규칙

Iris uses risk-based permission control.

- 한국어 설명: Iris는 모든 조작을 똑같이 막지 않고, 위험도에 따라 자동 실행 또는 승인 필요로 나눕니다.
- 현재 정책: LOW_RISK, MEDIUM_RISK, HIGH_RISK는 추가 승인 없이 실행할 수 있고, CRITICAL_RISK는 명시적 사용자 승인이 필요합니다.

Dangerous actions may still be blocked even when the user approves.

- 한국어 설명: 사용자가 승인해도 위험한 셸 명령, 파괴적 파일 작업, 결제/비밀번호/개인정보 제출 등은 안전장치가 차단할 수 있습니다.

---

## 2. Permission Levels / 권한 단계

### LOW_RISK: Auto-Allowed / 1단계: 자동 허용

- Read open window titles.
  - 한국어: 열린 창 제목 읽기.
- Read visible app state.
  - 한국어: 보이는 앱 상태 읽기.
- Public web search.
  - 한국어: 공개 웹 검색.
- OCR summary without storing raw OCR text.
  - 한국어: 원문 저장 없는 OCR 요약.

### MEDIUM_RISK: Auto-Allowed / 2단계: 자동 허용

- Launch applications.
  - 한국어: 앱 실행.
- Open public websites.
  - 한국어: 공개 웹사이트 열기.
- Focus, move, and resize windows.
  - 한국어: 창 포커스, 이동, 크기 조정.
- Read-only file search.
  - 한국어: 읽기 전용 파일 검색.

### HIGH_RISK: Auto-Allowed / 3단계: 자동 허용

- Keyboard input in non-sensitive contexts.
  - 한국어: 민감하지 않은 화면에서 키보드 입력.
- Mouse clicks in non-sensitive contexts.
  - 한국어: 민감하지 않은 화면에서 마우스 클릭.
- Multi-step automation without critical actions.
  - 한국어: 4단계 위험 작업이 없는 다단계 자동화.
- Work, game, and creative preset execution after collecting needed information.
  - 한국어: 필요한 정보를 받은 뒤 작업/게임/창작 프리셋 실행.

### CRITICAL_RISK: Approval Required / 4단계: 승인 필요

- Running shell commands.
  - 한국어: 셸 명령 실행.
- File deletion, destructive move, overwrite, or mass modification.
  - 한국어: 파일 삭제, 파괴적 이동, 덮어쓰기, 대량 변경.
- Payment, purchase, transfer, or financial confirmation.
  - 한국어: 결제, 구매, 송금, 금융 확인.
- Password input or authentication secret submission.
  - 한국어: 비밀번호 또는 인증 비밀값 제출.
- Personal information submission.
  - 한국어: 개인정보 제출.
- Changing system, security, registry, firewall, or permission settings.
  - 한국어: 시스템, 보안, 레지스트리, 방화벽, 권한 설정 변경.
- Browser actions involving login, payment, private forms, account settings, or sensitive data.
  - 한국어: 로그인, 결제, 비공개 폼, 계정 설정, 민감 정보 관련 브라우저 조작.

---

## 3. Blocked Actions / 차단 대상

The following actions are blocked by default or require extra caution:

- 한국어: 아래 작업은 기본 차단 또는 특별 주의 대상입니다.

- Dangerous shell patterns such as `rm -rf`, `del /s`, `format`, `shutdown`, `powershell -enc`, or `curl | bash`.
  - 한국어: 위험한 셸 패턴.
- Destructive file operations without a clear target and preview.
  - 한국어: 명확한 대상과 미리보기가 없는 파괴적 파일 작업.
- Payment or purchase confirmation.
  - 한국어: 결제 또는 구매 확정.
- Password submission.
  - 한국어: 비밀번호 제출.
- Personal data submission.
  - 한국어: 개인정보 제출.
- Disabling security features.
  - 한국어: 보안 기능 비활성화.

---

## 4. Sensitive Monitoring Areas / 민감 화면 모니터링

Iris must not monitor or store content from sensitive areas.

- 한국어: Iris는 민감한 영역의 내용을 모니터링하거나 저장하지 않아야 합니다.

Sensitive areas:

- Password fields / 비밀번호 입력란
- Payment pages / 결제 페이지
- Banking pages / 금융 페이지
- Private documents / 개인 문서
- Personal identification forms / 신분증명 또는 개인정보 폼
- Login forms / 로그인 폼
- Medical or legal private pages / 의료 또는 법률 관련 개인 페이지

If detected, Iris should say:

> 민감한 화면으로 보입니다. 이 화면은 모니터링하지 않겠습니다.

---

## 5. Data Storage Policy / 데이터 저장 정책

Default behavior:

- Do not store raw screenshots.
  - 한국어: 원본 스크린샷을 저장하지 않습니다.
- Do not store full OCR text.
  - 한국어: 전체 OCR 텍스트를 저장하지 않습니다.
- Do not store full browser page text.
  - 한국어: 브라우저 페이지 전체 내용을 저장하지 않습니다.
- Store summarized events only.
  - 한국어: 요약 이벤트만 저장합니다.
- Store action logs with risk level, result, and whether approval was required.
  - 한국어: 실행 로그에는 위험도, 결과, 승인 필요 여부를 저장합니다.

---

## 6. Approval Flow / 승인 흐름

For CRITICAL_RISK actions:

1. Create ActionRequest.
   - 한국어: 실행 요청을 만듭니다.
2. Classify risk.
   - 한국어: 위험도를 분류합니다.
3. Show preview to the user.
   - 한국어: 실행 전 미리보기를 사용자에게 보여줍니다.
4. Ask for explicit approval.
   - 한국어: 명시적 승인을 요청합니다.
5. If approved, execute.
   - 한국어: 승인되면 실행합니다.
6. If denied, cancel.
   - 한국어: 거부되면 취소합니다.
7. Log result.
   - 한국어: 결과를 기록합니다.

Example:

Iris:

> 터미널에서 셸 명령을 실행하려고 합니다. 실행할까요?

User:

> 응.

Iris:

> 승인 확인. 셸 명령을 실행합니다.

---

## 7. Monitoring Alert Safety / 모니터링 알림 안전

Monitoring may recommend actions.

- 한국어: 모니터링은 조치를 제안할 수 있습니다.

LOW/MEDIUM/HIGH recommendations may be executed automatically.

- 한국어: 1~3단계 조치는 자동 실행될 수 있습니다.

CRITICAL recommendations require explicit approval.

- 한국어: 4단계 조치는 명시적 승인이 필요합니다.
