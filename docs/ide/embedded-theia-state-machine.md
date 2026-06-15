# Embedded Theia 상태 머신

## 상태

```text
NOT_STARTED
PREFLIGHT
BACKEND_STARTING
FRONTEND_LOADING
SHELL_PROBING
READY
ERROR
STOPPED
```

## 허용 전이

```text
NOT_STARTED → PREFLIGHT → BACKEND_STARTING → FRONTEND_LOADING → SHELL_PROBING → READY
어느 단계든 실패 → ERROR
앱 종료 → STOPPED
```

## 금지 전이

- `READY` 이후 `loadProgress` / `loadStarted`로 `FRONTEND_LOADING`·`BACKEND_STARTING` 복귀
- Probe 성공 후 Stack을 로딩 페이지로 되돌리기

## 구현

- 단일 진입점: `EmbeddedTheiaView._set_state()`
- READY 유일 경로: `EmbeddedTheiaView._show_ready_webview()`
- 모든 전이: `%USERPROFILE%\.iris\logs\ide-webengine.log` (`[theia-view]` prefix)

## UI 매핑

| 상태 | Stack / Overlay |
|------|-----------------|
| NOT_STARTED | placeholder |
| PREFLIGHT / BACKEND_STARTING | placeholder 또는 web_container + overlay |
| FRONTEND_LOADING / SHELL_PROBING | web_container + overlay 표시 |
| READY | web_container, overlay 숨김 |
| ERROR | error panel |
