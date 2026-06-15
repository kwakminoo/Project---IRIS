# Embedded IDE Troubleshooting

## 증상별 원인

| 메시지 | 원인 | 조치 |
|--------|------|------|
| PyQt6-WebEngine을 사용할 수 없습니다 | venv에 WebEngine 미설치 | `pip install PyQt6-WebEngine==6.11.0` 또는 IDE 화면 **환경 복구** |
| Theia Build 없음 | `main.js` 없음 | `scripts\build-iris-ide.ps1` |
| Node 없음 | Node/yarn 미설치 | `scripts\setup-iris-ide.ps1` |
| Backend 조기 종료 | native module ABI 불일치 | setup 후 node-pty 등 rebuild |
| Backend Timeout | 포트·방화벽·빌드 손상 | `ide-backend.log` tail 확인 |
| Frontend Load 실패 | backend 미기동·URL 오류 | 브라우저에서 동일 URL 직접 열기 |
| Render Process 종료 | GPU/Chromium | `ide-webengine.log` 확인 |
| Theia Shell 준비 실패 | frontend 로드됐으나 workbench 미완성 | 브라우저에서 동일 URL 확인 |

## 진단 순서

1. `.\scripts\diagnose-iris-ide.ps1`
2. `.\iris\.venv\Scripts\python.exe .\iris\scripts\smoke_webengine.py`
3. `.\scripts\start-iris-ide-backend.ps1` → Edge/Chrome `http://127.0.0.1:3100`
4. Iris IDE 버튼 → **로그 보기**

## 로그 위치

```
%USERPROFILE%\.iris\logs\
  ide-preflight.log
  ide-backend.log
  ide-webengine.log
  ide-recovery.log
```

## Iris UI 버튼

- **다시 시도** — backend 정리 후 preflight·재로드
- **환경 진단** — `diagnose-iris-ide.ps1` 실행
- **IDE 환경 복구** — PyQt6-WebEngine 6.11.0 pip 설치
- **로그 보기** — preflight/backend/webengine tail

## 빌드 EBUSY

Iris·Theia backend가 `.node` 파일을 잡고 있으면 webpack 실패.

1. Iris 완전 종료
2. `scripts\build-iris-ide.ps1` 재실행

## QWebEngine만 실패·브라우저는 성공

Host/WebSocket/CSP 이슈 가능. `127.0.0.1`만 허용하는 기존 정책 유지.

`ide-webengine.log`에서 WebSocket·CSP 오류 확인.
