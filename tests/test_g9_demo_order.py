import os
import pytest


def test_g9_refuses_without_demo_mode(monkeypatch):
    monkeypatch.setenv("G9_DEMO_CONFIRM", "true")
    from config.settings import config
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    from scripts.g9_demo_order import main
    with pytest.raises(RuntimeError, match="IS_DEMO"):
        import asyncio
        asyncio.run(main())


def test_g9_refuses_without_explicit_confirmation(monkeypatch):
    monkeypatch.delenv("G9_DEMO_CONFIRM", raising=False)
    from config.settings import config
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    from scripts.g9_demo_order import main
    with pytest.raises(RuntimeError, match="G9_DEMO_CONFIRM"):
        import asyncio
        asyncio.run(main())
