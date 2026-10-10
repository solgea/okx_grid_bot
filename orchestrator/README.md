# Agent Orchestration — Deferred

**Status: DISABLED / DEFERRED.**

The agent orchestration system is not part of the core-first stabilization phase. Do not launch `orchestrator.cli`, `MasterOrchestrator`, or agent lifecycle tasks while the core is being made buildable and test-stable. The engineering-agent GitHub Actions workflow has been removed from this branch so CI failures no longer trigger agent automation.

## Re-enable criteria

Reintroduce the agent system only in a separate, reviewed phase after all of the following are evidenced on the core branch:

1. Python compile/import checks pass.
2. Core unit and integration tests pass consistently.
3. Docker image builds and the local runtime smoke test passes.
4. OKX read-only bootstrap is verified without invoking exchange mutation methods.
5. CI is green on the exact commit proposed for merge.

Re-enabling agents must not change risk gates or grant order, merge, deployment, or live-trading authority. Phase B remains locked; live trading and Emergency Flatten remain disabled.

The existing orchestration source and tests are retained temporarily to avoid deleting code before dependency/import boundaries are mapped. They are deferred, not considered part of the runnable core, and must be removed or reintroduced deliberately in the next refactor step.
