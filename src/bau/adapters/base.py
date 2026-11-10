"""Adapter interface for the executive controller (docs/ARCHITECTURE_RFC.md).

An adapter is a trusted in-process callable that performs one task for the
controller. This module defines only the contract; no real adapter ships here
yet. Tool calls still go through the Universal Gateway, and an adapter is never
handed credentials by this package.

The controller runs adapters synchronously in the caller's thread. There is no
worker pool, no retry and no preemption: cancellation is cooperative, through
``ExecutionContext.should_cancel``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..executive import TaskContract

RESULT_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")


@dataclass(frozen=True)
class ExecutionContext:
    """What an adapter may know about the run. Data only; no authority."""

    task_id: str
    mission_id: str
    should_cancel: Callable[[], bool]

    def cancelled(self) -> bool:
        """True once the owner's cancel has been recorded; stop cleanly."""
        return self.should_cancel()


@dataclass
class ExecutionResult:
    """What an adapter reports back.

    ``status`` is the adapter's own claim (``COMPLETED``, ``FAILED`` or
    ``CANCELLED``). The controller does not independently verify the result;
    Jarvis's verification step remains a separate decision. ``evidence`` is
    returned to the caller and is not persisted by the controller.
    """

    status: str = "COMPLETED"
    artifacts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"status must be one of {RESULT_STATUSES}")

    @property
    def success(self) -> bool:
        """Derived from ``status`` so the two can never disagree."""
        return self.status == "COMPLETED"


class AdapterBase(ABC):
    """The minimal adapter contract: an id, capability tags and one run method.

    Subclasses declare ``adapter_id`` (unique in the registry) and
    ``capabilities`` (free-form tags such as ``"draft"`` or ``"video.clip"``).
    """

    adapter_id: str = ""
    capabilities: tuple[str, ...] = ()

    @abstractmethod
    def run(self, contract: TaskContract, context: ExecutionContext) -> ExecutionResult:
        """Perform the task and return a result.

        Return ``FAILED`` for an expected failure; raise only for an unexpected
        fault. The controller records either as a failed job.
        """


class AdapterRegistry:
    """Adapter lookup by id and by capability tag.

    Registration is explicit and duplicate ids are refused, so one adapter can
    never silently replace another. Several adapters may share a capability.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, AdapterBase] = {}

    def register(self, adapter: AdapterBase) -> None:
        adapter_id = getattr(adapter, "adapter_id", "")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("adapter_id must be a non-empty string")
        if adapter_id in self._adapters:
            raise ValueError(f"adapter {adapter_id!r} is already registered")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> AdapterBase:
        try:
            return self._adapters[adapter_id]
        except KeyError:
            raise KeyError(f"unknown adapter {adapter_id!r}") from None

    def for_capability(self, capability: str) -> list[AdapterBase]:
        return [a for a in self._adapters.values() if capability in a.capabilities]

    def ids(self) -> list[str]:
        return sorted(self._adapters)
