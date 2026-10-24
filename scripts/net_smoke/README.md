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

Copy these scripts to the Blue project directory or invoke them from a cloned checkout there. Run `slurm/net_smoke_same_node.sh` through `sbatch` after replacing `<COURSE_GROUP>` and `<gatorlink>`; it uses two concurrent `srun` steps, with the coordinator launched first. See [the smoke-test plan](../../docs/hipergator_outbound_connect_smoke_test.md) for allocation requirements, the optional two-node test, and result recording.

Do not run the coordinator or worker on the login node.
