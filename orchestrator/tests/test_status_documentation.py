from pathlib import Path


def test_status_docs_contain_safety_contract():
    docs=[]
    for name in ("MASTER_ORCHESTRATOR.md","AGENT_PROTOCOL.md","ORCHESTRATOR_POLICY.md","ORCHESTRATOR_STATUS.md"):
        text=Path(name).read_text(encoding="utf-8")
        assert text.strip()
        docs.append(text)
    combined="\n".join(docs)
    assert "live_order" in combined
    assert "BLOCKED" in combined
