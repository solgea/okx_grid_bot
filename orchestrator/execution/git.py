import subprocess
from dataclasses import dataclass

_ALLOWED = {"status", "diff", "rev-parse", "branch", "log"}

@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str

class GitExecutor:
    def run(self, operation: str, *args: str) -> GitResult:
        if operation not in _ALLOWED:
            raise PermissionError(f"git operation not allowlisted: {operation}")
        proc = subprocess.run(["git", operation, *args], text=True, capture_output=True, check=False)
        return GitResult(proc.returncode, proc.stdout, proc.stderr)

    def read(self): return self.run("status", "--short")
    def branch(self, name): return self.run("branch", name)

    def commit(self, message):
        proc = subprocess.run(["git", "commit", "-m", message], text=True, capture_output=True, check=False)
        return GitResult(proc.returncode, proc.stdout, proc.stderr)

    def head_sha(self):
        return self.run("rev-parse", "HEAD")
