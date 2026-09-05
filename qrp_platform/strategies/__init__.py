"""Strategy plugin package.

Adding a strategy: subclass `Strategy` in this directory. It will be
auto-registered in `_STRATEGY_REGISTRY` the first time `qrp_platform.strategies`
is imported.
"""
from __future__ import annotations

from .base import Strategy, get_strategy, list_strategies

# Importing concrete strategies populates the registry.
from . import momentum  # noqa: F401
from . import mean_reversion  # noqa: F401
from . import multi_factor  # noqa: F401

__all__ = ["Strategy", "get_strategy", "list_strategies"]