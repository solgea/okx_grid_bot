"""Request routing for the dashboard.

Routes are declared as data so the handler stays a thin transport layer and
the URL contract is visible in one place.
"""

from __future__ import annotations

from typing import Any, Callable

# Each agent action maps to the manager call that performs it.
AGENT_ACTIONS: dict[str, str] = {
    "start": "start",
    "stop": "stop",
    "close": "close",
    "update": "update",
    "delete": "delete",
}

# Agent paths are /api/agents/<id>/<action>.
AGENT_PATH_PREFIX = "api/agents"


def parse_agent_action(path: str) -> tuple[str, str] | None:
    """Return (agent_id, action) for an agent path, or None if it is not one."""
    parts = path.strip("/").split("/")
    if len(parts) != 4 or "/".join(parts[:2]) != AGENT_PATH_PREFIX:
        return None
    agent_id, action = parts[2], parts[3]
    if action not in AGENT_ACTIONS:
        return None
    return agent_id, action


def is_agent_collection(path: str) -> bool:
    """Return True for the agent collection endpoint."""
    return path.strip("/") == AGENT_PATH_PREFIX


def dispatch_agent_action(
    paper: Any,
    agent_id: str,
    action: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Perform an agent action and return the HTTP status and body."""
    if action == "start":
        agent = paper.set_agent_active(agent_id, True)
        return 200, {"agent": agent}
    if action == "stop":
        agent = paper.set_agent_active(agent_id, False)
        return 200, {"agent": agent}
    if action == "close":
        fill = paper.close_position(agent_id)
        return 200, {"fill": fill}
    if action == "update":
        agent = paper.update_agent(
            agent_id,
            name=payload.get("name"),
            contracts=payload.get("contracts"),
            leverage=payload.get("leverage"),
        )
        return 200, {"agent": agent}
    if action == "delete":
        if payload.get("confirm") is not True:
            return 400, {"error": "Silme işlemi onay gerektirir."}
        agent = paper.delete_agent(agent_id)
        return 200, {"agent": agent}
    return 404, {"error": "İşlem bulunamadı."}


__all__ = [
    "AGENT_ACTIONS",
    "dispatch_agent_action",
    "is_agent_collection",
    "parse_agent_action",
]
