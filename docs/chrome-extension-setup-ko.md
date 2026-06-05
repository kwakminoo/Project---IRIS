# Iris Chrome 확장 (Iris Tab Monitor)

**URL(사이트) 규칙**으로 동작합니다. 탭 ID마다 허용할 필요 없습니다.

## 설치 (최초 1회)

1. `.\scripts\setup-iris-chrome-extension.ps1` (또는 `chrome://extensions`)
2. 개발자 모드 → **압축해제된 확장 프로그램 로드** → `IRIS/chrome-extension`
3. **Iris Tab Monitor** 툴바 고정

## 사이트 허용 (1회 설정)

1. Iris 실행 (`python -m iris`)
2. 확장 아이콘 → 체크할 사이트 선택 (예: **YouTube 전체**)
3. 포트 `17777` (`.env` `IRIS_EXTENSION_PORT`와 동일) → **설정 저장**

이후 **새 Chrome 탭**, Iris `open_url`로 연 링크, 검색·watch·홈 등 해당 도메인이면 자동 전송됩니다.

## 기본 제공 규칙

| 규칙 ID | 범위 |
|---------|------|
| `youtube_site` | `*.youtube.com` |
| `netflix_site` | `*.netflix.com` |
| `google_site` | `google.com`, `google.co.kr` |
| `naver_site` | `*.naver.com` |

새 사이트 추가: `chrome-extension/url_rules.js`의 `SITE_RULES`·`SITE_RULE_ORDER`에 항목 추가 후 확장 새로고침.

## 포트

| 위치 | 설정 |
|------|------|
| Iris | `iris/.env` → `IRIS_EXTENSION_PORT=17777` |
| 확장 팝업 | 로컬 포트 |

## 레거시

예전 **「현재 탭 허용」**(`irisAllowedTabIds`)만 쓰던 경우, 첫 실행 시 **YouTube 사이트 규칙**으로 자동 승격됩니다.
