"""Phase 4 packaging regressions.

Covers:
1. The trade journal is read once, with and without a header row.
2. The portfolio analyzer runs on a console that defaults to a legacy
   code page without raising.
3. The recovery journal is read without leaking a file handle.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from analyzer.portfolio_analyzer import analyze_portfolio, load_trade_log
from demo_exec.recovery import Recovery

REPO_ROOT = Path(__file__).resolve().parents[1]

HEADER_CSV = (
    "Timestamp,Symbol,Action,Position_Size,Entry_Price,Realized_PnL,"
    "Unrealized_PnL,Net_Total_PnL,Wallet_Balance\n"
    "2026-10-20 10:00:00,ETH/USDT:USDT,ENTRY / ADD,0.01,2500.0,0.0,0.0,0.0,10000.0\n"
    "2026-10-20 10:05:00,ETH/USDT:USDT,TAKE PROFIT / REDUCE,0.0,2500.0,5.0,0.0,5.0,10005.0\n"
)

HEADERLESS_CSV = (
    "2026-10-20 10:00:00,ETH/USDT:USDT,ENTRY / ADD,0.01,2500.0,0.0,0.0,0.0,10000.0\n"
)


def test_trade_log_with_a_header_row(tmp_path):
    path = tmp_path / "trade.csv"
    path.write_text(HEADER_CSV, encoding="utf-8")

    frame = load_trade_log(str(path))

    assert frame is not None
    assert len(frame) == 2
    assert list(frame.columns)[:3] == ["Timestamp", "Symbol", "Action"]


def test_trade_log_without_a_header_row_uses_the_documented_columns(tmp_path):
    path = tmp_path / "trade.csv"
    path.write_text(HEADERLESS_CSV, encoding="utf-8")

    frame = load_trade_log(str(path))

    assert frame is not None
    assert len(frame) == 1
    assert list(frame.columns)[:3] == ["Timestamp", "Symbol", "Action"]


def test_trade_log_with_a_wrong_column_count_is_rejected(tmp_path):
    path = tmp_path / "trade.csv"
    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    assert load_trade_log(str(path)) is None


def test_analyze_portfolio_runs_on_a_legacy_console(tmp_path, capsys):
    """A cp1254 console must not crash the analyzer on emoji output."""
    path = tmp_path / "trade.csv"
    path.write_text(HEADER_CSV, encoding="utf-8")

    analyze_portfolio(str(path))

    captured = capsys.readouterr()
    assert "ROI" in captured.out


def test_analyzer_entry_point_accepts_a_path_argument(tmp_path):
    path = tmp_path / "trade.csv"
    path.write_text(HEADER_CSV, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "analyzer/portfolio_analyzer.py", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert "ROI" in result.stdout


def test_recovery_reads_the_journal_without_leaking_a_handle(tmp_path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        '{"seq": 1}\n{"seq": 2}\n', encoding="utf-8"
    )

    result = Recovery().recover(str(journal))

    assert result.state == "RECOVERED_PAUSED"
    assert result.reason == "G14"


def test_recovery_blocks_a_corrupt_journal(tmp_path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text("not json\n", encoding="utf-8")

    result = Recovery().recover(str(journal))

    assert result.state == "BLOCKED"
    assert result.reason == "E_JOURNAL_CORRUPT"
