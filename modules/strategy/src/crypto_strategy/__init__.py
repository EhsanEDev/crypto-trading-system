"""crypto-strategy: Strategy + Backtester module of crypto-trading-system.

Consumes Research outputs through the explicit data contract in
``crypto_strategy.data.adapter`` — never Research internals.

Milestone scope: strategy v001 (trend pullback momentum recovery),
risk-based sizing, execution simulation, candle-driven backtester,
performance metrics, auditable reports. Long-only, spot, no live trading.
"""

from .config import StrategyConfig, load_config

__version__ = "0.1.0"

__all__ = ["StrategyConfig", "load_config", "__version__"]
