"""Single tool registry. Finance capabilities register here; CLI and MCP both read from it.

This is the spine of the "build for agents" design: a capability is written once as a
plain Python function, registered as a tool, and is then callable from the shell (CLI)
and by an agent (MCP) with no extra wiring.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

_REGISTRY: dict[str, "Tool"] = {}

# Tool modules whose import side-effects register finance capabilities.
_TOOL_MODULES = [
    "finance_hub.runtime.tools",
    "finance_hub.ingestion.tools",
    "finance_hub.market_data.tools",
    "finance_hub.research.tools",
    "finance_hub.strategy.tools",
]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable


def tool(name: str | None = None, description: str | None = None):
    def deco(fn: Callable) -> Callable:
        t = Tool(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            fn=fn,
        )
        _REGISTRY[t.name] = t
        return fn

    return deco


def load_all() -> None:
    """Import every tool module so its @tool decorators run."""
    for mod in _TOOL_MODULES:
        importlib.import_module(mod)


def all_tools() -> dict[str, Tool]:
    return dict(_REGISTRY)


def get(name: str) -> Tool:
    return _REGISTRY[name]
