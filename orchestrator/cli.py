import argparse, json, sys
from pathlib import Path
from orchestrator.core.policy import DefaultPolicyEngine
from orchestrator.execution.dispatcher import ActionDispatcher
from orchestrator.execution.runtime import build_commit_executor, build_test_executor
from orchestrator.agents.planner_agent import PlannerAgent
from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.agents.test_agent import TestAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from .runtime.service import RuntimeService

def _service(root):
    policy = DefaultPolicyEngine()
    agents = {"planner": PlannerAgent(), "engineering": EngineeringAgent(), "test": TestAgent(build_test_executor()), "reviewer": ReviewerAgent()}
    return RuntimeService(root, policy, ActionDispatcher(agents, policy), agents, commit_executor=build_commit_executor())

def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m orchestrator.cli")
    parser.add_argument("--root", default=".orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit"); submit.add_argument("task_file")
    run = sub.add_parser("run"); run.add_argument("task_id")
    status = sub.add_parser("status"); status.add_argument("task_id")
    report = sub.add_parser("report"); report.add_argument("task_id")
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
        else:
            print(json.dumps(service.report(args.task_id), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
