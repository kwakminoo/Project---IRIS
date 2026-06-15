# Embedded Theia Readiness Probe

## 목적

`loadFinished(True)`만으로 READY 처리하지 않고, Theia ApplicationShell DOM이 실제로 렌더된 뒤 WebView를 표시한다.

## Selector (Theia 1.55 실제 DOM)

```javascript
'.theia-ApplicationShell'
'#theia-app-shell'
'body.iris-ide-shell'
'.theia-Navigator'
'#theia-left-side-panel'
'.theia-Editor'
'.monaco-editor'
'.p-Panel-main'
```

## 조건

```text
document.readyState === 'complete'
&& !error-page (Cannot GET, Application Error)
&& !preloadOnly (.theia-preload만 있고 shell 없음)
&& (shellFound + bodyLength>80) OR fallbackOk OR wsOk/monaco
```

## 타이밍

| 파라미터 | 값 |
|----------|-----|
| 초기 지연 | 500ms |
| 간격 | 750ms |
| 최대 대기 | 45s |

## 실패 시

- `TheiaShellReadinessFailure` 오류 종류
- 마지막 Probe JSON (`readyState`, `reason`, `title`, `url`, `bodyLength`) 표시
- 무한 재시도 금지

## 성공 시

- `_show_ready_webview()` 단일 호출
- `ready` 시그널 emit

## 금지

- `QTimer.singleShot(5000, mark_ready)` 등 시간만으로 READY 처리
