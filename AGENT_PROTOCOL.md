# Agent Protocol

`AgentRequest` carries task_id, agent_id, action, and context. `AgentResult` carries task_id, agent_id, status, evidence, and optional next_action.

Valid statuses are success, failure, and blocked. Task IDs must match and evidence must be non-empty.
