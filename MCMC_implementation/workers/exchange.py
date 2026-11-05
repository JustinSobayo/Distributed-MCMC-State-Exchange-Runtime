"""Joint temperature-exchange Metropolis decision for parallel tempering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExchangeDecision:
    """Result of one coordinator temperature-swap proposal."""

    log_ratio: float
    p_swap: float
    accepted: bool
    u: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "log_ratio": self.log_ratio,
            "p_swap": self.p_swap,
            "accepted": self.accepted,
            "u": self.u,
        }


def exchange_log_ratio(temperature_a: float, temperature_b: float, energy_a: float, energy_b: float) -> float:
    """Return log α = (1/T_A - 1/T_B) * (E_A - E_B) for untempered energies."""
    for label, value in (
        ("temperature_a", temperature_a),
        ("temperature_b", temperature_b),
        ("energy_a", energy_a),
        ("energy_b", energy_b),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")
    if temperature_a <= 0 or temperature_b <= 0:
        raise ValueError("temperatures must be positive")
    return (1.0 / float(temperature_a) - 1.0 / float(temperature_b)) * (
        float(energy_a) - float(energy_b)
    )


def exchange_probability(log_ratio: float) -> float:
    """Return min(1, exp(log_ratio)) with overflow-safe capping."""
    if not math.isfinite(log_ratio):
        raise ValueError("log_ratio must be finite")
    if log_ratio >= 0.0:
        return 1.0
    return math.exp(log_ratio)


def decide_temperature_exchange(
    temperature_a: float,
    temperature_b: float,
    energy_a: float,
    energy_b: float,
    u: float,
) -> ExchangeDecision:
    """Accept a temperature swap with Metropolis probability min(1, exp(log α)).

    ``u`` must be drawn by the coordinator from Uniform(0, 1). The decision uses
    the numerically stable comparison ``log(u) < min(0, log_ratio)`` when u > 0.
    """
    if isinstance(u, bool) or not isinstance(u, (int, float)) or not math.isfinite(u):
        raise ValueError("u must be a finite number")
    if not 0.0 <= float(u) < 1.0:
        raise ValueError("u must satisfy 0 <= u < 1")
    log_ratio = exchange_log_ratio(temperature_a, temperature_b, energy_a, energy_b)
    p_swap = exchange_probability(log_ratio)
    # Prefer log-space when possible; u == 0 accepts almost surely for finite α.
    if float(u) == 0.0:
        accepted = True
    else:
        accepted = math.log(float(u)) < min(0.0, log_ratio)
    return ExchangeDecision(log_ratio=log_ratio, p_swap=p_swap, accepted=accepted, u=float(u))
