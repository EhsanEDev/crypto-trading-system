"""Strategy module configuration.

All thresholds live here (loaded from ``configs/default.yaml``); nothing is
hard-coded in the algorithms. Cross-field validation keeps the
configuration honest (positive periods, risk/size bounds, exit toggles).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

MODULE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = MODULE_ROOT.parents[1]
DEFAULT_CONFIG_PATH = MODULE_ROOT / "configs" / "default.yaml"

SCHEMA_VERSION = "1.0"


class VolatilityConfig(BaseModel):
    enabled: bool = True
    percentile: float = 90.0
    lookback: int = 200

    @field_validator("percentile")
    @classmethod
    def _percentile(cls, v: float) -> float:
        if not 0.0 < v <= 100.0:
            raise ValueError("percentile must be within (0, 100]")
        return v

    @field_validator("lookback")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("lookback must be positive")
        return v


class RiskConfig(BaseModel):
    risk_per_trade: float = 0.005
    atr_stop_multiplier: float = 1.5
    reward_ratio: float = 2.0

    @field_validator("risk_per_trade")
    @classmethod
    def _risk(cls, v: float) -> float:
        if not 0.0 < v <= 0.05:
            raise ValueError("risk_per_trade must be within (0, 0.05]")
        return v

    @field_validator("atr_stop_multiplier")
    @classmethod
    def _stop_mult(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("atr_stop_multiplier must be positive")
        return v

    @field_validator("reward_ratio")
    @classmethod
    def _reward(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("reward_ratio must be positive")
        return v


class PortfolioConfig(BaseModel):
    max_open_positions: int = 3
    max_total_exposure: float = 1.0
    one_position_per_symbol: bool = True

    @field_validator("max_open_positions")
    @classmethod
    def _positions(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_open_positions must be positive")
        return v

    @field_validator("max_total_exposure")
    @classmethod
    def _exposure(cls, v: float) -> float:
        if not 0.0 < v <= 5.0:
            raise ValueError("max_total_exposure must be within (0, 5]")
        return v


class ExecutionConfig(BaseModel):
    fee_rate: float = 0.0006
    slippage_bps: float = 5.0

    @field_validator("fee_rate")
    @classmethod
    def _fee(cls, v: float) -> float:
        if not 0.0 <= v <= 0.01:
            raise ValueError("fee_rate must be within [0, 0.01]")
        return v

    @field_validator("slippage_bps")
    @classmethod
    def _slippage(cls, v: float) -> float:
        if not 0.0 <= v <= 100.0:
            raise ValueError("slippage_bps must be within [0, 100]")
        return v

    @property
    def slippage(self) -> float:
        return self.slippage_bps / 10_000.0


class ExitsConfig(BaseModel):
    regime_exit: bool = True
    ema_exit: bool = False


class BacktestConfig(BaseModel):
    initial_equity: float = 10_000.0

    @field_validator("initial_equity")
    @classmethod
    def _equity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("initial_equity must be positive")
        return v


class StrategyConfig(BaseModel):
    strategy_name: str = "trend_pullback_momentum"
    strategy_version: str = "v001"
    assets: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    regime_timeframe: str = "4h"
    entry_timeframe: str = "1h"
    market: str = "futures"

    rsi_recovery_threshold: float = 50.0
    require_close_above_ema20: bool = True
    ema20_period: int = 20
    rsi_period: int = 14
    atr_period: int = 14

    volatility: VolatilityConfig = Field(default_factory=VolatilityConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    exits: ExitsConfig = Field(default_factory=ExitsConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    # path to the research module's data directory (the data contract root)
    research_data_dir: Path = REPO_ROOT / "modules" / "research" / "data"

    @field_validator("strategy_version", "strategy_name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v

    @field_validator("rsi_recovery_threshold")
    @classmethod
    def _rsi_threshold(cls, v: float) -> float:
        if not 0.0 < v < 100.0:
            raise ValueError("rsi_recovery_threshold must be within (0, 100)")
        return v

    @field_validator("market")
    @classmethod
    def _market(cls, v: str) -> str:
        if v not in ("futures", "spot"):
            raise ValueError("market must be 'futures' or 'spot'")
        return v

    @field_validator("assets")
    @classmethod
    def _symbols(cls, v: list[str]) -> list[str]:
        out = []
        for symbol in v:
            normalized = symbol.upper()
            if not normalized.endswith("USDT") or not normalized.isalnum():
                raise ValueError(f"unsupported symbol {symbol!r}: expected an alnum USDT symbol")
            out.append(normalized)
        return out

    @model_validator(mode="after")
    def _timeframes(self) -> "StrategyConfig":
        if self.regime_timeframe != "4h" or self.entry_timeframe != "1h":
            raise ValueError(
                "strategy v001 requires regime_timeframe='4h' and entry_timeframe='1h'"
            )
        if self.research_data_dir is not None and not self.research_data_dir.is_absolute():
            self.research_data_dir = (MODULE_ROOT / self.research_data_dir).resolve()
        return self


def load_config(path: str | Path | None = None, **overrides: Any) -> StrategyConfig:
    """Load YAML config (module default by default) and apply overrides."""
    cfg_path = Path(path or DEFAULT_CONFIG_PATH)
    if not cfg_path.is_absolute():
        cfg_path = MODULE_ROOT / cfg_path
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config file {cfg_path} must contain a YAML mapping")
        raw = loaded
    raw.update({k: v for k, v in overrides.items() if v is not None})
    return StrategyConfig(**raw)
