# Benchmarks (run archives only)

**This folder** holds dated experiment archives and this index.  
**Metric definitions** live in [`docs/benchmark_metrics.md`](../docs/benchmark_metrics.md).

There are **two different “benchmark” paths** in the repo — do not mix them:

| Path | Role |
| --- | --- |
| `benchmarks/` **(here)** | Dated **run outputs** (CSV/JSON fingerprints) for plots and papers |
| `MCMC_implementation/benchmarks/` | **Python harness code** (`single_chain_baseline.py`), not results |

Justin’s generated plots go in repo-root [`figures/`](../figures/README.md).  
Bakari/notebook PNGs stay in `MCMC_implementation/figures/`.

---

## Layout

```text
benchmarks/
  README.md
  YYYYMMDD_HHMMSS_TAG_description/
    README.md              ← 3–5 lines: what this is / is not
    batch_metrics.csv      ← or round_metrics.* for PT
    summary.json
    fingerprint.json
```

Copy HiPerGator `results/...` here with `rsync`/`scp` (do not git-commit huge beds).
Small metric folders may stay local; `benchmarks/*` is gitignored except this README
and per-run README files if you force-add them.

On HiPerGator Blue you can mirror the same tree under
`/blue/gly4930/justinsobayo/mcmc_runtime/benchmarks/`.

---

## Current archives

| Folder | Tag | Notes |
| --- | --- | --- |
| `20261110_094921_BASELINE_stancomb_single_cold/` | BASELINE | Stancomb T=1 single chain, 200 proposals smoke |

---

## Metrics we track (short list)

| Metric | Why |
| --- | --- |
| Wall time | Cost |
| Proposal budget / propos/s | Fair work / throughput |
| Energy \(E\) (+ trajectory) | Cold exploration proxy |
| \(a_{\mathrm{local}}\) | Local MH health (diagnostic) |
| \(a_{\mathrm{swap}}\) | PT ladder health (diagnostic) |
| \(T\) / cold worker id | Scientific cold target |
| Fingerprint | Reproducibility |

---

## Label runs honestly

| Tag | Meaning |
| --- | --- |
| `INTEGRATION` | Plumbing works; not a mixing claim |
| `BASELINE` | Cold reference (single or dual) |
| `PT` | Temperature-exchange experiment |
