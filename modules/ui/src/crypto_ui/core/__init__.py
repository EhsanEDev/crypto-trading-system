"""UI core: framework-agnostic logic (no Streamlit imports).

Everything here is reusable by any future presentation layer. Swap rule:
``core/`` is pure pandas + the research public API; ``pages/`` + ``app.py``
hold all presentation-framework code.
"""

from .calibration import CalibrationResult, recompute_regimes
from .dataset import available_markets, available_symbols, load_symbol_data
from .presets import PresetStore

__all__ = [
    "available_markets",
    "available_symbols",
    "load_symbol_data",
    "CalibrationResult",
    "recompute_regimes",
    "PresetStore",
]
