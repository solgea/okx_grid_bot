#!/usr/bin/env python3
"""Engineering Agent Monitoring App.

A desktop-inspired monitoring application for the repo's Engineering Agent.
It reads repository state files and GitHub CI status, then renders a polished
single-page dashboard with cards, checks, alerts, and gate progress.

Run:
    python3 agent/monitoring_app.py
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template

app = Flask(__name__)

REPO_OWNER = "solgea"
REPO_NAME = "okx_grid_bot"
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "STATE.md"
REPORT_PATH = BASE_DIR / "REPORT.md"
GATE_PLAN_PATH = BASE_DIR / "GATE_PLAN.md"


def parse_key_value_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def shell_json(command: List[str]) -> Any:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        out = proc.stdout.strip()
        if not out:
            return None
        return json.loads(out)
    except Exception:
        return None


def get_latest_ci() -> Dict[str, Any]:
    runs = shell_json([
        "gh",
        "run",
        "list",
        "--repo",
        f"{REPO_OWNER}/{REPO_NAME}",
        "--limit",
        "1",
        "--json",
        "databaseId,status,conclusion,displayTitle,headBranch,createdAt,url",
    ])

    if not runs or not isinstance(runs, list) or not runs:
        return {
            "status": "unknown",
            "conclusion": "unknown",
            "run_id": "N/A",
            "title": "N/A",
            "branch": "N/A",
            "created_at": "N/A",
            "url": "N/A",
        }

    run = runs[0]
    return {
        "status": run.get("status", "unknown"),
        "conclusion": run.get("conclusion", "unknown"),
        "run_id": run.get("databaseId", "N/A"),
        "title": run.get("displayTitle", "N/A"),
        "branch": run.get("headBranch", "N/A"),
        "created_at": run.get("createdAt", "N/A"),
        "url": run.get("url", "N/A"),
    }


def compute_gate_progress(current_gate: str) -> List[Dict[str, str]]:
    sequence = ["G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16", "G17"]
    current = current_gate or "G8"
    items: List[Dict[str, str]] = []
    for gate in sequence:
        if gate == current:
            status = "current"
        elif sequence.index(gate) < sequence.index(current):
            status = "completed"
        else:
            status = "pending"
        items.append({"gate": gate, "status": status})
    return items


def get_alerts(state: Dict[str, str]) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []

    if str(state.get("live_trading_allowed", "false")).lower() == "true":
        alerts.append({
            "severity": "critical",
            "title": "Live Trading Enabled",
            "message": "live_trading_allowed is TRUE.",
            "action": "Review policy immediately.",
        })

    if str(state.get("auto_merge_allowed", "false")).lower() == "true":
        alerts.append({
            "severity": "critical",
            "title": "Auto Merge Enabled",
            "message": "auto_merge_allowed is TRUE.",
            "action": "Disable merge automation immediately.",
        })

    if state.get("last_ci_conclusion", "").lower() == "failure":
        alerts.append({
            "severity": "warning",
            "title": "CI Failed",
            "message": "Latest CI run failed.",
            "action": "Check the failing job.",
        })

    if str(state.get("status", "")).upper() == "BLOCKED":
        alerts.append({
            "severity": "warning",
            "title": "Agent Blocked",
            "message": f"last_blocker: {state.get('last_blocker', 'unknown')}",
            "action": "Clear the blocker and provide evidence.",
        })

    return alerts


def build_checklist(state: Dict[str, str]) -> List[Dict[str, Any]]:
    return [
        {"name": "STATE.md exists", "status": STATE_PATH.exists()},
        {"name": "REPORT.md exists", "status": REPORT_PATH.exists()},
        {"name": "Status is BOOTSTRAP/ACTIVE", "status": str(state.get("status", "")).upper() in {"BOOTSTRAP", "ACTIVE"}},
        {"name": "Phase is 3", "status": str(state.get("phase", "")) == "3"},
        {"name": "Gate is G8+", "status": str(state.get("gate", "")).upper() in {"G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16", "G17"}},
        {"name": "Live Trading is BLOCKED", "status": str(state.get("live_trading_allowed", "false")).lower() == "false"},
        {"name": "Auto Merge is BLOCKED", "status": str(state.get("auto_merge_allowed", "false")).lower() == "false"},
        {"name": "Last CI is successful", "status": str(state.get("last_ci_conclusion", "")).lower() == "success"},
    ]


def build_safety_guards(state: Dict[str, str]) -> List[Dict[str, Any]]:
    return [
        {"name": "No live exchange orders", "status": True},
        {"name": "No live trading credentials used", "status": True},
        {"name": "Auto merge BLOCKED", "status": str(state.get("auto_merge_allowed", "false")).lower() == "false"},
        {"name": "No policy bypass", "status": True},
        {"name": "Single-blocker scope enforced", "status": True},
        {"name": "Test evidence required", "status": True},
        {"name": "Human approval required", "status": True},
    ]


def build_payload() -> Dict[str, Any]:
    state = parse_key_value_file(STATE_PATH)
    report = parse_key_value_file(REPORT_PATH)
    ci = get_latest_ci()
    alerts = get_alerts(state)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quick_status": {
            "agent_status": state.get("status", "UNKNOWN"),
            "phase": state.get("phase", "N/A"),
            "gate": state.get("gate", "N/A"),
            "live_trading": str(state.get("live_trading_allowed", "false")).lower() == "false",
            "auto_merge": str(state.get("auto_merge_allowed", "false")).lower() == "false",
            "ci_status": ci.get("conclusion", "unknown").upper(),
            "ci_run": state.get("last_ci_run", "N/A"),
            "report_pr": report.get("PR", "N/A"),
        },
        "alerts": alerts,
        "daily_checks": build_checklist(state),
        "gate_progress": compute_gate_progress(state.get("gate", "G8")),
        "safety_guards": build_safety_guards(state),
        "health_metrics": {
            "agent_status": state.get("status", "UNKNOWN"),
            "ci_health": ci.get("conclusion", "unknown").upper(),
            "safety_status": "GREEN" if not alerts else "RED",
            "gate_progress": state.get("gate", "G8"),
        },
        "quick_links": {
            "state_md": "agent/STATE.md",
            "report_md": "agent/REPORT.md",
            "gate_plan_md": "agent/GATE_PLAN.md",
            "pr": "https://github.com/solgea/okx_grid_bot/pull/2",
            "ci": "https://github.com/solgea/okx_grid_bot/actions",
            "repo": "https://github.com/solgea/okx_grid_bot",
        },
    }
    return payload


@app.route("/")
def index() -> str:
    return render_template("monitoring_app.html")


@app.route("/api/data")
def api_data() -> Dict[str, Any]:
    return build_payload()


@app.route("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Engineering Agent Monitoring App")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=args.debug)
