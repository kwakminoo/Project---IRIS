# Embedded Theia 개발 가이드

## 사전 요구

- Node.js 18+
- Yarn 1.x
- Python: `PyQt6-WebEngine` (`requirements-windows.txt`)

## 설치·빌드

```powershell
.\scripts\setup-iris-ide.ps1
.\scripts\build-iris-ide.ps1
```

## 수동 Backend 실행

```powershell
.\scripts\start-iris-ide-backend.ps1 -Workspace "C:\path\to\project" -Port 3100
```

## Workspace 경로

환경 변수 `IRIS_IDE_WORKSPACE_PATH` 또는 Settings `ide_workspace_path`.  
미설정 시 IRIS 저장소 루트.

## 패키징

```powershell
.\scripts\package-iris-ide.ps1
```

산출물: `iris/iris/resources/ide/lib/`

## 확장

- `iris-ide/theia-extensions/iris-product` — 테마
- `iris-ide/theia-extensions/iris-bridge` — context bridge
