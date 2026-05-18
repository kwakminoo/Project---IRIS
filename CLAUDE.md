# CLAUDE.md

This project is Iris.

- 한국어 설명: 이 프로젝트는 Iris입니다.

Iris is a local-first personal AI assistant for Windows.

- 한국어 설명: Iris는 Windows용 로컬 우선 개인 AI 비서입니다.

The main reference documents are:

1. `AGENTS.md`
   - 한국어: 최상위 에이전트 지침입니다.
2. `.cursor/rules/iris.mdc`
   - 한국어: Cursor용 규칙입니다.
3. `docs/domain-design.md`
   - 한국어: 도메인 설계 문서입니다.
4. `docs/architecture.md`
   - 한국어: 아키텍처 문서입니다.
5. `docs/safety-policy.md`
   - 한국어: 안전 정책 문서입니다.
6. `docs/implementation-plan.md`
   - 한국어: 구현 계획 문서입니다.

## Important Rules / 중요 규칙

- Do not rename the project.
  - 한국어: 프로젝트 이름을 바꾸지 않습니다.
- Do not use Dexter as the project name.
  - 한국어: Dexter를 프로젝트 이름으로 쓰지 않습니다.
- Use Gemma 4 local LLM as the primary model direction.
  - 한국어: Gemma 4 로컬 LLM을 기본 방향으로 사용합니다.
- Do not make Claude API or Gemini API the default model.
  - 한국어: Claude/Gemini API를 기본 모델로 만들지 않습니다.
- Use risk-based permission control.
  - 한국어: 위험도 기반 권한 제어를 사용합니다.
- LOW_RISK, MEDIUM_RISK, and HIGH_RISK actions may run without extra approval.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행될 수 있습니다.
- CRITICAL_RISK actions require explicit user approval.
  - 한국어: 4단계 작업은 명시적 사용자 승인이 필요합니다.
- Never bypass Safety Guard.
  - 한국어: Safety Guard를 우회하지 않습니다.
- Do not store raw screenshots or full OCR text by default.
  - 한국어: 원본 스크린샷이나 전체 OCR 텍스트는 기본 저장하지 않습니다.
- Keep assistant, automation, monitoring, UI, and storage layers separated.
  - 한국어: 비서, 자동화, 모니터링, UI, 저장소 계층을 분리합니다.

## Implementation Style / 구현 방식

Before editing code:

1. Read `AGENTS.md`.
   - 한국어: AGENTS.md를 읽습니다.
2. Read `docs/domain-design.md`.
   - 한국어: 도메인 설계를 읽습니다.
3. Read `docs/architecture.md`.
   - 한국어: 아키텍처 문서를 읽습니다.
4. Read `docs/safety-policy.md`.
   - 한국어: 안전 정책을 읽습니다.
5. Explain the plan briefly.
   - 한국어: 계획을 짧게 설명합니다.
6. Then modify code.
   - 한국어: 그 다음 코드를 수정합니다.

If a requested change conflicts with Safety Guard, refuse to implement it directly and suggest a safer alternative.

- 한국어 설명: 요청이 Safety Guard와 충돌하면 직접 구현하지 말고 더 안전한 대안을 제안합니다.
