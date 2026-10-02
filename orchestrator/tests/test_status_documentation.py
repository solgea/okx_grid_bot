from pathlib import Path

def test_status_docs_contain_safety_contract():
    for name in ("MASTER_ORCHESTRATOR.md","AGENT_PROTOCOL.md","ORCHESTRATOR_POLICY.md","ORCHESTRATOR_STATUS.md"):
        text=Path(name).read_text(encoding="utf-8")
        assert "live_order" in text and "BLOCKED" in text
