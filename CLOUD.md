# CLOUD.md

## Cloud Policy for Iris / Iris 클라우드 정책

Iris is designed as a local-first AI assistant.

- 한국어 설명: Iris는 로컬 우선 AI 비서로 설계됩니다.

The default architecture should not depend on cloud services for core functionality.

- 한국어 설명: 핵심 기능은 기본적으로 클라우드 서비스에 의존하지 않아야 합니다.

## Local-First Requirements / 로컬 우선 요구사항

The following features should work locally whenever possible:

- LLM response through Gemma 4 local model.
  - 한국어: Gemma 4 로컬 모델로 LLM 응답.
- Text chat.
  - 한국어: 텍스트 대화.
- App launching.
  - 한국어: 앱 실행.
- Window control.
  - 한국어: 창 제어.
- Risk-based keyboard and mouse control.
  - 한국어: 위험도 기반 키보드·마우스 제어.
- SQLite logging.
  - 한국어: SQLite 로그 저장.
- Basic monitoring.
  - 한국어: 기본 모니터링.
- OCR-based detection.
  - 한국어: OCR 기반 감지.
- STT/TTS where possible.
  - 한국어: 가능한 경우 로컬 STT/TTS.

## Cloud Services / 클라우드 서비스

Cloud services are optional and must not be required for basic operation.

- 한국어 설명: 클라우드 서비스는 선택 사항이며 기본 동작에 필수이면 안 됩니다.

Examples of optional cloud use:

- External LLM API for testing.
  - 한국어: 테스트용 외부 LLM API.
- Cloud TTS if local TTS is unavailable.
  - 한국어: 로컬 TTS가 불가할 때 클라우드 TTS.
- Cloud STT if local STT is unavailable.
  - 한국어: 로컬 STT가 불가할 때 클라우드 STT.
- Remote sync in future versions.
  - 한국어: 향후 원격 동기화.

## Restrictions / 제한 사항

Do not send the following to cloud services by default:

- Raw screenshots.
  - 한국어: 원본 스크린샷.
- Full OCR text.
  - 한국어: 전체 OCR 텍스트.
- Passwords.
  - 한국어: 비밀번호.
- Personal data.
  - 한국어: 개인정보.
- Browser content from private pages.
  - 한국어: 비공개 페이지의 브라우저 내용.
- Payment pages.
  - 한국어: 결제 페이지.
- Login forms.
  - 한국어: 로그인 폼.
- Sensitive documents.
  - 한국어: 민감 문서.

## Future Cloud Expansion / 향후 클라우드 확장

If Iris later supports cloud sync or user accounts, create a separate cloud architecture document.

- 한국어 설명: 나중에 클라우드 동기화나 사용자 계정을 지원한다면 별도 클라우드 아키텍처 문서를 만듭니다.

For now, Iris must remain usable without cloud deployment.

- 한국어 설명: 현재 Iris는 클라우드 배포 없이도 사용할 수 있어야 합니다.
