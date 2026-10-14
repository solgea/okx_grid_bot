# FreeLLMAPI Integration — Security-First Plan

Status: **foundation only; no model-driven repository writes are enabled**.

## Audit findings

- FreeLLMAPI is an OpenAI-compatible self-hosted gateway. GitHub-hosted runners cannot reach a gateway bound only to a developer machine's `localhost`; the endpoint must be reachable from the runner over HTTPS.
- The repository's current `master-orchestrator.yml` invokes `python -m orchestrator.cli`, but the current `main` tree does not contain an `orchestrator` package. Treat that workflow as unverified until its runtime dependency is restored or the workflow is corrected in a separate scoped change.
- Free tiers have no uptime or quota guarantee. Router failover helps provider-level errors but does not extend ChatGPT limits and cannot guarantee continuous inference.
- Model output is untrusted. No API key, OKX credential, exchange response containing sensitive data, or repository secret may be included in prompts or checkpoint state.

## Implemented foundation

`automation/continuation_state.py` stores only a strict allowlist of task metadata. Unknown fields are rejected; writes use a same-directory temporary file and atomic replace. `WAITING_FOR_QUOTA` requires a UTC resume timestamp and cannot transition directly to `READY`; a separate scheduler/controller must explicitly authorize a resume after rechecking quota and policy.

## GitHub Actions integration plan

1. Deploy FreeLLMAPI outside the ephemeral runner, behind HTTPS and authentication. Do not expose the dashboard or unauthenticated API to the public internet. Keep provider keys in FreeLLMAPI's encrypted store and its encryption key in the host's secret manager.
2. Add GitHub repository Actions secret `FREELLMAPI_API_KEY` and repository variable `FREELLMAPI_BASE_URL` only after the endpoint is secured. The base URL must be an HTTPS origin; never put credentials in the URL.
3. Start with a manual, fixed-prompt connectivity smoke test only. The smoke test must not execute tools, edit files, create commits, or receive OKX secrets. It should log only pass/fail and non-sensitive error classes, never prompts, response bodies, or auth headers.
4. Persist checkpoint metadata as a workflow artifact with short retention or a dedicated protected state branch. Do not use `GITHUB_TOKEN` with broad write permissions in the smoke workflow. A future resume controller must prevent concurrent duplicate task execution and cap retry attempts.
5. A quota wait should stop the current job, save a checkpoint, and let a later scheduled/manual run re-check the quota. Do not keep a runner sleeping indefinitely; hosted runners are ephemeral and time-limited.
6. Model-assisted code changes must be limited to a branch and pull request. CI and human review remain mandatory; no automatic merge, no arbitrary shell execution, no deployment, no exchange mutation.

## Hard safety gates

- Trading stays disabled; Phase B stays locked.
- No API/provider secrets in repository files, logs, artifacts, prompts, or test fixtures.
- No live/demo exchange mutation calls from this integration.
- No automatic PR merge or unrestricted write token.
- Any missing configuration, malformed checkpoint, failed test, unknown state, or provider error fails closed.

## Current scope boundary

This change introduces a tested checkpoint state primitive and its policy. It does **not** yet start FreeLLMAPI requests or claim automatic resumption is operational. The next safe milestone is a manually triggered, no-tools API smoke workflow after an authenticated HTTPS endpoint and repository secret are configured.
