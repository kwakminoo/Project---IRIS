"""Registered API/MCP integration endpoint caller."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


@dataclass(frozen=True)
class IntegrationRecord:
    """Row shape for integration_endpoints."""

    name: str
    kind: str  # api | mcp
    base_url: str
    command: str
    auth_header: str
    enabled: bool
    notes: str = ""


class IntegrationClient:
    """Runs a registered integration endpoint."""

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
        """action is an API path or MCP tool name. Returns (success, message, detail)."""
        if not self._record.enabled:
            return False, "disabled integration (비활성)", self._record.name
        payload = dict(params) if params else {}
        act = (action or "").strip()
        if not act:
            return False, "action is required", ""

        kind = self._record.kind
        if kind == "api":
            return self._call_http_api(act, payload)
        if kind == "mcp":
            if self._record.base_url:
                return self._call_mcp_http(act, payload)
            if self._record.command:
                return self._call_mcp_stdio(act, payload)
            return False, "MCP base_url or command is required", ""
        return False, f"unknown integration kind: {kind}", ""

    def call_json(self, action: str, params: Mapping[str, Any] | None = None) -> tuple[bool, str, Any]:
        ok, msg, detail = self.call(action, params)
        if not ok:
            return ok, msg, detail
        try:
            return ok, msg, json.loads(detail)
        except (TypeError, json.JSONDecodeError):
            return ok, msg, detail

    def list_tools(self) -> tuple[bool, str, list[dict[str, Any]]]:
        """MCP tools/list discovery."""
        if not self._record.enabled:
            return False, "disabled integration (비활성)", []
        if self._record.kind != "mcp":
            return False, "tools/list requires an MCP endpoint", []
        if self._record.base_url:
            return self._list_mcp_http_tools()
        if self._record.command:
            return self._list_mcp_stdio_tools()
        return False, "MCP base_url or command is required", []

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
            return False, "API base_url is empty.", ""
        path = action if action.startswith("/") else f"/{action}"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = (
                    client.post(f"{base}{path}", json=params, headers=self._headers())
                    if params
                    else client.get(f"{base}{path}", headers=self._headers())
                )
            body = resp.text[:4000]
            if resp.is_success:
                return True, f"API call ok ({resp.status_code})", body
            return False, f"API error HTTP {resp.status_code}", body
        except Exception as exc:
            return False, f"API connection failed: {exc}", ""

    def _mcp_url(self) -> str:
        url = self._record.base_url
        if not url.endswith("/"):
            url += "/"
        return url if "mcp" in url.lower() else f"{url}mcp"

    def _call_mcp_http(self, tool_name: str, arguments: Mapping[str, Any]) -> tuple[bool, str, str]:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": dict(arguments)},
        }
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(self._mcp_url(), json=req, headers=self._headers())
            body = resp.text[:4000]
            if not resp.is_success:
                return False, f"MCP HTTP {resp.status_code}", body
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return False, f"MCP error: {msg}", body
            result = data.get("result") if isinstance(data, dict) else data
            return True, "MCP call ok", json.dumps(result, ensure_ascii=False)[:3000]
        except Exception as exc:
            return False, f"MCP HTTP connection failed: {exc}", ""

    def _list_mcp_http_tools(self) -> tuple[bool, str, list[dict[str, Any]]]:
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(self._mcp_url(), json=req, headers=self._headers())
            if not resp.is_success:
                return False, f"MCP HTTP {resp.status_code}", []
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return False, f"MCP error: {msg}", []
            result = data.get("result") if isinstance(data, dict) else {}
            tools = result.get("tools", []) if isinstance(result, dict) else []
            return True, "MCP tools/list ok", [t for t in tools if isinstance(t, dict)]
        except Exception as exc:
            return False, f"MCP HTTP tools/list failed: {exc}", []

    def _run_mcp_stdio(self, method: str, params: Mapping[str, Any]) -> tuple[bool, str, Any]:
        cmd = self._record.command.strip()
        if not cmd:
            return False, "MCP command is empty", None
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
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": method, "params": dict(params)}, ensure_ascii=False),
        ]
        try:
            proc = subprocess.run(
                shlex.split(cmd, posix=False),
                input="\n".join(lines) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            out = proc.stdout or ""
            if proc.returncode != 0:
                return False, f"MCP process exited {proc.returncode}", (proc.stderr or out)[:4000]
            for line in reversed(out.splitlines()):
                try:
                    data = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if data.get("id") != 2:
                    continue
                if data.get("error"):
                    err = data["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    return False, f"MCP error: {msg}", out[:4000]
                return True, "MCP stdio ok", data.get("result")
            return False, "MCP stdio response not found", out[:4000]
        except subprocess.TimeoutExpired:
            return False, "MCP stdio timeout", None
        except Exception as exc:
            return False, f"MCP stdio failed: {exc}", None

    def _call_mcp_stdio(self, tool_name: str, arguments: Mapping[str, Any]) -> tuple[bool, str, str]:
        ok, msg, result = self._run_mcp_stdio(
            "tools/call",
            {"name": tool_name, "arguments": dict(arguments)},
        )
        return ok, msg, json.dumps(result, ensure_ascii=False)[:3000] if ok else str(result or "")

    def _list_mcp_stdio_tools(self) -> tuple[bool, str, list[dict[str, Any]]]:
        ok, msg, result = self._run_mcp_stdio("tools/list", {})
        if not ok:
            return False, msg, []
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return True, msg, [t for t in tools if isinstance(t, dict)]
