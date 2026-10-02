from pathlib import Path

WORKFLOW = Path(".github/workflows/master-orchestrator.yml")


def test_master_orchestrator_workflow_is_manual_and_fail_closed():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert 'contents: read' in text
    assert "python -m orchestrator.cli --root \"$ORCHESTRATOR_ROOT\" submit task.json" in text
    assert "python -m orchestrator.cli --root \"$ORCHESTRATOR_ROOT\" run \"$TASK_ID\"" in text
    assert "actions/upload-artifact@v4" in text

    forbidden = ("LIVE_ORDER", "LIVE_WITHDRAWAL", "PRODUCTION_DEPLOY")
    assert not any(item in text for item in forbidden)
