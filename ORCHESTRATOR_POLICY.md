# Orchestrator Policy

Restricted by default: live_order, live_withdrawal, live_account_mutation, production_deploy, policy_change, merge_pr.

Agents cannot self-authorize restricted actions. Git execution is allowlisted and arbitrary shell execution is not exposed.
