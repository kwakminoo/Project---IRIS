# Iris Prompt Execution Order / Iris 프롬프트 실행 순서

## Step 1: Plan Mode / 1단계: 계획 모드

Use Plan Mode before writing code.

- 한국어 설명: 코드를 작성하기 전에 먼저 계획 모드로 구조를 검토합니다.

Prompt:

```text
Read AGENTS.md, .cursor/rules/iris.mdc, and docs/*.md.
Do not write code yet.
Review the architecture and propose the file creation plan for Iris.
```

Expected output:

- File structure review / 파일 구조 검토
- Implementation order / 구현 순서
- Potential risks / 잠재 위험
- Clarifying questions if needed / 필요한 질문

---

## Step 2: Agent Mode - Assistant / 2단계: 에이전트 모드 - 비서 기능

Goal:

- Build or improve the Jarvis-like assistant.
  - 한국어: 자비스형 비서 기능을 만들거나 개선합니다.

Check:

- PyQt6 window opens / PyQt6 창 열림
- Chat works / 채팅 동작
- Gemma 4 or fallback works / Gemma 4 또는 폴백 동작
- Work mode asks needed questions / 작업 모드가 필요한 질문을 함
- Game mode asks needed questions / 게임 모드가 필요한 질문을 함
- Risk-based permission works / 위험도 기반 권한 정책 동작

---

## Step 3: Manual Test / 3단계: 수동 테스트

Commands:

```bash
python -m compileall iris -q
python -m pytest -q
python -m iris
```

Manual test phrases:

- "작업 시작할게"
- "게임할래"
- "검색해줘"
- "Cursor 열어줘"
- "창 정리해줘"

Expected behavior:

- LOW/MEDIUM/HIGH actions execute without extra approval.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행됩니다.
- CRITICAL actions ask for approval.
  - 한국어: 4단계 작업은 승인을 요청합니다.

---

## Step 4: Plan Mode - Monitoring / 4단계: 계획 모드 - 모니터링

Before coding monitoring, run Plan Mode again.

- 한국어 설명: 모니터링 기능을 코딩하기 전에 다시 구조를 검토합니다.

Prompt:

```text
Existing Iris assistant is implemented.
Now plan how to add or improve hybrid monitoring without breaking the assistant.
Do not write code yet.
Review monitoring layer files and integration points.
```

---

## Step 5: Agent Mode - Monitoring / 5단계: 에이전트 모드 - 모니터링

Check:

- target registry / 대상 등록
- current screen OCR / 현재 화면 OCR
- terminal log collector / 터미널 로그 수집
- Chrome Extension structure / Chrome 확장 구조
- state detector / 상태 감지기
- notification panel / 알림 패널
- event logs / 이벤트 로그

---

## Step 6: Integration Test / 6단계: 통합 테스트

Test:

- Terminal approval waiting / 터미널 승인 대기
- Error detection / 오류 감지
- GPT response ready / GPT 응답 완료
- Midjourney failed generation / Midjourney 생성 실패
- Risk-based action after alert / 알림 후 위험도 기반 조치

---

## Step 7: Parallel Work Only After Stable Core / 7단계: 안정화 후 병렬 작업

Allowed for parallel agents:

- README / README 문서
- UI polish / UI 다듬기
- test code / 테스트 코드
- demo scenario docs / 데모 시나리오 문서
- Chrome Extension popup UI / Chrome 확장 팝업 UI

Do not parallelize:

- `database.py`
- `command_router.py`
- `safety_guard.py`
- `action_executor.py`
- `state_machine.py`

한국어 설명: 핵심 파일은 충돌과 회귀 위험이 크므로 병렬 작업을 피합니다.

---

## Initial Project Prompt / 초기 프로젝트 프롬프트

```text
Iris 프로젝트 구현 전에 기준 문서를 먼저 생성해줘.

아직 실제 앱 코드는 작성하지 마.

다음 파일을 생성해줘:
1. AGENTS.md
2. .cursor/rules/iris.mdc
3. CLAUDE.md
4. CLOUD.md
5. docs/domain-design.md
6. docs/architecture.md
7. docs/safety-policy.md
8. docs/implementation-plan.md
9. docs/prompt-execution-order.md

프로젝트 기준:
- 프로젝트명은 Iris
- 로컬 기반 개인 AI 비서
- Gemma 4 로컬 LLM 우선
- Claude/Gemini API를 기본 모델로 사용하지 않음
- 자비스형 AI 비서 기능 포함
- STT/TTS 포함
- barge-in 구조 포함
- 앱 실행, 창 포커스, 창 배치 포함
- Playwright 웹 에이전트 포함
- 작업 모드/게임 모드는 필요한 정보를 먼저 질문
- 1~3단계 위험 작업은 자동 실행 가능
- 4단계 위험 작업은 사용자 승인 필요
- 이후 하이브리드 모니터링 기능을 추가할 수 있도록 구조화
- 모니터링은 터미널 로그, 앱 창 UI/OCR, 브라우저 탭 DOM, 현재 화면 OCR, Windows Event Log, VLM adapter를 조합하는 구조

각 문서는 이후 구현 단계에서 참고할 수 있도록 명확하고 구체적으로 작성해줘.
```
