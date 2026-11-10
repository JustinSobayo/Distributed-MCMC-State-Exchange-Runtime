# Figures (Justin / this runtime)

**This folder is for visualizations produced from our benchmark runs**
(energy traces, acceptance diagnostics, PT comparison panels, posters).

Do **not** put Bakari/Niya notebook assets here. Those live upstream-style under:

`MCMC_implementation/figures/` (IceVelocityMagnitude, Topographies, logo, …)

## Layout

```text
figures/
  README.md
  .gitkeep
  stancomb_single_cold_energy.png     ← generated (gitignored)
  stancomb_single_cold_accept.png
  pt_energy_trace_panel_ab.png        ← later, after dual-cold + PT
```

Plot scripts should write here by default, e.g.
`--output-dir figures`.

## Regenerate Stancomb single-chain diagnostics

```bash
conda activate gstatsMCMC   # or env with matplotlib
python MCMC_implementation/scripts/plot_single_chain_baseline.py \
  --run-dir benchmarks/20261110_094921_BASELINE_stancomb_single_cold \
  --output-dir figures
```

Generated (gitignored PNGs/PDFs; keep README):

- `stancomb_single_cold_energy.png` / `.pdf`
- `stancomb_single_cold_accept.png` / `.pdf`
- `stancomb_single_cold_throughput.png` / `.pdf`
- `stancomb_single_cold_summary.json`

## Data inputs

Prefer archived runs under `benchmarks/` (not `results/` on the cluster, and
not `MCMC_implementation/figures/`). Example local archive already staged:

`benchmarks/20261110_094921_BASELINE_stancomb_single_cold/`
