import asyncio

import pytest

from demo_exec.executor import DemoExecutor
from demo_exec.intent import Intent
from demo_exec.lifecycle import Lifecycle, LifecycleState
from demo_exec.journal import Journal
from demo_exec.transport import NullTransport
from scripts.record_phase_a_evidence import (
    acceptance_passes,
    phase_a_agent_id,
    phase_a_evidence_filename,
    validate_evidence_consistency,
)


def intent(seq=1, agent_id="agent1"):
    return Intent.create(agent_id, "ETH/USDT:USDT", "buy", "test", seq)


def test_phase_a_daily_gate_accepts_zero_safety_counters():
    assert acceptance_passes({
        "daily_shadow_run": True,
        "null_transport_only": True,
        "unexpected_exchange_order_calls": 0,
        "unresolved_incidents": 0,
    })


@pytest.mark.parametrize(
    "override",
    [
        {"daily_shadow_run": False},
        {"null_transport_only": False},
        {"unexpected_exchange_order_calls": 1},
        {"unresolved_incidents": 1},
    ],
)
def test_phase_a_daily_gate_rejects_failed_conditions(override):
    acceptance = {
        "daily_shadow_run": True,
        "null_transport_only": True,
        "unexpected_exchange_order_calls": 0,
        "unresolved_incidents": 0,
    }
    acceptance.update(override)
    assert acceptance_passes(acceptance) is False


def test_phase_a_requires_null_transport():
    with pytest.raises(ValueError, match="NullTransport"):
        DemoExecutor(object())


def test_phase_a_rejects_non_a_phase():
    with pytest.raises(ValueError, match="Phase A"):
        DemoExecutor(NullTransport(), demo_phase="B")


@pytest.mark.asyncio
async def test_shadow_submit_never_reaches_exchange():
    transport = NullTransport()
    result = await DemoExecutor(transport).submit(intent())
    assert result.accepted is True
    assert result.code == "SHADOW"
    assert result.state == "SUBMITTED"
    assert transport.place_calls == 1


@pytest.mark.asyncio
async def test_duplicate_agent_seq_is_rejected():
    executor = DemoExecutor(NullTransport())
    assert (await executor.submit(intent(1))).accepted
    second = await executor.submit(intent(1))
    assert second.code == "E_JOURNAL"


@pytest.mark.asyncio
async def test_disabled_shadow_does_not_submit():
    transport = NullTransport()
    result = await DemoExecutor(transport, enabled=False).submit(intent())
    assert result.code == "E_DISABLED"
    assert transport.place_calls == 0


def test_lifecycle_unknown_is_terminal_until_external_resolution():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.UNKNOWN)
    with pytest.raises(ValueError):
        lifecycle.transition(LifecycleState.FILLED)


def test_lifecycle_reject_is_not_unknown():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.REJECTED)
    assert lifecycle.state is LifecycleState.REJECTED


def test_write_ahead_journal(tmp_path):
    journal = Journal(tmp_path / "events.jsonl")
    journal.append({"event": "INTENT", "seq": 1})
    journal.append({"event": "SHADOW_SUBMITTED", "seq": 1})
    assert journal.read() == [
        {"event": "INTENT", "seq": 1},
        {"event": "SHADOW_SUBMITTED", "seq": 1},
    ]


def test_clordid_is_bounded_and_alphanumeric():
    result = asyncio.run(DemoExecutor(NullTransport()).submit(intent(12)))
    assert result.client_order_id == "gagent112"
    assert result.client_order_id.isascii()
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32


def test_clordid_normalizes_agent_ids_with_punctuation():
    result = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(3, agent_id="phase-a-agent"))
    )
    assert result.client_order_id.isascii()
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32


def test_clordid_normalization_is_deterministic_across_executors():
    first = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(7, agent_id="phase-a-agent"))
    )
    second = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(7, agent_id="phase-a-agent"))
    )
    assert first.client_order_id == second.client_order_id


def test_clordid_normalizes_long_agent_ids():
    result = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(8, agent_id="a" * 80))
    )
    assert result.client_order_id.isascii()
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32


