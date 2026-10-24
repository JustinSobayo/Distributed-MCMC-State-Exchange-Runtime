# HiPerGator Smoke Test — Worker Connects Outbound

Status: **plan for a short on-cluster proof** (no MCMC, no adapter, no C++).

## Implementation status (2026-10-24)

The local smoke-test artifacts are implemented. No HiPerGator allocation has been run by this agent, so on-cluster Test A/Test B and the results note remain pending.

Implemented:

- `scripts/net_smoke/coord_listen.py`: stdlib coordinator; binds `0.0.0.0`, accepts `--expect` workers, validates one line of `HELLO`, returns `ACK coordinator`, and exits nonzero on timeout/socket/protocol failures.
- `scripts/net_smoke/worker_dial.py`: stdlib outbound client; connects with a bounded timeout, sends `HELLO from worker-<replica-id>`, validates the ACK, and exits 0/1.
- `scripts/net_smoke/README.md`: local invocation plus the SLURM execution boundary.
- `slurm/net_smoke_same_node.sh` and `slurm/net_smoke_two_nodes.sh`: optional templates using concurrent `srun` steps and only `<COURSE_GROUP>` / `<gatorlink>` placeholders.

Local validation passed: `coord_listen.py` on `127.0.0.1:17000` accepted `worker_dial.py`, logged the HELLO, returned the ACK, and both scripts printed their `SMOKE_TEST_*_PASS` markers. This only validates the scripts and local TCP; it does not validate the HiPerGator network.

To validate on HiPerGator, replace the placeholders, ensure the scripts are accessible from Blue, submit `slurm/net_smoke_same_node.sh`, then record the job ID and result in §6 below. Run the two-node template only after same-node Test A passes.
Goal: confirm that inside a SLURM allocation, a **worker process can open a TCP connection out to a coordinator process** that is listening — the network mode locked for the replica worker.

Related decision: `docs/replica_worker_implementation_plan.md` §5 (workers connect outbound).

---

## 1. What this proves / does not prove

**Proves**

- Intra-job TCP: coordinator listens → worker dials → short message round-trip succeeds.
- Same pattern on **one node** (mandatory first) and optionally **two nodes** (Test D lite).

**Does not prove**

- Full replica worker / adapter / PT swaps
- Login-node → compute-node connectivity (out of scope; do not use login as coordinator)
- External internet → compute ports
- Production framing or C++ coordinator

---

## 2. Preconditions (HiPerGator)

```text
ssh <gatorlink>@hpg.rc.ufl.edu
# do NOT run the smoke test on the login node

mkdir -p /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime/net_smoke
cd /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime/net_smoke
```

Every `sbatch` / interactive allocation must include course:

```text
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
```

Use Blue for scripts and logs. Keep this test tiny (seconds–minutes).

---

## 3. Minimal programs to create

Put two tiny stdlib-only Python scripts in the Blue smoke dir (or under `scripts/net_smoke/` in the repo and copy/run from Blue).

### `coord_listen.py` — coordinator (listens)

Behavior:

1. Bind `0.0.0.0` on a chosen port (e.g. `7000`) or port `0` then print the chosen port.
2. Accept one connection (or N for multi-worker later).
3. Read one line (e.g. `HELLO from worker-0`).
4. Write one line back (e.g. `ACK coordinator`).
5. Print success + peer address; exit 0.

### `worker_dial.py` — worker (connects outbound)

Behavior:

1. Read `COORD_HOST` and `COORD_PORT` from argv or env.
2. `socket.create_connection((host, port), timeout=30)` (or asyncio equivalent).
3. Send `HELLO from <replica_id>\n`.
4. Read reply; print it; exit 0 on success, non-zero on failure.

No NumPy, no conda env required if system Python 3 is available; otherwise use your course Python module.

---

## 4. Test A — same node (do this first)

### Option A1 — interactive (fastest for you)

```text
# from login node, request an interactive CPU allocation (dev partition if allowed)
srun --pty --account=<COURSE_GROUP> --qos=<COURSE_GROUP> \
  --ntasks=2 --cpus-per-task=1 --time=00:10:00 bash
```

Inside the allocation (still one job, shared node or SLURM-placed):

```text
# terminal logic if you only have one shell: use background + wait
python coord_listen.py --port 7000 > coord.log 2>&1 &
COORD_PID=$!
sleep 1
python worker_dial.py --host 127.0.0.1 --port 7000 --replica-id 0
wait $COORD_PID
cat coord.log
```

**Pass criteria**

- Worker exits 0
- Coordinator log shows accepted connection + `HELLO`
- Worker printed `ACK`

If `127.0.0.1` works, same-node loopback is fine for Test A.

### Option A2 — batch script (two tasks, one node)

```bash
#!/bin/bash
#SBATCH --job-name=net_smoke_a
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime/net_smoke/%x-%j.out

module load python3   # adjust to whatever UF module you use

# Rank 0 = coordinator, Rank 1 = worker (example using srun)
if [[ "${SLURM_PROCID}" -eq 0 ]]; then
  python coord_listen.py --port 7000 --expect 1
else
  # Head node / first task host — adjust if your site exposes a better var
  HOST=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
  sleep 2
  python worker_dial.py --host "$HOST" --port 7000 --replica-id 1
fi
```

