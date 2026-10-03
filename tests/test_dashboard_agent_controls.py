"""Static guard: the dashboard keeps its agent management controls wired to the API."""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(encoding="utf-8")


def test_agent_management_controls_are_present():
    for marker in ('data-action="${agent.active ? "stop" : "start"}"',  # enable / disable
                   "data-edit=", "data-delete=",                          # update / delete buttons
                   'id="edit-dialog"', 'id="agent-form"'):                # edit dialog / create form
        assert marker in HTML, marker


def test_dashboard_calls_the_agent_endpoints():
    assert '"/api/agents", {name' in HTML                                    # create
    assert "/api/agents/${editingAgentId}/update" in HTML                    # update
    assert "/api/agents/${agentId}/delete" in HTML                           # delete
    assert "{confirm:true}" in HTML                                          # delete must be explicit
    assert "window.confirm(" in HTML                                         # and confirmed by the user
