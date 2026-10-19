"""HTTP layer for the local paper/demo dashboard.

The dashboard is loopback-only. It never exposes API credentials and it
never places an order without an explicit confirmation.
"""

from web.handler import DashboardHandler, build_handler
from web.server import create_server

__all__ = ["DashboardHandler", "build_handler", "create_server"]
