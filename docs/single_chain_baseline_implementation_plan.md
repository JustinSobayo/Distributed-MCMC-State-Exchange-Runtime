# Deliverable: single-chain cold baseline harness

**Top of deliverable (say this):**  
I am establishing a reproducible **single-chain, \(T=1\) cold baseline** on the same glacier problem I will later run with parallel tempering. This harness records running local acceptance rate, trailing energy \(E\), wall-clock time, and proposals/sec, plus a fixed seed and software/config fingerprint. Those numbers are what PT runs will be compared against. Tonight’s implementation is the **benchmark driver and metrics**, not the PT coordinator yet. Backend is selectable (`cpu` now for a shippable result; `cuda` on the same harness before claiming GPU PT gains).

Related: `docs/parallel_tempering_implementation_plan.md` (PT comes after this baseline exists).

---

## Goal

Ship a small CLI/script that runs **one** `chain_crf` replica at **\(T=1\)**, no temperature swaps, and writes:

| Metric | Definition |
| --- | --- |
| Running local acceptance rate | \(a_{\mathrm{local}}(t)=\frac{\sum \text{accepted proposals so far}}{\sum \text{attempted proposals so far}}\) |
| Trailing / final energy \(E\) | Untempered total loss after the latest batch (adapter `get_energy()` / refreshed bed energy) |
| Wall-clock | `time.perf_counter()` from first batch start → last batch end |
| Proposals/sec | \(\text{total attempted proposals} / \text{wall-clock seconds}\) |
| Fingerprint | Seed(s), backend, grid/shape, config paths/hashes, git revision, package paths, `T=1`, exchange=false |

Optional for the same run: per-batch log lines (terminal) and a JSON/CSV summary under `results/`.

**Not in this deliverable:** coordinator, swaps, multi-worker PT, editing Niya’s `/T` line (can stay for the PT slice; baseline must run at effective \(T=1\)).

---

## CPU vs GPU — what to establish

| When | Backend | Why |
| --- | --- | --- |
| **Now (tomorrow deliverable)** | **`cpu`** | Runnable locally; proves metrics + fingerprint + compare protocol. |
| **Before GPU PT claims** | **`cuda`** on the **same harness** | Baseline and PT must share backend, grid, and wall-clock budget rules. |
| **Do you need both tonight?** | No | One code path, `backend: cpu \| cuda`. Run CPU now; schedule a GPU baseline job when you have a device, then compare GPU-PT to **GPU** baseline (and CPU-PT to CPU baseline). |

Do **not** compare CPU single-chain acceptance to GPU PT and call it an apples-to-apples PT win.

---

## Locked choices for this harness

1. **Single process, \(T=1\), exchange off** — cold reference chain.
2. **Reuse** `TopographyMCMCAdapter.run_batch` — it already returns `steps` (Niya `step_cache`) and updates energy.
3. **Count proposals correctly** — Niya `run(n)` attempts **`n - 1`** proposals (index 0 is the start, `step_cache[0]` is false).  
   - Attempted this batch: `n_iterations - 1`  
   - Accepted this batch: `int(np.sum(steps[1:]))` if `steps` length is `n_iterations`, else document whatever length Niya returns and test it once.  
   - Do **not** use Niya’s progress formula `sum(step_cache)/(i+1)` for the official baseline (it dilutes with the dummy index 0).
4. **Batching** — e.g. many `run_batch(batch_n)` calls so the terminal shows a **running** \(a_{\mathrm{local}}\) without holding every bed in memory (`only_save_last_bed=True` path).
5. **Synthetic vs Stancomb** — if full Stancomb data/paths are not ready tonight, run the harness on `build_synthetic_crf_pair` (already used by the worker) **and label the fingerprint `problem=synthetic`**. Same metrics code path; swap in Stancomb when data config exists. Do not mix unlabeled synthetic numbers into a “Stancomb baseline” slide.
6. **Fixed seeds** — `rng_seed`, `rf_seed` (and any global seed you set) recorded in the fingerprint and summary JSON.

---

## Suggested YAML (baseline profile)

```yaml
experiment:
  name: single_chain_cold_baseline
  seed: 1234
science:
  problem: synthetic   # synthetic | stancomb (when wired)
  backend: cpu         # cpu | cuda
  config: null         # path when stancomb is ready
sampling:
  temperature: 1.0
  batch_n_iterations: 51   # -> 50 proposals per batch (Niya n-1)
  num_batches: 40          # -> 2000 attempted proposals total
  # tomorrow smoke: ~2k–10k proposals; longer later under fixed wall-clock
logging:
  terminal: true
  log_every_batches: 1
runtime:
  output_dir: results/single_chain_cold_baseline
```

