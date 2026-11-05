# Implementation plan: configurable parallel tempering (CPU/GPU)

## Goal and scope

Run two replicas of the same glacier-bed inference problem. Each replica is one worker process on CPU or one visible GPU. A CPU coordinator attempts **temperature exchanges** at synchronous batch boundaries. Measure whether coordination improves **cold-target** sampling enough to justify overhead.

This plan records locked product/engineering decisions and the build order. Inspect existing adapter, worker, protocol, and sampler code before changing them. Reuse working components; keep scientific changes minimal and explicit.

The harness is **backend-agnostic**: `science.backend: cpu | cuda`. PT math and protocol are identical; only device placement and CUDA synchronization differ. GPU is the intended Stancomb production path; CPU is for laptop/protocol/math validation and cheap baselines.

---

## Locked engineering decisions (and why)

| Decision | Choice | Why |
| --- | --- | --- |
| What to exchange | **Temperatures only** (beds stay local) | Wire carries scalars; GPU/CPU bed arrays and RNG stay put; same PT stationary idea as state-exchange for identical models; lower overhead than shipping \(500\times500\) beds every round. |
| Not bed/state swap in MVP | Deferred | Feasible on two nodes (~MB/swap) but needs host↔device copies and derived-state consistency; does **not** remove the need for tempered local accept or a coordinator Metropolis decision. |
| How tempering enters Niya | **Edit local accept** in the bundled science copy: `exp((loss_prev-loss_next)/T)` with **default `T=1`** | Real PT requires hot/cold local dynamics; metadata-only `T` (Option B) only demos the wire. Default `T=1` preserves today’s single-chain behavior. |
| Do not silently patch user site-packages | Users of stock upstream Niya keep her accept until they use **this repo’s science build** or a tempering-aware adapter | Avoid “library randomly changed under the hood”; PT is an explicit opt-in stack. |
| External adapter protocol later | `run_batch` / `get_energy` / `set_temperature` (must affect accept) / checkpoint | Bring-your-own chain without monkeypatching. |
| Who decides swaps | **Coordinator only**, one RNG draw | Workers do not vote; avoids split-brain partial exchanges. |
| Swap rule | \(\log\alpha=(1/T_A-1/T_B)(E_A-E_B)\); accept with \(\min(1,e^{\log\alpha})\) | Preserves joint tempered targets; greedy “always give cold the better bed” is invalid MCMC. |
| Energy in swap | **Untempered** loss/energy \(E(b)\) | Matches likelihood tempering contract; \(T\) scales accept, it does not redefine reported \(E\). |
| Sync model | Synchronous rounds, configurable `steps_per_batch` | Correct frozen snapshot; fail-stop beats async recovery in MVP. |
| Placement | Coordinator on CPU, colocated with a worker node OK | No dedicated coordinator GPU/node required. |
| Config | Validated **YAML** | Change \(T\), batch size, seeds, exchange on/off without code edits. |
| Observability | **Terminal + structured round logs** every barrier | Tune cadence/\(T_{\mathrm{hot}}\) from measured behavior, not guesswork. |
| Inference samples | From whichever worker currently holds **\(T=1\)** | Hot samples are not posterior samples under the scientific target. |
| Primary success metric | Cold-chain **mixing / ESS / exploration** vs equal-resource baseline — **not** “higher local acceptance everywhere” | Hot local accept rises by construction when \(T>1\); that alone does not prove PT helps the scientific chain. |
| Equal-resource baseline | **Two independent \(T=1\) chains** (same wall-clock / device budget as one PT pair) | Fair compute comparison. Single cold chain is a useful debug baseline but under-states the non-PT alternative when you already have two devices. |
| Ablation | PT with `exchange.enabled: false` (fixed hot+cold, no swaps) | Separates “tempered locals” from “swap mixing.” |

---

## What you are building in this slice

