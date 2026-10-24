# HiPerGator outbound TCP smoke test

These scripts are intentionally stdlib-only and use one line of text, not the production worker's framed JSON protocol. They prove only that a process inside a SLURM allocation can connect outbound to a coordinator process in the same allocation.

## Local Test A

From the repository root:

```bash
python scripts/net_smoke/coord_listen.py --port 7000 > coord.log 2>&1 &
COORD_PID=$!
python scripts/net_smoke/worker_dial.py --host 127.0.0.1 --port 7000 --replica-id 0
wait "$COORD_PID"
cat coord.log
```

Both commands must exit zero. The worker prints `ACK coordinator` and the coordinator prints `SMOKE_TEST_COORDINATOR_PASS`.

## HiPerGator

From the Blue checkout **repo root** (so `SLURM_SUBMIT_DIR` is correct):

```bash
mkdir -p /blue/gly4930/justinsobayo/mcmc_runtime/net_smoke
sbatch slurm/net_smoke_same_node.sh
sbatch slurm/net_smoke_two_nodes.sh
```

Scripts are already wired for `gly4930` / `justinsobayo`. See [the smoke-test plan](../../docs/hipergator_outbound_connect_smoke_test.md) for results and pass criteria.

Do not run the coordinator or worker on the login node.
