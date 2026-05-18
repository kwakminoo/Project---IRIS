"""3계층 메모리: 단기 대화·작업 세션·장기 요약."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from iris.ai.gemma_client import ChatMessage
from iris.storage.database import Database

# 단기: 최근 턴 수·문자 제한
_MAX_SHORT_TURNS = 12
_MAX_SHORT_CHARS = 6000


@dataclass
class ShortTermTurn:
    role: str
    content: str


class MemoryManager:
    """프라이버시: 원문 OCR·스크린샷·PII 저장 금지."""

    def __init__(self, db: Database, session_key: str = "default") -> None:
        self._db = db
        self._session_key = session_key
        self._short: Deque[ShortTermTurn] = deque(maxlen=_MAX_SHORT_TURNS)

    @property
    def session_key(self) -> str:
        return self._session_key

    def set_session_key(self, key: str) -> None:
        self._session_key = key

    # --- 단기 대화 ---

    def add_turn(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        self._short.append(ShortTermTurn(role, text[:2000]))
        self._trim_short_chars()

    def _trim_short_chars(self) -> None:
        total = sum(len(t.content) for t in self._short)
        while total > _MAX_SHORT_CHARS and self._short:
            dropped = self._short.popleft()
            total -= len(dropped.content)

    def short_term_history(self) -> List[ChatMessage]:
        """LLM에 넣을 최근 대화."""
        out: List[ChatMessage] = []
        for t in self._short:
            role = "assistant" if t.role in ("assistant", "Iris") else "user"
            out.append(ChatMessage(role, t.content))
        return out

    # --- 작업 세션 (SQLite) ---

    def load_task_session(self) -> dict:
        row = self._db.get_task_session(self._session_key)
        if not row:
            return {"current_goal": "", "tools_run": [], "observations": [], "approvals": []}
        return {
            "current_goal": str(row["current_goal"] or ""),
            "tools_run": json.loads(str(row["tools_run_json"] or "[]")),
            "observations": json.loads(str(row["observations_json"] or "[]")),
            "approvals": json.loads(str(row["approvals_json"] or "[]")),
        }

    def save_task_session(
        self,
        current_goal: str,
        tools_run: Optional[List[str]] = None,
        observations: Optional[List[str]] = None,
        approvals: Optional[List[str]] = None,
    ) -> None:
        """요약 JSON만 저장 (전체 트랜스크립트 아님)."""
        sess = self.load_task_session()
        if tools_run is not None:
            sess["tools_run"] = (sess.get("tools_run") or []) + tools_run
        if observations is not None:
            sess["observations"] = (sess.get("observations") or []) + observations
        if approvals is not None:
            sess["approvals"] = (sess.get("approvals") or []) + approvals
        # 최근 항목만 유지
        for key in ("tools_run", "observations", "approvals"):
            items = sess.get(key) or []
            if len(items) > 30:
                sess[key] = items[-30:]
        self._db.upsert_task_session(
            self._session_key,
            current_goal or sess.get("current_goal") or "",
            json.dumps(sess.get("tools_run") or [], ensure_ascii=False),
            json.dumps(sess.get("observations") or [], ensure_ascii=False),
            json.dumps(sess.get("approvals") or [], ensure_ascii=False),
        )

    def task_session_summary_for_prompt(self) -> str:
        """프롬프트용 작업 세션 요약."""
        sess = self.load_task_session()
        goal = sess.get("current_goal") or ""
        if not goal and not sess.get("observations"):
            return ""
        lines = []
        if goal:
            lines.append(f"현재 목표: {goal}")
        obs = sess.get("observations") or []
        if obs:
            lines.append("최근 관찰:")
            for o in obs[-5:]:
                lines.append(f"- {str(o)[:200]}")
        tools = sess.get("tools_run") or []
        if tools:
            lines.append("최근 도구: " + ", ".join(str(t) for t in tools[-8:]))
        return "\n".join(lines)

    # --- 장기 요약 ---

    def add_long_term_summary(self, category: str, summary: str, source_hint: str = "") -> None:
        text = (summary or "").strip()
        if not text:
            return
        self._db.insert_memory_summary(category, text[:2000], source_hint[:500])

    def long_term_context_for_prompt(self, limit: int = 8) -> str:
        rows = self._db.list_memory_summaries(limit=limit)
        if not rows:
            return ""
        lines = ["[장기 기억 요약]"]
        for row in rows:
            cat = str(row["category"])
            summ = str(row["summary"])[:300]
            lines.append(f"- ({cat}) {summ}")
        return "\n".join(lines)

    def build_extra_context(self) -> str:
        """prompt_builder에 주입할 통합 컨텍스트."""
        parts: list[str] = []
        task = self.task_session_summary_for_prompt()
        if task:
            parts.append("[작업 세션]\n" + task)
        long_ = self.long_term_context_for_prompt()
        if long_:
            parts.append(long_)
        return "\n\n".join(parts)
