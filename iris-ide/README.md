# Iris IDE (Eclipse Theia Browser)

Iris MainWindow에 내장되는 Theia Browser Application입니다.

## 요구 사항

- Node.js 18+
- Yarn 1.x

## 빠른 시작

```powershell
..\..\scripts\setup-iris-ide.ps1
..\..\scripts\build-iris-ide.ps1
..\..\scripts\start-iris-ide-backend.ps1 -Workspace "C:\path\to\project"
```

Iris 앱에서는 **IDE** 버튼으로 자동 시작됩니다.

## 구조

- `applications/browser` — Theia Browser 앱
- `theia-extensions/iris-product` — 다크 테마·레이아웃
- `theia-extensions/iris-bridge` — Iris Python ↔ Theia context bridge

## 환경 변수

- `IRIS_IDE_WORKSPACE_PATH` — 기본 workspace (미설정 시 저장소 루트)
