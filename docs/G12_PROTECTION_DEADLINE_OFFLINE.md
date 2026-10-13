# G12 protection deadline — offline contract

The execution contract sets PROTECT_DEADLINE_SEC = 5. The clock starts at the
first POSITION_DETECTED observation, not at order submission. This Phase-A
helper validates timing deterministically with caller-supplied monotonic
timestamps.

- The first position detection starts the clock; duplicate detections cannot
  reset it.
- Protection confirmed at exactly five seconds is accepted; confirmation after
  the deadline is rejected.
- Missing detection, a backwards monotonic timestamp, or an expired deadline
  fails closed.
- Once expired, late protection confirmation cannot clear the expired state.
- emergency_action_required is only a signal for the higher-level safety
  controller. This helper does not place a reduce-only order, mutate a
  position, call OKX, or claim an emergency close was completed.

## Validation

tests/test_g12_protection_deadline.py covers the exact boundary, late
confirmation, non-resettable start time, missing detection, invalid timestamps,
and invalid deadline configuration. These are offline contract tests only;
they do not prove real exchange protection/SL behavior. Phase B remains LOCKED.
