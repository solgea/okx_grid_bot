# Review Template

## Change summary

- Area:
- Risk level: Low / Medium / High
- Related files:
- Validation command(s):

## Safety review

- [ ] Preflight or authorization is explicit before any live action.
- [ ] Paper/demo paths remain the safe default for development.
- [ ] No live execution path is reachable by default or fallback logic.
- [ ] Symbol, leverage, and order arguments match the expected validation contract.
- [ ] Exposure, drawdown, and risk limits are enforced before action.
- [ ] Market data freshness and state validity are checked.
- [ ] Secrets, keys, and sensitive state are not exposed in logs or output.
- [ ] Regression test has been added or updated for the changed guardrail.
- [ ] Remaining risk or follow-up action is documented.

## Reviewer decision

- [ ] Approve
- [ ] Needs changes
- [ ] Blocked

Reason:

## Final note

This change preserves the repository’s fail-closed trading model and keeps demo/paper flows safer than live execution.
