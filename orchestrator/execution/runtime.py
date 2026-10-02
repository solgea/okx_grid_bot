import subprocess

from orchestrator.execution.ci import TestExecutor
from orchestrator.execution.git import GitExecutor


def subprocess_runner(command):
    proc = subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
    return proc


def build_test_executor():
    return TestExecutor(subprocess_runner)


def build_commit_executor(git=None):
    git = git or GitExecutor()

    def commit(task_id):
        status = git.read()
        if status.returncode != 0:
            return {"passed": False, "reason": status.stderr.strip() or "git status failed"}
        if not status.stdout.strip():
            return {"passed": False, "reason": "no repository changes to commit"}
        result = git.commit(f"orchestrator: commit {task_id}")
        if result.returncode != 0:
            return {"passed": False, "reason": result.stderr.strip() or "git commit failed"}
        head = git.head_sha()
        if head.returncode != 0 or not head.stdout.strip():
            return {"passed": False, "reason": "commit completed without readable HEAD"}
        return {"passed": True, "commit_sha": head.stdout.strip()}

    return commit