Total attempted proposals ≈ `num_batches * (batch_n_iterations - 1)`.

---

## Implementation steps (do in order)

### 1. Metrics helper (pure, unit-testable)

```text
accumulate_batch(steps, proposals_this_batch) -> accepted_delta, attempted_delta
running_accept(accepted_total, attempted_total) -> float
```

Assert attempted_delta == `batch_n - 1` for the adapter contract.

### 2. Fingerprint builder

Collect and write:

- `experiment.name`, `backend`, `problem`, `temperature`, `exchange=false`
- `seed`, `rf_seed`, `batch_n_iterations`, `num_batches`
- `bed_shape`, dtype
- `git_rev` (`git rev-parse HEAD` or “unknown”)
- hostname, platform, Python version
- optional: hash of YAML file bytes

### 3. Baseline runner script

Location suggestion: `MCMC_implementation/scripts/run_single_chain_baseline.py`  
(or `scripts/run_single_chain_baseline.py` with `sys.path` to `MCMC_implementation`).

Pseudo-flow:

1. Load YAML / argparse (YAML preferred to match PT plan).
2. Build chain+RF (`build_synthetic_crf_pair` or Stancomb builder when available).
3. `adapter.initialize(..., temperature=1.0, rng_seed=...)`.
4. `t0 = perf_counter()`.
5. Loop `num_batches`:
   - `result = adapter.run_batch(batch_n_iterations)`
   - update accepted/attempted from `result["steps"]`
   - read `result["energy"]`
   - if logging: print running \(a_{\mathrm{local}}\), \(E\), batch wall time, cumulative proposals/sec
6. `t1 = perf_counter()`.
7. Write `summary.json` (+ optional `batch_metrics.csv`) under `output_dir`.

### 4. Terminal line format (stable)

```text
batch=3/40  proposals=150  a_local=0.3120  E=1.234e+02  propos/s=12.4  wall_s=12.1
```

Final line:

```text
BASELINE DONE  proposals=2000  a_local=0.3085  E_final=...  wall_s=...  propos/s=...  fingerprint=...
```

### 5. Tests (fast)

- Metrics: known `steps` array → expected \(a_{\mathrm{local}}\).
- Smoke: `num_batches=2`, `batch_n_iterations=3` on synthetic CPU; assert summary keys exist and `attempted == 4`.

### 6. Run for tomorrow’s artifact

```bash
# from appropriate env / cwd
python -m ... run_single_chain_baseline --config configs/single_chain_cold_baseline.yaml
```

Commit or save under `results/.../summary.json` (results may be gitignored — keep a copy for the meeting).

---

## What “enough iterations” means for this deliverable

| Tier | Attempted proposals | Use |
| --- | --- | --- |
| Smoke | ~100 | Script works |
| **Tomorrow talk** | **~2k–10k** | Quote \(a_{\mathrm{local}}\), \(E_{\mathrm{final}}\), propos/s, wall_s |
| Compare-ready | Fixed **wall-clock** (e.g. 30–60 min) later matched by PT | Fair PT comparison |

Record the tier in the summary (`budget_mode: proposals | wall_clock`).

---

## How this compares to PT later

| Baseline (this plan) | PT (next) |
| --- | --- |
| 1 worker, \(T=1\) | 2 workers, e.g. \(T\in\{1,T_{\mathrm{hot}}\}\) |
| No swap | Coordinator swap metrics too |
| Log \(a_{\mathrm{local}}\), \(E\), propos/s | Log cold \(a_{\mathrm{local}}\), hot \(a_{\mathrm{local}}\), \(a_{\mathrm{swap}}\), who holds cold |
| Same YAML science + backend + fingerprint fields | Same problem fingerprint; differ only sampling/exchange |

Equal-resource note (say if asked): a single cold chain is the **first** baseline for tomorrow; the plan’s stricter later baseline is **two** independent cold chains on the same device budget as one PT pair.

---

## Done checklist

- [x] Metrics helper + unit test (proposal counting excludes Niya index 0).
- [x] Fingerprint in `summary.json`.
- [x] Runner: batched `run_batch`, terminal running \(a_{\mathrm{local}}\), final \(E\), wall_s, propos/s.
- [x] YAML profile with `backend: cpu`, `temperature: 1.0`.
- [x] One synthetic CPU run saved for tomorrow (`results/single_chain_cold_baseline/summary.json`; gitignored).
- [ ] (Later) identical run with `backend: cuda` when hardware is available.
- [ ] (Later) Stancomb problem flag when data config is wired.

---

## Explicit non-goals tonight

- Implementing the coordinator or swap formula.
- Claiming PT improvement.
- Using hot-chain acceptance as a success metric.
- Silent monkeypatch of an external Niya install.
