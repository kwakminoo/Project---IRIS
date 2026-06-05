# SearXNG 설정 (Iris 웹 검색, 다중 엔진)

Iris는 일반/뉴스 검색(`WEB_SEARCH` 등)에 SearXNG JSON API를 사용할 수 있습니다.  
이 저장소의 `scripts/searxng/settings.yml`은 **단일 Google 엔진에 의존하지 않도록** 검색 엔진을 다중으로 쓰도록 되어 있습니다.

## 1. SearXNG 실행 (Docker)

**Docker Desktop**이 필요합니다. `docker` 명령이 없으면:

```powershell
winget install -e --id Docker.DockerDesktop
```

설치 후 **Docker Desktop**을 한 번 실행한 뒤:

```powershell
.\scripts\setup-searxng.ps1
```

또는:

```powershell
cd scripts\searxng
$env:PATH = "C:\Program Files\Docker\Docker\resources\bin;" + $env:PATH
docker compose up -d
```

> 새 PowerShell에서 `docker`를 못 찾으면 위 PATH 줄을 먼저 실행하거나 PC를 재로그인하세요.

브라우저에서 http://127.0.0.1:8080 이 열리면 준비 완료입니다.

## 2. Iris `.env`

`iris/.env`에 추가:

```env
SEARXNG_BASE_URL=http://127.0.0.1:8080
# SearXNG만 쓰려면:
# IRIS_SEARCH_PROVIDER=searxng
```

`IRIS_SEARCH_PROVIDER=searxng`이면 SearXNG만 사용합니다.  
`local`(기본)일 때는 **SearXNG** → DuckDuckGo HTML 순입니다.

## 3. 다중 엔진 keep_only 설정

`scripts/searxng/settings.yml`의 `keep_only` 예시:

```yaml
use_default_settings:
  engines:
    keep_only:
      - google
      - bing
      - duckduckgo
      - wikipedia
```

엔진 목록 변경 후에는 컨테이너 재시작:

```powershell
docker compose restart
```

## 4. 문제 해결

- **Internal Server Error**: `use_default_settings: true`와 `keep_only`를 동시에 쓰지 않았는지 확인.
- **Iris가 결과 없음**: Google 엔진 CAPTCHA — SearXNG 로그 `docker compose logs -f` 확인. DuckDuckGo HTML 또는 Playwright 폴백을 사용할 수 있습니다.
- **secret_key**: 운영 환경에서는 `settings.yml`의 `server.secret_key`를 긴 랜덤 문자열로 바꾸세요.