1. **Niya local accept + adapter wiring** — `T` used inside `chain_crf.run` (and `chain_sgs` if used); adapter `set_temperature` feeds that value into the next `run_batch`.
2. **Coordinator decision-maker** — joint temperature-exchange accept/reject from \((E_A,E_B,T_A,T_B)\).
3. **YAML experiment config** — behavior knobs for baseline vs PT without code edits.
4. **Terminal metrics/logging** — per-round observability (energies, \(T\) map, local accept rates, swap accept, timings, who holds cold).

Out of scope for the first vertical slice: C++ coordinator, Apptainer, async exchange, many-replica ladders, bed shipping.

---

## 0. Do this first (build and eval order)

Correct sequence:

1. **Tempered accept hook in bundled Niya** (`T` arg, default `1`) + adapter passes `T` into `run`.
2. **Prove `T=1` ≡ current behavior** (batch equivalence / accept stats on a fixed seed).
3. **Prove `T>1` changes uphill accepts** on a tiny synthetic target (more uphill accepts than `T=1`, same proposals/seed where comparable).
4. **YAML + logging scaffolding** (even on one process).
5. **Baseline runs**
   - **B0:** one cold chain (`T=1`) — sanity / single-node reference.
   - **B1 (principal):** two independent cold workers, `exchange.enabled: false`, both `temperatures: [1.0, 1.0]` (or two separate single-chain jobs with equal budget).
6. **Coordinator + swap math unit tests** (numeric checks below) + two-worker sync loop.
7. **PT runs** — `[1.0, T_hot]`, `exchange.enabled: true`, same science config and wall-clock budget as B1.
8. **Compare** cold-chain quality and cost (see metrics). Use acceptance rates as **diagnostics**, not as the sole “PT worked” score.

### Important: do not chase “higher acceptance rate” as the PT goal

| Rate | What it means | Expectation under PT |
| --- | --- | --- |
| Local Metropolis acceptance | Fraction of **bed proposals** kept inside a worker | **Hot** (\(T>1\)) should accept **more uphill** moves. **Cold** (\(T=1\)) often stays similar; it may not increase. |
| Exchange acceptance | Fraction of **temperature-swap proposals** kept by the coordinator | Tune toward a healthy band (often cited ~20–40% as a rule of thumb for ladders); very high or very low both can be suboptimal. |

**PT success** = the worker (or label) at \(T=1\) explores/mixes better per wall-clock than the equal-resource all-cold baseline — e.g. ESS/sec, mode occupancy on a known target, cross-run agreement — while logging both acceptance rates for observability.

---

## Acceptance rate formulas (log these)

### Local (per worker, per batch or cumulative)

Over a window of \(N\) attempted bed proposals (accepted + rejected; Niya `run(n)` attempts \(n-1\) proposals):

