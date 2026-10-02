from dataclasses import dataclass

@dataclass(frozen=True)
class VerificationEvidence:
    passed: bool
    summary: str
    details: dict

class TestExecutor:
    def __init__(self, runner): self.runner = runner
    def run(self, command):
        result = self.runner(command)
        return VerificationEvidence(result.returncode == 0, "tests passed" if result.returncode == 0 else "tests failed", {"stdout":result.stdout,"stderr":result.stderr})

class CIExecutor:
    def __init__(self, status_provider): self.status_provider = status_provider
    def status(self, commit_sha):
        status = self.status_provider(commit_sha)
        return VerificationEvidence(status == "success", f"CI status: {status}", {"commit_sha":commit_sha,"status":status})
