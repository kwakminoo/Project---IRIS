# Iris Prompt Execution Order

## Recommended Cursor Workflow

## Step 1: Plan Mode

Use Plan Mode before writing code.

Prompt:

"Read AGENTS.md, .cursor/rules/iris.mdc, and docs/*.md.  
Do not write code yet.  
Review the architecture and propose the file creation plan for Phase 1: Jarvis-like AI assistant."

Expected output:
- File structure review
- Implementation order
- Potential risks
- Clarifying questions if needed

---

## Step 2: Agent Mode - Phase 1

Run the AI assistant implementation prompt.

Goal:
Build the base Jarvis-like assistant.

Check:
- PyQt6 window opens
- Chat works
- Gemma 4 or fallback works
- Work mode asks questions
- Game mode asks questions
- User approval required for actions

---

## Step 3: Manual Test

Test before adding monitoring.

Commands:

```bash
python -m compileall iris -q
python -m iris

Manual test:

"작업 시작할게"
"게임할래"
"검색해줘"
"Cursor 열어줘"
"창 정리해줘"
Step 4: Plan Mode - Monitoring

Before coding monitoring, run Plan Mode again.

Prompt:

"Existing Iris assistant is implemented.
Now plan how to add hybrid monitoring without breaking the assistant.
Do not write code yet.
Review monitoring layer files and integration points."

Step 5: Agent Mode - Monitoring

Run the hybrid monitoring implementation prompt.

Check:

target registry
current screen OCR
terminal log collector
Chrome Extension structure
state detector
notification panel
event logs
Step 6: Integration Test

Test:

Terminal approval waiting
Error detection
GPT response ready
Midjourney failed generation
User-approved action after alert
Step 7: Parallel Work Only After Stable Core

Allowed for parallel agents:

README
UI polish
test code
demo scenario docs
Chrome Extension popup UI

Do not parallelize:

database.py
command_router.py
safety_guard.py
action_executor.py
state_machine.py

---

# 11. Cursor에서 처음 실행할 Plan Mode 프롬프트

위 파일들을 직접 만들거나, Cursor에게 먼저 만들게 하려면 이 프롬프트를 쓰세요.

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
- 작업 모드/게임 모드는 바로 실행하지 말고 사용자에게 무엇을 할지 먼저 질문
- 모든 컴퓨터 조작은 사용자 승인 후 실행
- 이후 하이브리드 모니터링 기능을 추가할 수 있도록 구조화
- 모니터링은 터미널 로그, 앱 창 UI/OCR, 브라우저 탭 DOM, 현재 화면 OCR, Windows Event Log, VLM adapter를 조합하는 구조

각 문서는 Cursor가 이후 구현 단계에서 참고할 수 있도록 명확하고 구체적으로 작성해줘.