Launch pattern may need a small wrapper so both tasks run concurrently via `srun` rather than a single shell `if`. Prefer:

```text
srun --ntasks=1 --exclusive python coord_listen.py --port 7000 &
sleep 2
HOST=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
srun --ntasks=1 --exclusive python worker_dial.py --host "$HOST" --port 7000
wait
```

**Pass criteria:** same as A1, using the job’s hostname (not only loopback).

---

## 5. Test B — two nodes (optional same day)

Only after Test A passes.

```bash
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --ntasks-per-node=1
```

- Start coordinator on node 0 (`srun` bound to that node or `SLURM_PROCID==0`).
- Worker on node 1 dials **node 0’s hostname/IP** on the agreed port.
- Do **not** use `127.0.0.1` for the worker on a different node.

**Pass criteria**

- Cross-node TCP HELLO/ACK succeeds within timeout
- Record timestamps for rough RTT in the log (optional one-liner)

**Fail → next step:** open UFIT-RC support ticket with job id + logs; ask whether user TCP between allocation nodes needs a specific port range. Do not redesign the whole worker until this is clarified.

---

## 6. What to record in the repo after the run

Add a short note under this file or in `docs/notes.md`:

```text
Date:
GatorLink / course account:
Test A result: PASS/FAIL (job id)
Test B result: PASS/FAIL/SKIPPED (job id)
Host/port method used:
Python module used:
Blockers:
```

Update `docs/replica_worker_implementation_plan.md` Agent Context if anything unexpected (e.g. must use a fixed port range).

---

## 7. Definition of done (this smoke test only)

- [x] Scripts exist and passed local stdlib TCP validation; HiPerGator execution remains pending.
- [ ] Test A (same node) PASS
- [ ] (Optional) Test B (two nodes) PASS or documented FAIL + ticket
- [ ] Results note written
- [ ] No login-node compute used for the test

---

## 8. Agent Context (handoff for implementing the smoke scripts)

**Give the implementing agent this entire markdown file.** This task is **independent** of the full replica worker.

### Intent

Justin wants a **quick** HiPerGator validation that **outbound connect** works inside SLURM before trusting multi-node worker dial-in for the real runtime.

### Scope boundary

| In scope | Out of scope |
|----------|----------------|
| `scripts/net_smoke/coord_listen.py` | `replica_worker.py` / adapter / MCMC |
| `scripts/net_smoke/worker_dial.py` | Length-prefixed production framing |
| Optional `slurm/net_smoke_same_node.sh`, `slurm/net_smoke_two_nodes.sh` | C++ coordinator |
| README blurb in `scripts/net_smoke/README.md` | PT swaps, REGISTER JSON schema |

**Framing note:** This smoke test may use **plain line-based** `HELLO`/`ACK` text. That is intentional simplicity. Production worker uses **length-prefixed JSON** (`docs/replica_worker_implementation_plan.md`). Do not merge the two protocols in this smoke task.

### Locked platform decision

- Coordinator **listens**
- Workers **connect outbound**
- Do **not** put coordinator on the login node
- Job I/O under `/blue/<COURSE_GROUP>/<gatorlink>/...`
- Every job needs `--account` and `--qos` for the course group

### Exact deliverables

- [x] `scripts/net_smoke/coord_listen.py` — argparse `--port`, bind `0.0.0.0`, accept ≥1 client, readline HELLO, write ACK, exit 0
- [x] `scripts/net_smoke/worker_dial.py` — argparse `--host --port --replica-id`, connect with timeout, send HELLO line, read ACK, exit 0/1
- [x] `scripts/net_smoke/README.md` — how to run Test A locally + pointer to this doc for HiPerGator
- [x] Optional SLURM scripts with placeholders `<COURSE_GROUP>` / `<gatorlink>` (never hardcode Justin’s real account secrets)

### Implementation rules

1. Stdlib only (`socket` or `asyncio`); no NumPy/conda required for the scripts themselves.
2. Clear exit codes and prints so SLURM `.out` files are enough to judge PASS/FAIL.
3. Prefer the concurrent `srun` pattern in §4 Option A2 over a broken single-shell `SLURM_PROCID` if/else that only runs one branch per task incorrectly — document the chosen launch method in README.
4. Do not edit Niya science code.
5. Commit only if Justin asks (`test:` or `chore:` smoke scripts).

### Local verify (before HiPerGator)

```text
# two terminals or background
python scripts/net_smoke/coord_listen.py --port 7000
python scripts/net_smoke/worker_dial.py --host 127.0.0.1 --port 7000 --replica-id 0
```

### On-cluster verify

Justin (or agent with SSH) runs Test A per §4; record results in §6.

### Success message for Justin

“Same-node (and optionally cross-node) worker→coordinator TCP works on HiPerGator under your account; safe to build replica_worker as connect-outbound.”

### If Justin attaches both plans

- Smoke plan → only scripts + SLURM helpers above.
- Worker plan → Phase 0 asyncio worker (separate PR).
- Do not block worker localhost implementation on HiPerGator PASS unless Justin requires it.