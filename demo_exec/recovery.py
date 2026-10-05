import json
from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryResult:
    state: str
    reason: str


class Recovery:
    def recover(self, journal_path: str, *, last_seq: int | None = None) -> RecoveryResult:
        try:
            rows = [json.loads(x) for x in open(journal_path, encoding="utf-8").read().splitlines() if x]
        except (OSError, json.JSONDecodeError):
            return RecoveryResult("BLOCKED", "E_JOURNAL_CORRUPT")
        seqs = [int(r["seq"]) for r in rows if "seq" in r]
        if any(b != a + 1 for a, b in zip(seqs, seqs[1:])):
            return RecoveryResult("BLOCKED", "E_SEQ_GAP")
        if last_seq is not None and seqs and seqs[-1] != last_seq:
            return RecoveryResult("BLOCKED", "E_SEQ_GAP")
        return RecoveryResult("RECOVERED_PAUSED", "G14")
