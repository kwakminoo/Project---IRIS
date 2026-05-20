"""앱 인덱스 스캔·병합·목표 문구 매칭 (LLM에 전체 목록 노출 금지)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from iris.config.app_paths import detect_app_paths
from iris.storage.database import Database

try:
    import winreg  # type: ignore
except ImportError:
    winreg = None  # type: ignore

# Windows .lnk → exe (테스트에서 주입 가능)
_lnk_resolver: Callable[[Path], str | None] | None = None


@dataclass(frozen=True)
class AppScanResult:
    app_key: str
    display_name: str
    exe_path: str
    source: str = "scan"


def set_lnk_resolver(resolver: Callable[[Path], str | None] | None) -> None:
    """단위 테스트용 .lnk 해석기 주입."""
    global _lnk_resolver
    _lnk_resolver = resolver


def slug_app_key(name: str) -> str:
    """표시명·파일명에서 논리 키 생성."""
    stem = Path(name).stem if "." in name else name
    key = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return key or "app"


def is_runnable_exe(path: str | Path) -> bool:
    """실행 가능한 exe인지 경로만 검증 (프로세스 기동 없음)."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        if p.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if os.name == "nt":
        return p.suffix.lower() in (".exe", ".bat", ".cmd", ".com", ".msc")
    return os.access(p, os.X_OK)


def verify_exe_stable(
    exe_path: str | Path,
    *,
    checks: int = 2,
    interval_sec: float = 1.5,
) -> bool:
    """
    설치 완료 휴리스틱: 연속 checks회 동일 경로·크기 안정.
    interval_sec>0 이면 sleep (watcher·통합 테스트용).
    """
    import time

    p = Path(exe_path)
    last_size: int | None = None
    for i in range(max(1, checks)):
        if not is_runnable_exe(p):
            return False
        size = p.stat().st_size
        if last_size is not None and size != last_size:
            return False
        last_size = size
        if i + 1 < checks and interval_sec > 0:
            time.sleep(interval_sec)
    return True


def resolve_lnk(lnk_path: Path) -> str | None:
    """시작 메뉴 .lnk → 대상 exe."""
    if _lnk_resolver is not None:
        return _lnk_resolver(lnk_path)
    if os.name != "nt" or not lnk_path.is_file():
        return None
    try:
        import win32com.client  # type: ignore

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk_path.resolve()))
        target = getattr(shortcut, "TargetPath", None)
        return str(target) if target else None
    except Exception:
        pass
    try:
        import subprocess

        ps = (
            f"(New-Object -ComObject WScript.Shell)"
            f".CreateShortcut('{str(lnk_path.resolve())}').TargetPath"
        )
        r = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        out = (r.stdout or "").strip()
        return out if out and Path(out).exists() else None
    except Exception:
        return None


def _scan_registry_app_paths() -> List[AppScanResult]:
    if winreg is None:
        return []
    results: List[AppScanResult] = []
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, base) as root:
                idx = 0
                while True:
                    try:
                        subname = winreg.EnumKey(root, idx)
                        idx += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, subname) as sub:
                            val, _ = winreg.QueryValueEx(sub, "")
                    except OSError:
                        continue
                    if not isinstance(val, str):
                        continue
                    exe = val.strip('"').strip()
                    if not is_runnable_exe(exe):
                        continue
                    key = slug_app_key(subname)
                    disp = Path(subname).stem
                    results.append(AppScanResult(key, disp, exe, "scan"))
        except OSError:
            continue
    return results


def _start_menu_roots() -> List[Path]:
    roots: List[Path] = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env, "")
        if not base:
            continue
        sm = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if sm.is_dir():
            roots.append(sm)
    return roots


def _scan_start_menu() -> List[AppScanResult]:
    results: List[AppScanResult] = []
    seen_exe: set[str] = set()
    for root in _start_menu_roots():
        for lnk in root.rglob("*.lnk"):
            exe = resolve_lnk(lnk)
            if not exe or not is_runnable_exe(exe):
                continue
            norm = str(Path(exe).resolve()).lower()
            if norm in seen_exe:
                continue
            seen_exe.add(norm)
            disp = lnk.stem
            key = slug_app_key(disp)
            results.append(AppScanResult(key, disp, exe, "scan"))
    return results


def builtin_scan_fallbacks() -> List[AppScanResult]:
    """스캔 보조 — 메모장 등 시스템 기본 앱."""
    out: List[AppScanResult] = []
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    notepad = Path(sysroot) / "System32" / "notepad.exe"
    if is_runnable_exe(notepad):
        out.append(AppScanResult("notepad", "메모장", str(notepad), "scan"))
    calc = Path(sysroot) / "System32" / "calc.exe"
    if is_runnable_exe(calc):
        out.append(AppScanResult("calc", "계산기", str(calc), "scan"))
    return out


def scan_installed_apps() -> List[AppScanResult]:
    """App Paths + 시작 메뉴 + 내장 fallback (Program Files 재귀 스캔 없음)."""
    by_key: Dict[str, AppScanResult] = {}
    for batch in (
        _scan_registry_app_paths(),
        _scan_start_menu(),
        builtin_scan_fallbacks(),
    ):
        for item in batch:
            if item.app_key not in by_key:
                by_key[item.app_key] = item
    return list(by_key.values())


