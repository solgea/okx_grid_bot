# OKX Engineering Agent V1

Event-driven engineering loop for this repository.

1. GitHub CI completes.
2. The agent receives the CI result.
3. It inspects the first failure, or the next documented gate blocker.
4. It makes one scoped change.
5. It runs local validation.
6. It pushes the active PR branch.
7. The resulting CI run triggers the next cycle.

## Required repository secrets
- OPENAI_API_KEY — used only by the Codex GitHub Action.
- AGENT_GITHUB_TOKEN — fine-scoped GitHub token capable of pushing to this repository and triggering the next CI workflow.

Never provide OKX API keys to this workflow.
