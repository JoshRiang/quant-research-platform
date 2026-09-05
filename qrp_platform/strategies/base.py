"""Strategy abstract base class + plugin registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd


class Strategy(ABC):
    """Base class for all strategies.

    Subclasses must set:
        - `name` (str): unique registry key
        - `description` (str): human-readable one-liner

    And implement:
        - `generate_signals(df) -> DataFrame` with a single `weight` column,
          indexed by the same dates as `df`. Weights should be in [-1, 1]
          (or beyond, but the engine clips them).
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init__(self, **params) -> None:
        self.params = params

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with at least a `weight` column."""


# ---------------------------------------------------------------------------
# Auto-registry. Any class in this directory that subclasses Strategy and has
# a non-empty `name` will be registered.
# ---------------------------------------------------------------------------

_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    """Class decorator that adds a Strategy to the global registry."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    if cls.name in _STRATEGY_REGISTRY:
        # Allow re-imports in tests without raising.
        return cls
    _STRATEGY_REGISTRY[cls.name] = cls
    return cls


def get_strategy(name: str, **params) -> Strategy:
    """Instantiate a registered strategy by name."""
    if name not in _STRATEGY_REGISTRY:
        raise KeyError(
            f"Unknown strategy '{name}'. Available: {sorted(_STRATEGY_REGISTRY)}"
        )
    return _STRATEGY_REGISTRY[name](**params)


def list_strategies() -> list[dict[str, str]]:
    """List registered strategies as {name, description} dicts."""
    return [
        {"name": cls.name, "description": cls.description}
        for cls in _STRATEGY_REGISTRY.values()
    ]