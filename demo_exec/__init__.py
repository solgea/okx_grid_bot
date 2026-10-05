"""Demo execution contract primitives.

Phase A is shadow-only: NullTransport is the only transport permitted.
Real Demo transport is intentionally not implemented here.
"""
from .intent import Intent
from .lifecycle import LifecycleState, Lifecycle
from .transport import NullTransport
from .executor import DemoExecutor, SubmitResult

__all__ = ["Intent", "LifecycleState", "Lifecycle", "NullTransport", "DemoExecutor", "SubmitResult"]
