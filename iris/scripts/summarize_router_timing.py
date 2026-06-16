#!/usr/bin/env python3
"""SQLite router_timing 로그 요약."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "iris.db"


def summarize(db_path: Path, limit: int = 100) -> dict[str, object]:
    if not db_path.exists():
        return {"error": "database_not_found", "path": str(db_path)}

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT message, result FROM logs
            WHERE type = 'router_timing'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    parsed: list[dict[str, object]] = []
    for _msg, result in rows:
        if not result:
            continue
        try:
            parsed.append(json.loads(result))
        except json.JSONDecodeError:
            continue

    if not parsed:
        return {"turns": 0, "note": "no router_timing rows"}

    paths: dict[str, int] = {}
    frontier = sum(1 for p in parsed if p.get("frontier_invoked"))
    total_ms = [int(p["total_latency_ms"]) for p in parsed if p.get("total_latency_ms")]
    first_ms = [
        int(p["first_visible_response_ms"])
        for p in parsed
        if p.get("first_visible_response_ms")
    ]
    model_calls = [int(p.get("model_call_count", 0)) for p in parsed]

    for p in parsed:
        sp = str(p.get("selected_path", "unknown"))
        paths[sp] = paths.get(sp, 0) + 1

    def _avg(vals: list[int]) -> float | None:
        return sum(vals) / len(vals) if vals else None

    return {
        "turns": len(parsed),
        "path_counts": paths,
        "frontier_rate": frontier / len(parsed) if parsed else 0,
        "avg_total_ms": _avg(total_ms),
        "avg_first_visible_ms": _avg(first_ms) if first_ms else None,
        "avg_model_calls": _avg(model_calls),
    }


def main() -> None:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_DB
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    print(json.dumps(summarize(db, limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