def valid_evidence():
    day = "2026-10-14"
    run_id = "38528140194"
    attempt = "1"
    return {
        "schema": "phase-a-evidence.v3",
        "evidence_id": phase_a_evidence_filename(day, run_id, attempt),
        "date_utc": day,
        "git_sha": "c2b5423908ec96d72c0682cd88b1fc0949748daf",
        "workflow_run_id": run_id,
        "workflow_run_attempt": attempt,
        "workflow_event": "workflow_dispatch",
        "transport": "NullTransport",
        "exchange_touched": False,
        "exchange_mutation_calls": 0,
        "exchange_order_call_observation": {"value": 0},
        "intent_count": 3,
        "null_transport_place_calls": 3,
        "journal_event_count": 3,
        "incidents": [],
        "sequence_scope": "daily_synthetic_validation",
        "sequence_continuity_proven": False,
        "acceptance": {
            "daily_shadow_run": True,
            "null_transport_only": True,
            "unexpected_exchange_order_calls": 0,
            "unresolved_incidents": 0,
        },
    }


def test_phase_a_evidence_consistency_accepts_valid_record():
    assert validate_evidence_consistency(valid_evidence()) is True


@pytest.mark.parametrize(
    "field,wrong_value",
    [
        ("git_sha", "4fc3bb20d84759787bbf357e0e19ed1114cb879d"),
        ("workflow_run_id", "38513143918"),
        ("workflow_run_attempt", "2"),
        ("workflow_event", "schedule"),
    ],
)
def test_phase_a_provenance_must_match_actual_workflow(field, wrong_value):
    evidence = valid_evidence()
    expected = {
        "git_sha": "c2b5423908ec96d72c0682cd88b1fc0949748daf",
        "workflow_run_id": "38528140194",
        "workflow_run_attempt": "1",
        "workflow_event": "workflow_dispatch",
    }
    evidence[field] = wrong_value
    assert validate_evidence_consistency(evidence, expected) is False


def test_phase_a_provenance_accepts_exact_runtime_identity():
    evidence = valid_evidence()
    expected = {
        "git_sha": "c2b5423908ec96d72c0682cd88b1fc0949748daf",
        "workflow_run_id": "38528140194",
        "workflow_run_attempt": "1",
        "workflow_event": "workflow_dispatch",
    }
    assert validate_evidence_consistency(evidence, expected) is True


@pytest.mark.parametrize(
    "override",
    [
        {"null_transport_place_calls": 2},
        {"journal_event_count": 2},
        {"workflow_run_id": "local"},
        {"workflow_event": "local"},
        {"workflow_run_attempt": "2"},
        {"evidence_id": "2026-10-14.json"},
        {"sequence_scope": "persistent"},
        {"sequence_continuity_proven": True},
        {"transport": "OkxDemoTransport"},
        {"exchange_mutation_calls": 1},
        {"exchange_order_call_observation": {"value": 1}},
        {"incidents": [{"code": "unexpected"}]},
        {"schema": "phase-a-evidence.v2"},
    ],
)
def test_phase_a_evidence_consistency_rejects_mismatch_or_weak_provenance(override):
    evidence = valid_evidence()
    evidence.update(override)
    assert validate_evidence_consistency(evidence) is False


def test_phase_a_evidence_consistency_accepts_coherent_local_record():
    evidence = valid_evidence()
    evidence.update({
        "evidence_id": phase_a_evidence_filename("2026-10-14", "local", "local"),
        "workflow_run_id": "local",
        "workflow_run_attempt": "local",
        "workflow_event": "local",
        "git_sha": "local",
    })
    assert validate_evidence_consistency(evidence) is True


def test_phase_a_evidence_filename_is_unique_per_run_and_attempt():
    first = phase_a_evidence_filename("2026-10-14", "12345", "1")
    second_run = phase_a_evidence_filename("2026-10-14", "12346", "1")
    retry = phase_a_evidence_filename("2026-10-14", "12345", "2")
    assert first == "2026-10-14-run-12345-attempt-1.json"
    assert len({first, second_run, retry}) == 3


def test_phase_a_agent_ids_are_run_scoped_and_synthetic():
    first = phase_a_agent_id("2026-10-14", "12345")
    retry = phase_a_agent_id("2026-10-14", "12346")
    assert first == "phasea2026101412345"
    assert first.isalnum()
    assert first != retry
    first_result = asyncio.run(DemoExecutor(NullTransport()).submit(intent(1, first)))
    next_result = asyncio.run(DemoExecutor(NullTransport()).submit(intent(1, retry)))
    assert first_result.client_order_id != next_result.client_order_id