\[
a_{\mathrm{local}} = \frac{\#\{\text{accepted bed proposals}\}}{N}
\]

Optionally split:

- \(a_{\mathrm{local}}^{\mathrm{uphill}}\) — accepts among proposals with \(\Delta E > 0\)
- \(a_{\mathrm{local}}^{\mathrm{downhill}}\) — usually ~1 when constraints allow

Report **per temperature label** and **per worker id** (worker id ≠ temperature after swaps).

### Exchange (coordinator, cumulative or per window)

Over \(M\) attempted swap decisions at barriers:

\[
a_{\mathrm{swap}} = \frac{\#\{\text{accepted temperature exchanges}\}}{M}
\]

Also log the instantaneous swap probability used that round: \(p_{\mathrm{swap}} = \min(1, \exp(\log\alpha))\) with

\[
\log\alpha = \Bigl(\frac{1}{T_A}-\frac{1}{T_B}\Bigr)(E_A - E_B)
\]

### Terminal line (illustrative)

```text
round=12  E=(152.4,148.1)  T=(1.0,2.0)  cold_worker=A
  a_local=(0.31@T1, 0.55@T2)  p_swap=0.42  swap=ACCEPT
  t_compute_ms=(810,795)  t_wait_ms=(15,0)  t_coord_ms=2
```

Keep definitions stable so you can improve cadence / \(T_{\mathrm{hot}}\) from logs without redefining rates mid-study.

---

## 1. Statistical contract

Let \(b\) be a bed. Likelihood-only tempering:

\[
\pi_T(b) \propto \mathrm{prior}(b)\,\exp(-E(b)/T)
\]

\(E\) is untempered energy (Niya total loss for the MVP contract once audited). Temperature is not ice temperature; it does not change \(E(b)\) for a fixed bed; it only changes accept probabilities.

**Niya change (bundled copy):**

```python
# before (implicit T=1)
acceptance_rate = min(1, np.exp(loss_prev - loss_next))

# after
acceptance_rate = min(1, np.exp((loss_prev - loss_next) / T))  # T defaults to 1
```

Confirm residual/prior/proposal factors still justify loss-only Metropolis; if not, extend the ratio consistently for both local and exchange rules.

**Gate:** Document target; `T=1` matches pre-change baseline; `T>1` only loosens uphill accepts.

---

## 2. YAML configuration

Illustrative pilot:

```yaml
experiment:
  name: stancomb_two_replica_pt
  seed: 1234
science:
  config: configs/stancomb.yaml
  backend: cuda   # cpu | cuda
sampling:
  replicas: 2
  temperatures: [1.0, 2.0]   # baseline B1: [1.0, 1.0]
  steps_per_batch: 50
  rounds: 1000
  warmup_rounds: 200
exchange:
  enabled: true               # baseline / ablation: false
  pairing: two_replica
logging:
  terminal: true
  level: info
  log_every_rounds: 1
runtime:
  coordinator_port: 5000
  round_timeout_seconds: 600
  output_dir: results/stancomb_two_replica_pt
```

Validate: positive ordered temperatures for PT mode; exactly one `1.0` when claiming a cold target; replica count match; `steps_per_batch` consistent with Niya `run(n)` proposing `n-1` times (worker already requires `n >= 2`).

Commands (names illustrative):

```bash
glacier-pt validate --config experiment.yaml
glacier-pt coordinator --config experiment.yaml
glacier-pt worker --config experiment.yaml --coordinator HOST:PORT --worker-id A
glacier-pt worker --config experiment.yaml --coordinator HOST:PORT --worker-id B
```

**Gate:** Temperatures, batch interval, seeds, exchange enablement, backend editable via YAML only.

---

## 3. Adapter and worker

| Operation | Contract |
| --- | --- |
| `run_batch(K)` | `K` attempted proposals semantics aligned with Niya; uses **current** `T` in accept. |
| `get_energy()` | Untempered \(E\) consistent with current bed. |
| `set_temperature(T)` | Updates value **consumed** by next local accepts (not metadata-only). |
| `checkpoint()` / `restore()` | Bed, derived state, `T`, progress, all RNG streams that affect trajectories. |

Reuse existing `TopographyMCMCAdapter` + `ReplicaWorker` protocol (`RUN_BATCH`, `SET_TEMPERATURE`, `STATUS`, …). Extend STATUS with local accept counters and timings for terminal aggregation.

**Gate:** Without exchange, chunked batches match uninterrupted `T=1` runs under reproducible settings.

---

## 4. Synchronous protocol

1. Register + config fingerprint.
2. `RUN_BATCH(round, K, T assignment)`.
3. `STATUS(round, E, T, a_local window, counters, timings)`.
4. Barrier: wait for both valid reports.
5. One coordinator swap decision.
6. `SET_TEMPERATURE` / assignment + ack both sides before next round.

Fail-stop on stale/nonfinite/missing ack. Checkpoint only at completed round boundaries.

**Gate:** No bed moves during the decision; both workers agree on assignments before resume.

---

## 5. Joint temperature-exchange acceptance

```text
log_ratio = (1/T_A - 1/T_B) * (E_A - E_B)
u = coordinator_rng.uniform(0,1)   # open interval preferred
accept = log(u) < min(0, log_ratio)
```

On accept: swap `T_A` and `T_B` only. On reject: keep assignments.

Deterministic checks:

- `T=(1,2), E=(10,12)` → `log_ratio=-1` → \(p\approx 0.3679\)
- `T=(1,2), E=(12,10)` → accept 1
- Equal `E` → accept 1

**Gate:** Unit tests for sign, log-space decision, post-swap assignments.

---

## 6. Compute placement (CPU/GPU)

**One node, two GPUs:** workers on GPU0/GPU1; coordinator CPU.  
**Two nodes:** coordinator + worker A on node A; worker B on node B; TCP dial-out to coordinator.  
**CPU-only pilot:** two worker processes, `backend: cpu`; same protocol.

No CUDA kernel for swap math. Profile sync, network, serialization, barrier wait — not the float ops in the swap formula.

---

## 7. Samples, logs, restart

- Round log: `E`, `T`, pair, `log_ratio`, `p_swap`, swap decision, cold worker id, `a_local` by T and by worker, compute/wait/coord timings.
- Samples from current `T=1` holder after completed rounds; keep rejects/repeats; exclude warmup.
- Restart: restore worker RNGs, coordinator RNG, assignments, round index together.

---

## 8. Validation sequence

1. Audit loss vs \(E\) contract; implement `T` in bundled Niya + adapter wire-up.
2. `T=1` equivalence tests; `T>1` uphill-accept smoke test.
3. Exchange math unit tests.
4. YAML validate + terminal log smoke (single or dual process).
5. Baseline B0 / B1.
6. PT enabled; compare cold metrics to B1 on equal wall-clock.
7. Failure/timeout/restart tests.
8. Small two-node HiPerGator run when local sync works.

Do not infer success from “loss went down” or “hot acceptance went up” alone.

---

## 9. What people often miss (checklist)

- [ ] Tempered **local** accept is mandatory for real PT (swap-only is not enough).
- [ ] Default `T=1` so non-PT users of the bundled copy stay unchanged in behavior.
- [ ] Stock upstream Niya ≠ automatically tempered; document install/adapter contract.
- [ ] Coordinator Metropolis is required for **both** temperature-swap and bed-swap.
- [ ] Primary baseline is **two cold chains**, not only one.
- [ ] Log **local** and **swap** rates separately; don’t optimize the wrong one.
- [ ] Collect inference only at **cold** label; label samples with actual `T` if saving hot.
- [ ] Niya `run(n)` proposes `n-1` times — align `steps_per_batch` / wire `n_iterations`.
- [ ] Dual RNG streams (chain vs RF / spectral) must be checkpointed.
- [ ] CUDA: sync before reading scalar `E` at the barrier.

---

## 10. Delivery checklist

- [ ] Bundled Niya accept uses `/T` with default `T=1`; adapter passes temperature into `run`.
- [ ] `T=1` equivalence + `T>1` uphill-accept tests.
- [ ] Validated YAML (`backend`, temperatures, exchange, logging, runtime).
- [ ] Coordinator swap decision + assignment bookkeeping + unit tests.
- [ ] Terminal/structured round metrics (`a_local`, `p_swap`, `a_swap`, timings, cold holder).
- [ ] Baseline B0/B1 scripts or config profiles.
- [ ] PT vs B1 equal-budget comparison harness.
- [ ] Two-worker CPU smoke; then GPU; then two-node.

Later: C++ coordinator (same protocol), Apptainer, longer ladders, optional bed-exchange mode, other science adapters.

---

## Literature and operational references

- Vousden, Farr, and Mandel (2016), *Dynamic temperature selection for parallel tempering*: https://arxiv.org/abs/1501.05823
- Syed, Bouchard-Côté, Deligiannidis, and Doucet (2022), *Non-Reversible Parallel Tempering*: https://arxiv.org/abs/1905.02939
- UF GPU access: https://docs.rc.ufl.edu/scheduler/gpu_access/
- UF scheduling: https://docs.rc.ufl.edu/quickstart/scheduling/

Batch sizes and example temperatures are engineering pilots, not literature optima. This document reflects decisions from project discussion and does not certify that all items are already implemented in the repository.
