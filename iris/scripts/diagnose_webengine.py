#!/usr/bin/env python3
"""PyQt6 WebEngine import·DLL·QtWebEngineProcess 진단."""

from __future__ import annotations

import glob
import os
import sys
import traceback

EXIT_OK = 0
EXIT_WEBENGINE = 1


def _pip_list_qt() -> list[str]:
    try:
        from importlib.metadata import distributions

        names = sorted(
            d.metadata["Name"]
            for d in distributions()
            if d.metadata.get("Name", "").lower().startswith("pyqt6")
        )
        return names
    except Exception:
        return []


def main() -> int:
    print("=== Iris WebEngine Diagnose ===")
    print(f"sys.executable: {sys.executable}")
    print(f"version: {sys.version}")
    print(f"64bit: {sys.maxsize > 2**32}")
    print(f"venv: {os.environ.get('VIRTUAL_ENV', '(none)')}")
    print(f"pip: {sys.executable} -m pip")

    for dist in ("PyQt6", "PyQt6-Qt6", "PyQt6_sip", "PyQt6-WebEngine", "PyQt6-WebEngine-Qt6"):
        try:
            from importlib.metadata import version

            print(f"{dist}: {version(dist)}")
        except Exception:
            print(f"{dist}: NOT INSTALLED")

    try:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR

        print(f"QT_VERSION_STR: {QT_VERSION_STR}")
        print(f"PYQT_VERSION_STR: {PYQT_VERSION_STR}")
        from PyQt6.QtWidgets import QApplication

        print("QApplication: OK")
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        print("QWebEngineView: OK")
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        print("\nsys.path:")
        for p in sys.path[:12]:
            print(f"  {p}")
        print("\nInstalled PyQt6 packages:")
        for name in _pip_list_qt():
            print(f"  {name}")
        try:
            import PyQt6

            base = os.path.dirname(PyQt6.__file__)
            print(f"\nPyQt6 package dir: {base}")
            for pat in ("**/QtWebEngineProcess.exe", "**/Qt6WebEngineCore.dll"):
                hits = glob.glob(os.path.join(base, pat), recursive=True)
                print(f"  {pat}: {hits[0] if hits else 'NOT FOUND'}")
        except Exception as inner:
            print(f"DLL search failed: {inner}")
        return EXIT_WEBENGINE

    try:
        import PyQt6

        base = os.path.dirname(PyQt6.__file__)
        proc = glob.glob(os.path.join(base, "**", "QtWebEngineProcess.exe"), recursive=True)
        print(f"QtWebEngineProcess: {proc[0] if proc else 'NOT FOUND'}")
    except Exception as exc:
        print(f"QtWebEngineProcess lookup: {exc}")
        return EXIT_WEBENGINE

    print("\n[PASS] WebEngine import")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
