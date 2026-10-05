class DemoExecutionError(RuntimeError):
    pass

class MutationForbidden(DemoExecutionError):
    pass
