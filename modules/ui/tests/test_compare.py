"""Compare-tab logic tests (diff_labels with pairwise transitions)."""

from __future__ import annotations

import pandas as pd
import pytest

from crypto_ui.core.calibration import diff_labels


def _series(values: list[str], start: str = "2024-01-01", freq: str = "1h") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=index, name="regime")


def test_identical_labels_zero_changes() -> None:
    labels = _series(["TREND_UP"] * 3 + ["RANGE"] * 2)
    diff = diff_labels(labels, labels)
    assert diff["changed_candles"] == 0
    assert diff["changed_pct"] == 0.0
    assert diff["pairs"] == {}


def test_pair_counts_and_transitions() -> None:
    baseline = _series(["TREND_UP"] * 4 + ["RANGE"] * 2 + ["TREND_UP"] * 2)
    candidate = _series(["TREND_UP"] * 2 + ["RANGE"] * 2 + ["TREND_UP"] * 2 + ["TREND_DOWN"] * 2)
    diff = diff_labels(baseline, candidate)
    assert diff["changed_candles"] == 6
    assert diff["changed_pct"] == pytest.approx(6 / 8 * 100)
    assert diff["pairs"] == {
        "TREND_UP -> RANGE": 2,
        "RANGE -> TREND_UP": 2,
        "TREND_UP -> TREND_DOWN": 2,
    }
    assert diff["transitions_out_of"] == {"TREND_UP": 4, "RANGE": 2}
    assert diff["transitions_into"] == {"RANGE": 2, "TREND_UP": 2, "TREND_DOWN": 2}


def test_pairs_sorted_by_count() -> None:
    baseline = _series(["RANGE"] * 8)
    candidate = _series(["TREND_UP"] * 5 + ["TREND_DOWN"] * 2 + ["RANGE"] * 1)
    diff = diff_labels(baseline, candidate)
    rows = sorted(diff["pairs"].items(), key=lambda kv: -kv[1])
    assert rows[0] == ("RANGE -> TREND_UP", 5)


def test_distributions_included() -> None:
    baseline = _series(["TREND_UP"] * 8)
    candidate = _series(["TREND_UP"] * 4 + ["RANGE"] * 4)
    diff = diff_labels(baseline, candidate)
    assert diff["baseline_distribution"]["TREND_UP"] == pytest.approx(100.0)
    assert diff["candidate_distribution"]["RANGE"] == pytest.approx(50.0)


def test_misaligned_indexes_rejected() -> None:
    with pytest.raises(ValueError, match="same index"):
        diff_labels(_series(["TREND_UP"]), _series(["TREND_UP"], start="2025-01-01"))
