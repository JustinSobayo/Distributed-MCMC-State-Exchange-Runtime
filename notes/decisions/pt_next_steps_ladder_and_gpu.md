# Next steps: PT ladder usefulness → GPU scale-up

**Status:** Locked direction after Stancomb 2-replica campaign (2026-11-11)  
**Context:** `[1.0, 1.01]` r600 proved swap machinery (`a_swap≈0.51` overall, `≈0.71` post≥180, many cold-label flips). Local `a_local` unchanged by swaps at this tiny ΔT.

## Immediate (still 2-replica CPU — do now)

1. Finish the **matched dual-cold control** at the same budget as the PT r600 run:
   - config: `MCMC_implementation/configs/two_replica_stancomb_baseline_cold.yaml`
   - `T=[1,1]`, exchange OFF, `rounds=600`, out `results/two_replica_stancomb_baseline_cold_r600`
2. Archive + plot dual-cold with the standardized 3-panel figure; keep the existing PT r600 figure.
3. Optional energy-trace compare: dual-cold vs PT cold label at r600 (equal proposal budget).
4. **Do not** raise \(T_\mathrm{hot}\) alone on 2 replicas — that kills swaps (already shown at 1.2 / 1.5).

## Phase A — Multi-replica ladder (science usefulness)

**Goal:** Keep cold at \(T=1\), raise \(T_\max\), keep **neighbor** `a_swap ~ 0.2–0.4`.

**Code status (in progress):** coordinator + launcher accept `N≥2` with
`exchange.pairing: neighbor_odd_even` (and legacy `two_replica` for N=2).
Configs:

- `MCMC_implementation/configs/four_replica_stancomb_pt.yaml` → `T=[1.0, 1.05, 1.15, 1.35]`
- `MCMC_implementation/configs/four_replica_stancomb_baseline_cold.yaml` → four×`T=1`

Still to do after dual-cold r600 lands:

1. Synthetic 4-replica smoke on login/compute, then short Stancomb 4-replica pilot.
2. Metrics per adjacent pair (`a_swap_by_edge` in summary), cold round-trips vs 4-cold baseline.
3. Success = connected ladder + cold mixing better than equal-resource N-cold — not raw headline `a_swap`.

Literature anchors: Kone & Kofke / Atchadé (~0.23 neighbor swaps); Vousden–Farr–Mandel (uniform neighbor acceptance / adaptive spacing).

## Phase B — GPU scale-up (engineering)

**Goal:** Afford longer runs / larger beds once ladder logic is right.

1. Port or enable `science.backend: gpu` path for Stancomb worker batches.
2. Keep the same protocol (coord listen, workers dial) so multi-node TCP stays valid.
3. Re-run Phase A ladder at higher `rounds` (e.g. 2k–10k) without changing science conclusions from short CPU pilots.
4. Profile: batch time, coordinator barrier, swap overhead vs compute.

## Phase C — Adaptive ladder (optional, after N>2 works)

Vousden-style dynamic spacing or later swap-travel objectives. Only after fixed geometric N-replica PT is correct and measurable.

## Explicit non-goals for the immediate experiment

- Exponential round growth on `[1.0, 1.01]` as a substitute for more rungs.
- Claiming PT “helps Stancomb” from swap rate alone without a matched multi-cold baseline.
- Jumping to GPU before the matched dual-cold r600 control is on disk.
