# TTS / UI 첫 글자 분리 — 후속 작업

## 현재 (Phase 9 최소 구현)

- `IRIS_TEXT_TTS_SYNC_MODE=fast`: 스트리밍 chunk 즉시 `append_stream_chunk`, TTS 동기 타이핑 생략
- `synchronized`: 기존 TTS-타이핑 동기화 유지
- `router_telemetry.mark_ui_first_character_active()` 로 첫 글자 시각 계측

## 후속 (선택)

- 스트리밍 경로에서 첫 문장 완성 후 TTS만 비동기 시작
- `chat_panel` speech_sync와 stream 경로 완전 분리 검증
