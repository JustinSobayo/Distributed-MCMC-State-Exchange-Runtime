"""Unit tests for coordinator temperature-exchange Metropolis math."""

from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.exchange import (  # noqa: E402
    decide_temperature_exchange,
    exchange_log_ratio,
    exchange_probability,
)


def test_plan_numeric_cases():
    # T=(1,2), E=(10,12) → log_ratio=-1 → p≈0.3679
    log_ratio = exchange_log_ratio(1.0, 2.0, 10.0, 12.0)
    assert abs(log_ratio - (-1.0)) < 1e-12
    assert abs(exchange_probability(log_ratio) - math.exp(-1.0)) < 1e-12

    # T=(1,2), E=(12,10) → accept with probability 1
    log_ratio = exchange_log_ratio(1.0, 2.0, 12.0, 10.0)
    assert log_ratio > 0.0
    assert exchange_probability(log_ratio) == 1.0
    decision = decide_temperature_exchange(1.0, 2.0, 12.0, 10.0, u=0.999)
    assert decision.accepted is True
    assert decision.p_swap == 1.0

    # Equal energies → accept 1
    log_ratio = exchange_log_ratio(1.0, 2.0, 11.0, 11.0)
    assert log_ratio == 0.0
    assert exchange_probability(log_ratio) == 1.0


def test_log_space_decision_matches_probability():
    decision_accept = decide_temperature_exchange(1.0, 2.0, 10.0, 12.0, u=0.1)
    assert decision_accept.p_swap == math.exp(-1.0)
    assert decision_accept.accepted is True  # 0.1 < 0.3679

    decision_reject = decide_temperature_exchange(1.0, 2.0, 10.0, 12.0, u=0.9)
    assert decision_reject.accepted is False


def test_rejects_invalid_inputs():
    try:
        exchange_log_ratio(0.0, 2.0, 1.0, 1.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        decide_temperature_exchange(1.0, 2.0, 1.0, 1.0, u=1.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
