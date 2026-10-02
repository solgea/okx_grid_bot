from pathlib import Path

def test_runtime_readme_documents_commands_and_safety():
    text=Path("orchestrator/README.md").read_text(encoding="utf-8")
    for command in ("submit", "run", "status", "report"):
        assert "orchestrator.cli" in text and command in text
    assert "PreFlight != AUTHORIZED" in text
    assert "does not authorize merge" in text
