"""Start the loopback-only OKX paper-trading dashboard."""

from __future__ import annotations

import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from paper_trading import PaperTradingError, PaperTradingManager
from demo_trading import DemoTradingError, DemoTradingManager

logger = logging.getLogger("PaperDashboard")
APP_DIRECTORY = Path(__file__).resolve().parent


def create_server(
    port: int = 8000,
    manager: PaperTradingManager | None = None,
    demo_manager: DemoTradingManager | None = None,
) -> ThreadingHTTPServer:
    paper = manager or PaperTradingManager()
    demo = demo_manager or DemoTradingManager()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/state":
                self._send_json(200, paper.get_state())
            elif path == "/api/demo/state":
                self._send_json(200, demo.get_state())
            elif path == "/":
                try:
                    html = (APP_DIRECTORY / "dashboard" / "index.html").read_bytes()
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
            else:
                self._send_json(404, {"error": "Kaynak bulunamadı."})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            try:
                origin = self.headers.get("Origin")
                expected_origin = f"http://127.0.0.1:{self.server.server_port}"
                if origin and origin != expected_origin:
                    self._send_json(403, {"error": "İstek yalnızca bu yerel panelden yapılabilir."})
                    return
                if self.headers.get_content_type() != "application/json":
                    self._send_json(415, {"error": "application/json içerik türü gerekli."})
                    return
                payload = self._read_json()
                parts = path.strip("/").split("/")
                if path == "/api/agents":
                    agent = paper.create_agent(
                        payload.get("name", ""),
                        payload.get("contracts", 1),
                        payload.get("leverage", 2),
                    )
                    self._send_json(201, {"agent": agent})
                elif len(parts) == 4 and parts[:2] == ["api", "agents"]:
                    agent_id, action = parts[2:]
                    if action in ("start", "stop"):
                        agent = paper.set_agent_active(agent_id, action == "start")
                        self._send_json(200, {"agent": agent})
                    elif action == "close":
                        fill = paper.close_position(agent_id)
                        self._send_json(200, {"fill": fill})
                    elif action == "update":
                        agent = paper.update_agent(
                            agent_id,
                            name=payload.get("name"),
                            contracts=payload.get("contracts"),
                            leverage=payload.get("leverage"),
                        )
                        self._send_json(200, {"agent": agent})
                    elif action == "delete":
                        if payload.get("confirm") is not True:
                            self._send_json(400, {"error": "Silme işlemi onay gerektirir."})
                            return
                        agent = paper.delete_agent(agent_id)
                        self._send_json(200, {"agent": agent})
                    else:
                        self._send_json(404, {"error": "İşlem bulunamadı."})
                elif path == "/api/orders":
                    fill = paper.place_order(
                        payload.get("agent_id", ""),
                        payload.get("side", ""),
                        payload.get("contracts"),
                    )
                    self._send_json(201, {"fill": fill})
                elif path == "/api/demo/orders":
                    order = demo.place_order(
                        side=payload.get("side", ""),
                        order_type=payload.get("type", ""),
                        contracts=payload.get("contracts"),
                        price=payload.get("price"),
                        confirm=payload.get("confirm") is True,
                    )
                    self._send_json(201, {"order": order})
                else:
                    self._send_json(404, {"error": "Kaynak bulunamadı."})
            except PaperTradingError as exc:
                self._send_json(400, {"error": str(exc)})
            except DemoTradingError as exc:
                self._send_json(400, {"error": str(exc)})
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                self._send_json(400, {"error": f"Geçersiz istek: {exc}"})
            except (OSError, RuntimeError):
                logger.exception("Paper dashboard request failed")
                self._send_json(500, {"error": "Yerel işlem kaydedilemedi."})

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "")
            if not raw_length.isdigit() or int(raw_length) > 8192:
                raise ValueError("İstek boyutu geçersiz.")
            content_length = int(raw_length)
            if content_length == 0:
                raise ValueError("İstek gövdesi boş olamaz.")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON nesnesi bekleniyor.")
            return payload

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

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local OKX swap paper-trading dashboard")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    manager = PaperTradingManager()
    demo_manager = DemoTradingManager()
    server = create_server(args.port, manager, demo_manager)
    manager.start_market_feed()
    logger.info("Paper dashboard ready at http://127.0.0.1:%d", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping paper dashboard")
    finally:
        server.server_close()
        manager.stop_market_feed()
        demo_manager.close()


if __name__ == "__main__":
    main()
