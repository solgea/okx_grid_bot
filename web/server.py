"""The loopback-only dashboard server."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from typing import Any

from web.handler import build_handler


def create_server(
    port: int = 8000,
    manager: Any | None = None,
    demo_manager: Any | None = None,
) -> ThreadingHTTPServer:
    """Create the dashboard server bound to the loopback interface."""
    from demo_trading import DemoTradingManager
    from paper_trading import PaperTradingManager

    paper = manager or PaperTradingManager()
    demo = demo_manager or DemoTradingManager()
    handler = build_handler(paper, demo)
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


__all__ = ["create_server"]
