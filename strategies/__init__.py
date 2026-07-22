"""
fluxV strategies module

fluxV is **strategy-agnostic**. This module provides the base infrastructure
for building strategies, but does not bundle any strategy implementations.

Strategy templates have been moved to the `test_strategy/` directory
at the project root and are NOT part of the fluxV package.

Write your own strategies by importing fluxV components directly:

    from fluxV import Broker, OrderRequest, OrderAction, Timeframe

    class MyStrategy:
        async def on_bar(self, bar):
            # your logic here
            pass
"""
from fluxV.strategies.base import BaseStrategy

__all__ = ["BaseStrategy"]
