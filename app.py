"""Start the loopback-only OKX paper-trading dashboard.

The HTTP layer lives in the ``web`` package; this module only wires the
managers to the server and runs it.
"""

from __future__ import annotations

import argparse
import logging

from demo_trading import DemoTradingManager
from paper_trading import PaperTradingManager
from web.server import create_server

logger = logging.getLogger("PaperDashboard")

# Re-exported so callers can keep importing create_server from the entry point.
__all__ = ["create_server", "main"]


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