def scan_results_as_tuples(results: Iterable[AppScanResult]) -> list[tuple[str, str, str, str]]:
    return [(r.app_key, r.display_name, r.exe_path, r.source) for r in results]


def build_merged_app_paths(db: Database | None = None) -> Dict[str, str]:
    """detect_app_paths + DB 인덱스 병합 → launch_by_key용 dict."""
    merged = dict(detect_app_paths())
    if db is None:
        return merged
    for row in db.list_app_launcher_entries():
        exe = str(row["exe_path"])
        if is_runnable_exe(exe):
            merged[str(row["app_key"])] = exe
    return merged


def run_background_scan(db: Database) -> tuple[int, list[str]]:
    """스캔 후 DB merge. (신규 수, 신규 표시명)."""
    results = scan_installed_apps()
    return db.merge_scan_results(scan_results_as_tuples(results))


# --- fuzzy match (top-K, 코드 전용) ---

_ALIAS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"메모장|notepad", re.I), "notepad"),
    (re.compile(r"계산기|calc", re.I), "calc"),
    (re.compile(r"커서|\bCursor\b", re.I), "code"),
    (re.compile(r"크롬|\bChrome\b", re.I), "chrome"),
    (re.compile(r"엣지|\bEdge\b", re.I), "edge"),
    (re.compile(r"디스코드|\bDiscord\b", re.I), "discord"),
    (re.compile(r"파이썬|\bPython\b", re.I), "python"),
    (re.compile(r"스팀|\bSteam\b", re.I), "steam"),
]


def _alias_key(text: str) -> str | None:
    for pat, key in _ALIAS_PATTERNS:
        if pat.search(text):
            return key
    return None


def _score_match(query: str, app_key: str, display_name: str) -> float:
    q = query.lower().strip()
    if not q:
        return 0.0
    if q in app_key.lower() or q in display_name.lower():
        return 1.0
    return max(
        SequenceMatcher(None, q, app_key.lower()).ratio(),
        SequenceMatcher(None, q, display_name.lower()).ratio(),
    )


def resolve_app_for_goal(
    text: str,
    app_paths: Dict[str, str],
    *,
    db: Database | None = None,
    top_k: int = 5,
) -> Tuple[str | None, str | None]:
    """
    사용자 목표 문구 → (app_key, exe_path). LLM 없이 top-K 휴리스틱.
    """
    alias = _alias_key(text)
    if alias and alias in app_paths:
        return alias, app_paths[alias]

    candidates: list[tuple[float, str, str]] = []
    rows: Sequence = ()
    if db is not None:
        rows = db.list_app_launcher_entries()
    for row in rows:
        key = str(row["app_key"])
        disp = str(row["display_name"])
        path = app_paths.get(key) or str(row["exe_path"])
        if not is_runnable_exe(path):
            continue
        sc = _score_match(text, key, disp)
        if sc >= 0.45:
            candidates.append((sc, key, path))

    for key, path in app_paths.items():
        disp = key
        if db is not None:
            row = db.get_app_launcher_entry(key)
            if row:
                disp = str(row["display_name"])
        sc = _score_match(text, key, disp)
        if sc >= 0.45:
            candidates.append((sc, key, path))

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:top_k]
    _, best_key, best_path = top[0]
    return best_key, best_path


def display_name_for_key(app_key: str, db: Database | None = None) -> str:
    if db is not None:
        row = db.get_app_launcher_entry(app_key)
        if row:
            return str(row["display_name"])
    return app_key


def resolve_app_candidates_for_llm(
    user_text: str,
    app_paths: Dict[str, str],
    *,
    db: Database | None = None,
    top_k: int = 8,
) -> List[Dict[str, str]]:
    """
    alias·퍼지·DB display_name으로 LLM용 앱 후보만 반환 (경로·exe 미포함).
    전체 앱 목록을 프롬프트에 넣지 않기 위한 top-K 압축 catalog.
    """
    k = max(1, min(int(top_k), 8))
    scored: list[tuple[float, str, str]] = []
    seen_keys: set[str] = set()

    alias = _alias_key(user_text)
    if alias:
        disp = display_name_for_key(alias, db)
        path = app_paths.get(alias)
        if path is None and db is not None:
            row = db.get_app_launcher_entry(alias)
            if row:
                path = str(row["exe_path"])
        if path and is_runnable_exe(path):
            scored.append((1.5, alias, disp))
            seen_keys.add(alias)

    rows: Sequence = ()
    if db is not None:
        rows = db.list_app_launcher_entries()
    for row in rows:
        key = str(row["app_key"])
        if key in seen_keys:
            continue
        disp = str(row["display_name"])
        path = app_paths.get(key) or str(row["exe_path"])
        if not is_runnable_exe(path):
            continue
        sc = _score_match(user_text, key, disp)
        if sc >= 0.35:
            scored.append((sc, key, disp))

    for key, path in app_paths.items():
        if key in seen_keys:
            continue
        disp = display_name_for_key(key, db)
        sc = _score_match(user_text, key, disp)
        if sc >= 0.35:
            scored.append((sc, key, disp))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, str]] = []
    for _, key, disp in scored:
        if key in seen_keys and any(e["app_key"] == key for e in out):
            continue
        seen_keys.add(key)
        out.append({"app_key": key, "display_name": disp})
        if len(out) >= k:
            break
    return out
