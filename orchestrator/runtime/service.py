from orchestrator.core.orchestrator import MasterOrchestrator
from .intake import TaskIntake
from .store import PersistentTaskStore

class RuntimeService:
    def __init__(self, root, policy, dispatcher, agents, commit_executor=None):
        self.store = PersistentTaskStore(root)
        self.intake = TaskIntake(policy)
        self.orchestrator = MasterOrchestrator(self.store, policy, dispatcher, agents, commit_executor=commit_executor)

    def submit(self, payload):
        task = self.intake.validate(payload)
        return self.orchestrator.submit(task)

    def run(self, task_id):
        return self.orchestrator.run(task_id)

    def status(self, task_id):
        record = self.store.get(task_id)
        return {"task_id": task_id, "state": record.state.value, "evidence": record.evidence[-1:]}

    def report(self, task_id):
        return self.orchestrator.report(task_id)
