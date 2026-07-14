"""python -m iris 진입점."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def _run_knowledge_cli(argv: list[str]) -> int:
    from iris.application.knowledge_service import build_knowledge_service, resolve_iris_repo_root
    from iris.config.settings import load_settings
    from iris.infrastructure.knowledge.vault_repository import default_vault_path
    from iris.storage.database import Database

    parser = argparse.ArgumentParser(prog="python -m iris knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-vault", help="Obsidian Vault 폴더 생성")
    add_src = sub.add_parser("add-source", help="인덱싱 소스 등록")
    add_src.add_argument("path")
    sub.add_parser("sync", help="등록 소스 동기화")
    search = sub.add_parser("search", help="FTS 검색")
    search.add_argument("query")
    sub.add_parser("status", help="인덱스 상태")
    bootstrap = sub.add_parser("bootstrap-iris", help="Iris 저장소 자동 등록·동기화")
    args = parser.parse_args(argv)

    settings = load_settings()
    vault = Path(settings.wiki_vault_path) if settings.wiki_vault_path else default_vault_path()
    svc = build_knowledge_service(Database(), vault, settings=settings)

    if args.cmd == "init-vault":
        path = svc.init_vault()
        print(path)
        return 0
    if args.cmd == "add-source":
        svc.init_vault()
        svc.register_source(Path(args.path))
        report = svc.sync()
        print(f"indexed={report.indexed} unchanged={report.unchanged}")
        return 0
    if args.cmd == "sync":
        report = svc.sync()
        print(
            f"indexed={report.indexed} unchanged={report.unchanged} "
            f"skipped={report.skipped} missing={report.missing}"
        )
        return 0
    if args.cmd == "search":
        hits = svc.search(args.query)
        for h in hits:
            print(f"[{h.score:.2f}] {h.title} — {h.path}")
            if h.snippet:
                print(f"  {h.snippet[:160]}")
        return 0
    if args.cmd == "status":
        st = svc.status()
        print(st)
        return 0
    if args.cmd == "bootstrap-iris":
        root = resolve_iris_repo_root()
        report = svc.ensure_iris_bootstrap(root)
        print(f"repo={root} indexed={report.indexed} unchanged={report.unchanged}")
        return 0
    return 1


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "knowledge":
        raise SystemExit(_run_knowledge_cli(sys.argv[2:]))

    from iris.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Iris")
    app.setFont(QFont("Noto Sans KR", 10))
    win = MainWindow()
    win.show()
    app.processEvents()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
