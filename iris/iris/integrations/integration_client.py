"""SQLite에 등록된 API·MCP 엔드포인트 호출."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


@dataclass(frozen=True)
class IntegrationRecord:
    """integration_endpoints 테이블 한 행."""

    name: str
    kind: str  # api | mcp
    base_url: str
    command: str
    auth_header: str
    enabled: bool
    notes: str = ""


class IntegrationClient:
    """등록된 연동 엔드포인트 실행."""

    def __init__(self, record: IntegrationRecord) -> None:
        self._record = record

    @staticmethod
    def from_row(row: Mapping[str, Any]) -> IntegrationRecord:
        return IntegrationRecord(
            name=str(row.get("name") or "").strip(),
            kind=str(row.get("kind") or "api").strip().lower(),
            base_url=str(row.get("base_url") or "").strip().rstrip("/"),
            command=str(row.get("command") or "").strip(),
            auth_header=str(row.get("auth_header") or "").strip(),
            enabled=bool(row.get("enabled", 1)),
            notes=str(row.get("notes") or ""),
        )

    def call(self, action: str, params: Mapping[str, Any] | None = None) -> tuple[bool, str, str]:
        """action: API 경로 또는 MCP tool 이름. 반환 (success, message, detail)."""
        if not self._record.enabled:
            return False, "비활성 연동입니다.", self._record.name
        payload = dict(params) if params else {}
        act = (action or "").strip()
        if not act:
            return False, "action이 필요합니다.", ""

        kind = self._record.kind
        if kind == "api":
            return self._call_http_api(act, payload)
        if kind == "mcp":
            if self._record.base_url:
                return self._call_mcp_http(act, payload)
            if self._record.command:
                return self._call_mcp_stdio(act, payload)
            return False, "MCP base_url 또는 command가 필요합니다.", ""
        return False, f"알 수 없는 연동 종류: {kind}", ""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth_raw = self._record.auth_header.strip()
        if auth_raw:
            if ":" in auth_raw:
                key, val = auth_raw.split(":", 1)
                headers[key.strip()] = val.strip()
            else:
                headers["Authorization"] = auth_raw
        return headers

    def _call_http_api(self, action: str, params: Mapping[str, Any]) -> tuple[bool, str, str]:
        base = self._record.base_url
        if not base:
            return False, "API base_url이 비어 있습니다.", ""
        path = action if action.startswith("/") else f"/{action}"
        url = f"{base}{path}"
        try:
            with httpx.Client(timeout=30.0) as client:
                if params:
                    resp = client.post(url, json=params, headers=self._headers())
                else:
                    resp = client.get(url, headers=self._headers())
            body = resp.text[:4000]
            if resp.is_success:
                return True, f"API 호출 성공 ({resp.status_code})", body
            return False, f"API 오류 HTTP {resp.status_code}", body
        except Exception as exc:
            return False, f"API 연결 실패: {exc}", ""

    def _call_mcp_http(self, tool_name: str, arguments: Mapping[str, Any]) -> tuple[bool, str, str]:
        """MCP Streamable HTTP / JSON-RPC tools/call (단순 POST)."""
        url = self._record.base_url
        if not url.endswith("/"):
            url = url + "/"
        rpc_url = url if "mcp" in url.lower() else f"{url}mcp"
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": dict(arguments)},
        }
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(rpc_url, json=req, headers=self._headers())
            body = resp.text[:4000]
            if not resp.is_success:
                return False, f"MCP HTTP {resp.status_code}", body
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return False, f"MCP 오류: {msg}", body
            result = data.get("result") if isinstance(data, dict) else data
            return True, "MCP 호출 성공", json.dumps(result, ensure_ascii=False)[:3000]
        except Exception as exc:
            return False, f"MCP HTTP 연결 실패: {exc}", ""

    def _call_mcp_stdio(self, tool_name: str, arguments: Mapping[str, Any]) -> tuple[bool, str, str]:
        """MCP stdio — initialize + tools/call (단일 요청 배치)."""
        cmd = self._record.command.strip()
        if not cmd:
            return False, "MCP command가 비어 있습니다.", ""
        lines = [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "iris", "version": "1.0"},
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": dict(arguments)},
                },
                ensure_ascii=False,
            ),
        ]
        stdin_blob = "\n".join(lines) + "\n"
        try:
            argv = shlex.split(cmd, posix=False)
            proc = subprocess.run(
                argv,
                input=stdin_blob,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            out = (proc.stdout or "")[:4000]
            err = (proc.stderr or "")[:800]
            if proc.returncode != 0:
                return False, f"MCP 프로세스 종료 코드 {proc.returncode}", err or out
            for line in reversed(out.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("id") == 2:
                    if data.get("error"):
                        err_obj = data["error"]
                        msg = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
                        return False, f"MCP 오류: {msg}", out
                    return True, "MCP stdio 호출 성공", json.dumps(
                        data.get("result"), ensure_ascii=False
                    )[:3000]
            return True, "MCP stdio 완료", out
        except subprocess.TimeoutExpired:
            return False, "MCP stdio 시간 초과", ""
        except Exception as exc:
            return False, f"MCP stdio 실행 실패: {exc}", ""
