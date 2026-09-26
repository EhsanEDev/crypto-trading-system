"""Data adapters (the Research integration boundary)."""

from .adapter import ContractError, ResearchData, align_regime_to_entry, load_symbol_data

__all__ = ["ContractError", "ResearchData", "align_regime_to_entry", "load_symbol_data"]
