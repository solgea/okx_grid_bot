"""The dashboard HTTP handler.

The handler is a module-level class rather than a closure so it can be
tested directly and so the routing table is not rebuilt per request.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from demo_trading import DemoTradingError
from paper_trading import PaperTradingError
from web.routes import dispatch_agent_action, is_agent_collection, parse_agent_action

logger = logging.getLogger("PaperDashboard")

APP_DIRECTORY = Path(__file__).resolve().parents[1]
DASHBOARD_DOCUMENT = APP_DIRECTORY / "dashboard" / "index.html"

MAX_REQUEST_BYTES = 8192
JSON_CONTENT_TYPE = "application/json"


class DashboardHandler(BaseHTTPRequestHandler):
    """Serves the dashboard document and the local JSON API."""

    paper: Any = None
    demo: Any = None

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/state":
            self._send_json(200, self.paper.get_state())
        elif path == "/api/demo/state":
            self._send_json(200, self.demo.get_state())
        elif path == "/":
            self._send_dashboard()
        else:
            self._send_json(404, {"error": "Kaynak bulunamadı."})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            self._assert_same_origin()
            self._assert_json_content_type()
            payload = self._read_json()

            if is_agent_collection(path):
                agent = self.paper.create_agent(
                    payload.get("name", ""),
                    payload.get("contracts", 1),
                    payload.get("leverage", 2),
                )
                self._send_json(201, {"agent": agent})
                return

            agent_action = parse_agent_action(path)
            if agent_action is not None:
                agent_id, action = agent_action
                status, body = dispatch_agent_action(
                    self.paper, agent_id, action, payload
                )
                self._send_json(status, body)
                return

            if path == "/api/orders":
                fill = self.paper.place_order(
                    payload.get("agent_id", ""),
                    payload.get("side", ""),
                    payload.get("contracts"),
                )
                self._send_json(201, {"fill": fill})
                return

            if path == "/api/demo/orders":
                order = self.demo.place_order(
                    side=payload.get("side", ""),
                    order_type=payload.get("type", ""),
                    contracts=payload.get("contracts"),
                    price=payload.get("price"),
                    confirm=payload.get("confirm") is True,
                )
                self._send_json(201, {"order": order})
                return

            self._send_json(404, {"error": "Kaynak bulunamadı."})
        except _HttpError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except (PaperTradingError, DemoTradingError) as exc:
            self._send_json(400, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(400, {"error": f"Geçersiz istek: {exc}"})
        except (OSError, RuntimeError):
            logger.exception("Paper dashboard request failed")
            self._send_json(500, {"error": "Yerel işlem kaydedilemedi."})

    def _assert_same_origin(self) -> None:
        """Reject cross-origin requests from a browser."""
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if origin and origin != expected_origin:
            raise _HttpError(403, "İstek yalnızca bu yerel panelden yapılabilir.")

    def _assert_json_content_type(self) -> None:
        """Reject requests that are not JSON."""
        if self.headers.get_content_type() != JSON_CONTENT_TYPE:
            raise _HttpError(415, "application/json içerik türü gerekli.")

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdigit() or int(raw_length) > MAX_REQUEST_BYTES:
            raise ValueError("İstek boyutu geçersiz.")
        content_length = int(raw_length)
        if content_length == 0:
            raise ValueError("İstek gövdesi boş olamaz.")
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON nesnesi bekleniyor.")
        return payload

    def _send_dashboard(self) -> None:
        try:
            html = DASHBOARD_DOCUMENT.read_bytes()
        except OSError:
            logger.exception("Dashboard document could not be read")
            self._send_json(500, {"error": "Dashboard dosyası okunamadı."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format_string % args)


class _HttpError(Exception):
    """An HTTP-level rejection with an explicit status code."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def build_handler(paper: Any, demo: Any) -> type[DashboardHandler]:
    """Return a handler class bound to the given managers."""
    return type(
        "BoundDashboardHandler",
        (DashboardHandler,),
        {"paper": paper, "demo": demo},
    )


__all__ = ["DashboardHandler", "build_handler"]
