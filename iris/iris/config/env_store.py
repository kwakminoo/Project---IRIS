"""작은 .env 설정 갱신 유틸리티."""

from __future__ import annotations

from pathlib import Path


def update_env_values(path: Path, values: dict[str, str | None]) -> None:
    """기존 주석과 순서를 최대한 보존하며 key=value를 갱신한다."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, _sep, _old = line.partition("=")
        clean_key = key.strip()
        if clean_key not in remaining:
            out.append(line)
            continue
        new_value = remaining.pop(clean_key)
        if new_value is None:
            continue
        out.append(f"{clean_key}={new_value}")

    for key, value in remaining.items():
        if value is None:
            continue
        out.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
