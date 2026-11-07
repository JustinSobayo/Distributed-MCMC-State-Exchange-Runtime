# Benchmarks

**This folder** holds dated experiment archives and this index.  
**Metric definitions** (what each number means and why we track it) live in:

→ [`docs/benchmark_metrics.md`](../docs/benchmark_metrics.md)

Read that glossary before comparing runs or writing poster text.

---

## Layout

```text
benchmarks/
  README.md                 ← you are here
  YYYYMMDD_HHMMSS_*/        ← one folder per campaign (copy of results/)
    README.md               ← optional: 3–5 lines on what this run is / is not
    single_chain_.../
    two_replica_baseline_cold/
    two_replica_pt_synthetic/
    stancomb_.../           ← later
```

On HiPerGator, keep the same structure under Blue, e.g.

`/blue/gly4930/justinsobayo/mcmc_runtime/benchmarks/`

Copy this README there if that tree is outside the git clone:

```bash
cp benchmarks/README.md /blue/gly4930/justinsobayo/mcmc_runtime/benchmarks/
```

---

## Metrics we track (short list)

| Metric | Why |
|--------|-----|
| Wall time | How long the run took on the clock (cost) |
| Proposal budget / propos/s | Fair work comparison and throughput |
| Energy \(E\) (+ trajectory) | Did the chain move? Cold exploration proxy |
| \(a_{\mathrm{local}}\) | Local MH health (diagnostic, not the PT trophy) |
| \(a_{\mathrm{swap}}\) | PT ladder health (diagnostic) |
| \(T\) / cold worker id | Which replica is the scientific cold target |
| Fingerprint | Reproducibility for the paper |

Full definitions: [`docs/benchmark_metrics.md`](../docs/benchmark_metrics.md).

---

## Label runs honestly

| Tag in folder name or note | Meaning |
|----------------------------|---------|
| `INTEGRATION` | Plumbing works; not a mixing claim (e.g. toy synthetic, \(a_{\mathrm{local}}=1\)) |
| `BASELINE` | Bakari-path or equal-resource cold reference |
| `PT` | Temperature-exchange experiment to compare to baseline |

Example rename on Blue:

```bash
mv benchmarks/20261106_232021 benchmarks/20261106_232021_INTEGRATION_synthetic
```
