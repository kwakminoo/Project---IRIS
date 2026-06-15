#!/usr/bin/env python3
"""QWebEngineView 단독 스모크 — Theia 로드 전 WebEngine 검증."""

from __future__ import annotations

import argparse
import sys
import traceback

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow

from PyQt6.QtWebEngineWidgets import QWebEngineView

_HTML = """<!DOCTYPE html>
<html>
<head><title>IRIS_WEBENGINE_OK</title></head>
<body><h1>IRIS WEBENGINE OK</h1></body>
</html>
"""

_READINESS_JS = "document.title"

_EXIT_OK = 0
_EXIT_FAIL = 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Iris QWebEngine smoke test")
    parser.add_argument("--headless-ms", type=int, default=2500, help="표시 후 종료 대기(ms)")
    parser.add_argument("--no-show", action="store_true", help="창 표시 생략")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = QMainWindow()
    view = QWebEngineView()
    win.setCentralWidget(view)
    if not args.no_show:
        win.resize(640, 480)
        win.setWindowTitle("Iris WebEngine Smoke")
        win.show()

    state = {"load_ok": False, "title_ok": False, "error": ""}

    def on_load(ok: bool) -> None:
        state["load_ok"] = ok
        if not ok:
            state["error"] = "loadFinished(False)"
            app.quit()
            return
        view.page().runJavaScript(_READINESS_JS, _on_title)

    def _on_title(title: object) -> None:
        state["title_ok"] = str(title) == "IRIS_WEBENGINE_OK"
        if not state["title_ok"]:
            state["error"] = f"title={title!r}"
        app.quit()

    view.loadFinished.connect(on_load)
    view.setHtml(_HTML, QUrl("about:blank"))
    QTimer.singleShot(max(args.headless_ms, 5000), lambda: (state.setdefault("error", "timeout"), app.quit()))
    app.exec()

    if state["load_ok"] and state["title_ok"]:
        print("[PASS] QWebEngine local HTML + JS title probe")
        return _EXIT_OK

    print(f"[FAIL] {state.get('error') or 'unknown'}")
    if state.get("error") == "loadFinished(False)":
        try:
            import glob
            import os

            import PyQt6

            base = os.path.dirname(PyQt6.__file__)
            proc = glob.glob(os.path.join(base, "**", "QtWebEngineProcess.exe"), recursive=True)
            print(f"QtWebEngineProcess: {proc[0] if proc else 'NOT FOUND'}")
        except Exception:
            traceback.print_exc()
    return _EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
