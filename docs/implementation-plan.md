# Iris Implementation Plan / Iris 구현 계획

## Phase 0: Project Setup / 0단계: 프로젝트 준비

Goal:

- Create project rules and design documents.
  - 한국어: 프로젝트 규칙과 설계 문서를 만듭니다.

Tasks:

- Create `AGENTS.md` / AGENTS.md 생성
- Create `.cursor/rules/iris.mdc` / Cursor 규칙 생성
- Create `docs/domain-design.md` / 도메인 설계 생성
- Create `docs/architecture.md` / 아키텍처 문서 생성
- Create `docs/safety-policy.md` / 안전 정책 생성
- Create `docs/implementation-plan.md` / 구현 계획 생성
- Create `.env.example` / 환경 변수 예시 생성

---

## Phase 1: Jarvis-like AI Assistant / 1단계: 자비스형 AI 비서

Goal:

- Build the base assistant before monitoring.
  - 한국어: 모니터링 전에 기본 비서 기능을 만듭니다.

Tasks:

1. PyQt6 main window / PyQt6 메인 창
2. Chat panel / 채팅 패널
3. Visualizer / 시각화
4. State machine / 상태 머신
5. Gemma 4 local LLM client / Gemma 4 로컬 LLM 클라이언트
6. Fallback response / 폴백 응답
7. STT interface / 음성 인식 인터페이스
8. TTS interface / 음성 출력 인터페이스
9. Barge-in structure / 말 끊기 구조
10. App launcher / 앱 실행기
11. Window controller / 창 제어기
12. Layout engine / 레이아웃 엔진
13. Action executor / 실행기
14. Safety guard / 안전장치
15. SQLite logs / SQLite 로그
16. Recent work manager / 최근 작업 관리자
17. Work mode / 작업 모드
18. Game mode / 게임 모드
19. Creative mode / 창작 모드
20. Playwright web agent / Playwright 웹 에이전트
21. Report window / 보고서 창
22. Settings dialog / 설정 창
23. Risk-based automation policy / 위험도 기반 자동화 정책

Validation:

- `python -m iris` opens app.
  - 한국어: 앱이 열립니다.
- Text chat works.
  - 한국어: 텍스트 대화가 동작합니다.
- Local LLM or fallback works.
  - 한국어: 로컬 LLM 또는 폴백이 동작합니다.
- Work mode asks what work to start.
  - 한국어: 작업 모드가 어떤 작업인지 묻습니다.
- Game mode asks which game to start.
  - 한국어: 게임 모드가 어떤 게임인지 묻습니다.
- LOW/MEDIUM/HIGH actions can run without extra approval.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행됩니다.
- CRITICAL actions require approval.
  - 한국어: 4단계 작업은 승인이 필요합니다.
- Logs are saved.
  - 한국어: 로그가 저장됩니다.

---

## Phase 2: Basic Monitoring / 2단계: 기본 모니터링

Goal:

- Add monitoring foundation.
  - 한국어: 모니터링 기반을 추가합니다.

Tasks:

1. target_registry / 대상 등록
2. monitor_manager / 모니터 관리자
3. current screen OCR / 현재 화면 OCR
4. selected window OCR / 선택 창 OCR
5. state_detector / 상태 감지기
6. alert_generator / 알림 생성기
7. notification_panel / 알림 패널
8. monitoring dashboard / 모니터링 대시보드

Validation:

- Can register targets / 대상 등록 가능
- Can detect approval waiting / 승인 대기 감지 가능
- Can detect error text / 오류 텍스트 감지 가능
- Can show alerts / 알림 표시 가능

---

## Phase 3: Hybrid Monitoring / 3단계: 하이브리드 모니터링

Goal:

- Use target-specific methods.
  - 한국어: 대상별 최적 수집 방식을 사용합니다.

Tasks:

1. terminal_log_collector / 터미널 로그 수집기
2. desktop_window_monitor / 데스크톱 창 모니터
3. browser_tab_monitor / 브라우저 탭 모니터
4. Chrome Extension / Chrome 확장
5. windows_event_collector / Windows 이벤트 수집기
6. vlm_adapter stub / VLM 어댑터 스텁
7. event storage / 이벤트 저장
8. cooldown / 알림 쿨다운
9. risk-based action after alert / 알림 후 위험도 기반 조치

Validation:

- Terminal stdout/stderr can be collected.
  - 한국어: 터미널 stdout/stderr 수집 가능.
- Existing terminal window can be read through UI Automation or OCR.
  - 한국어: 기존 터미널 창을 UI Automation/OCR로 읽기 가능.
- Chrome tab status can be sent from extension.
  - 한국어: Chrome 탭 상태를 확장에서 보낼 수 있음.
- Monitoring events are stored.
  - 한국어: 모니터링 이벤트 저장.
- Alerts do not repeat excessively.
  - 한국어: 알림 반복 과다 방지.

---

## Phase 4: Integration / 4단계: 통합

Goal:

- Connect assistant and monitoring.
  - 한국어: 비서 기능과 모니터링 기능을 연결합니다.

Tasks:

1. Monitoring event summary through Gemma 4 / Gemma 4로 모니터링 이벤트 요약
2. Alert-based risk classification / 알림 기반 위험도 분류
3. Auto execution for LOW/MEDIUM/HIGH / 1~3단계 자동 실행
4. Approval flow for CRITICAL / 4단계 승인 흐름
5. Log action result / 실행 결과 로그
6. Add dashboard controls / 대시보드 제어 추가

Validation:

- Iris detects terminal approval waiting.
  - 한국어: Iris가 터미널 승인 대기를 감지합니다.
- Iris classifies the recommended action risk.
  - 한국어: Iris가 추천 조치의 위험도를 분류합니다.
- Iris executes LOW/MEDIUM/HIGH actions directly.
  - 한국어: 1~3단계 조치는 바로 실행합니다.
- Iris asks approval for CRITICAL actions.
  - 한국어: 4단계 조치는 승인을 요청합니다.
- Result is logged.
  - 한국어: 결과가 기록됩니다.

---

## Phase 5: Polish / 5단계: 다듬기

Goal:

- Prepare for demo and competition.
  - 한국어: 데모와 대회 제출을 준비합니다.

Tasks:

1. UI polish / UI 다듬기
2. README / README 정리
3. Demo scenarios / 데모 시나리오
4. Error handling / 오류 처리
5. Presentation script / 발표 스크립트
6. Test data / 테스트 데이터
7. Install script / 설치 스크립트

Demo scenarios:

- Work mode start / 작업 모드 시작
- Game mode start / 게임 모드 시작
- Terminal approval waiting / 터미널 승인 대기
- Midjourney generation failed / Midjourney 생성 실패
- GPT response ready / GPT 응답 완료
- Cursor build not started / Cursor 빌드 미시작
