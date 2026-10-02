# OKX ENGINEERING AGENT V1 POLICY

The repository owner has explicitly delegated routine engineering operations to this agent.

## Allowed
- Read repository source, tests, CI results and PR metadata.
- Edit files needed for the current blocker.
- Run compile/tests/build checks in the disposable GitHub Actions runner.
- Commit and push a normal non-force commit to the active PR head branch.
- Post a concise PR status comment.

## Forbidden
- Live OKX execution or changing demo/live mode.
- Accessing .env, OKX API keys, account secrets, deployment credentials, or unrelated GitHub secrets.
- Force push, history rewrite, direct push to main, or automatic merge.
- Disabling CI checks or changing branch protection.
- Raising leverage, position limits, risk limits, or bypassing safety controls.
- Unrelated cleanup changes.
- Fixing more than one independent blocker in a single cycle.

## Stop conditions
Stop and report when required secrets are unavailable, the same blocker recurs twice, CI is unrelated/flaky, a change would affect live trading, or the PR is closed/merged.
