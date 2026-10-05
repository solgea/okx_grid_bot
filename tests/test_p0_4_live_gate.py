from unittest.mock import AsyncMock

import pytest

from config.settings import config
from engine.exchange import OKXEngine


def make_engine():
    engine = OKXEngine.__new__(OKXEngine)
    engine.exchange = None
    return engine


def test_live_mutation_requires_explicit_authorization(monkeypatch):
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    with pytest.raises(PermissionError, match="explicit live authorization"):
        make_engine()._assert_mutation_authorized()


def test_live_mutation_requires_second_explicit_authorization(monkeypatch):
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    with pytest.raises(PermissionError):
        make_engine()._assert_mutation_authorized()


def test_explicit_live_authorization_allows_gate(monkeypatch):
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", True)

    make_engine()._assert_mutation_authorized()


def test_demo_execution_is_not_blocked_by_live_gate(monkeypatch):
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    make_engine()._assert_mutation_authorized()
