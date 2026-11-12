"""Neighbor temperature-exchange pairing schedules for N-replica PT."""

from __future__ import annotations


def neighbor_pairs(n_replicas: int, round_index: int) -> list[tuple[int, int]]:
    """Return index pairs (into ordered worker list) for this round's swaps.

    N=2 always pairs (0, 1). For N>2, alternate odd/even neighbor edges so
    adjacent temperatures mix without overlapping pairs in one round.
    """
    if n_replicas < 2:
        raise ValueError("n_replicas must be >= 2")
    if n_replicas == 2:
        return [(0, 1)]
    pairs: list[tuple[int, int]] = []
    start = round_index % 2
    i = start
    while i + 1 < n_replicas:
        pairs.append((i, i + 1))
        i += 2
    return pairs


def pairs_for_config(pairing: str, n_replicas: int, round_index: int) -> list[tuple[int, int]]:
    if pairing == "two_replica":
        if n_replicas != 2:
            raise ValueError("exchange.pairing two_replica requires sampling.replicas == 2")
        return [(0, 1)]
    if pairing == "neighbor_odd_even":
        return neighbor_pairs(n_replicas, round_index)
    raise ValueError(f"unsupported exchange.pairing: {pairing!r}")
