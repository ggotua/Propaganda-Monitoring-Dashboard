"""Method contract (D-006).

Every analysis method has the shape ``run(segments, ctx)`` where ``ctx`` is injected, so a method
can record LLM calls and cost without owning a client, and can be tested with a fake context.
"Pure" here means **no ambient state**, not "no side effects anywhere": the side effect is routed
through the context.

Nothing in this module implements a method; it defines the contract only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class MethodContext(Protocol):
    """Gateway handed to every method: LLM access, cache, and cost accounting.

    A method receives no database handle and reads no environment variable; everything it needs
    from the outside world arrives through this object (D-006).
    """

    def llm(self, prompt: str, *, prompt_version: str) -> str:
        """Return a model response for ``prompt``, cached by prompt hash.

        Args:
            prompt: Fully rendered prompt text.
            prompt_version: Version tag of the prompt template that produced it.

        Returns:
            The model's response text.
        """
        ...

    def meter(self, *, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        """Record token usage and cost for one call.

        Args:
            input_tokens: Prompt tokens billed.
            output_tokens: Completion tokens billed.
            cost_usd: Measured cost of this call.
        """
        ...


@dataclass(frozen=True, slots=True)
class MethodMeta:
    """Registry entry describing a method.

    Attributes:
        name: Stable method identifier; also the ``res_<name>`` table suffix.
        version: Version of the method's logic (stored on every result row, D-009).
        needs_llm: Whether the method calls the model at all.
        outputs: Result table name.
        charts: Chart block identifiers the workbench may offer (APP-OVERVIEW §9).
    """

    name: str
    version: str
    needs_llm: bool
    outputs: str
    charts: tuple[str, ...] = field(default_factory=tuple)
