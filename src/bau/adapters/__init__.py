"""Adapters for the executive controller (docs/ARCHITECTURE_RFC.md).

The package is additive and ships only the interface and registry. Real
adapters (a coding agent, a local model, a media tool) arrive as thin wrappers
that call the existing Gateway, sandbox and runtime helpers.
"""

from .base import (
    RESULT_STATUSES,
    AdapterBase,
    AdapterRegistry,
    ExecutionContext,
    ExecutionResult,
)

__all__ = [
    "RESULT_STATUSES",
    "AdapterBase",
    "AdapterRegistry",
    "ExecutionContext",
    "ExecutionResult",
]
