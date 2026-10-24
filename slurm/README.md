# SLURM orchestration

## Net smoke (outbound TCP)

From the **repo root** on Blue:

```bash
mkdir -p /blue/gly4930/justinsobayo/mcmc_runtime/net_smoke
sbatch slurm/net_smoke_same_node.sh
sbatch slurm/net_smoke_two_nodes.sh
```

Logs: `/blue/gly4930/justinsobayo/mcmc_runtime/net_smoke/`. Details: `docs/hipergator_outbound_connect_smoke_test.md`.

## Later

TODO: replica-launch, CPU/GPU resource, and multi-node PT job templates.
