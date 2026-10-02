import argparse, json, os, sys
from pathlib import Path

from orchestrator.core.policy import DefaultPolicyEngine
from orchestrator.execution.dispatcher import ActionDispatcher
from orchestrator.execution.github_actions import GitHubActionsBridge, WORKFLOW_PATH
from orchestrator.agents.planner_agent import PlannerAgent
from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.agents.test_agent import TestAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from .runtime.service import RuntimeService


def _service(root):
    policy = DefaultPolicyEngine()
    agents = {"planner": PlannerAgent(), "engineering": EngineeringAgent(), "test": TestAgent(), "reviewer": ReviewerAgent()}
    return RuntimeService(root, policy, ActionDispatcher(agents, policy), agents)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m orchestrator.cli")
    parser.add_argument("--root", default=".orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("task_file")
    run = sub.add_parser("run")
    run.add_argument("task_id")
    status = sub.add_parser("status")
    status.add_argument("task_id")
    report = sub.add_parser("report")
    report.add_argument("task_id")
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("task_file")
    dispatch.add_argument("--ref", default="main")
    args = parser.parse_args(argv)
    service = _service(args.root)
    try:
        if args.command == "submit":
            payload = json.loads(Path(args.task_file).read_text(encoding="utf-8"))
            record = service.submit(payload)
            print(json.dumps({"task_id": record.task.task_id, "state": record.state.value}))
        elif args.command == "run":
            record = service.run(args.task_id)
            print(json.dumps({"task_id": args.task_id, "state": record.state.value}))
        elif args.command == "status":
            print(json.dumps(service.status(args.task_id), sort_keys=True))
        elif args.command == "dispatch":
            payload = json.loads(Path(args.task_file).read_text(encoding="utf-8"))
            owner = os.getenv("GITHUB_OWNER")
            repo = os.getenv("GITHUB_REPO")
            if not owner or not repo:
                raise ValueError("GITHUB_OWNER and GITHUB_REPO are required")
            bridge = GitHubActionsBridge(owner, repo)
            evidence = bridge.dispatch_and_find_run(WORKFLOW_PATH, args.ref, payload)
            print(json.dumps({
                "task_id": payload["task_id"],
                "run_id": evidence.run_id,
                "status": evidence.status,
                "conclusion": evidence.conclusion,
                "url": evidence.url,
            }, sort_keys=True))
        else:
            print(json.dumps(service.report(args.task_id), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
