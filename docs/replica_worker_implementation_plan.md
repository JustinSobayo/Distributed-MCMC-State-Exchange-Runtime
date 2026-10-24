# Replica Worker — Implementation Plan

Status: **Phase 0 implemented**. The worker, framed protocol, and localhost tests are present.

## Implementation record (2026-10-24)

Implemented Phase 0 only.

Files added/changed:

- `MCMC_implementation/workers/protocol.py`: 4-byte big-endian uint32 length-prefixed UTF-8 JSON framing; `MAX_FRAME_SIZE = 1_048_576`; malformed, non-object, and oversized frames raise `ProtocolError`.
- `MCMC_implementation/workers/replica_worker.py`: package CLI and outbound `asyncio` worker. It locally builds the synthetic CRF pair, registers with the coordinator, and dispatches `RUN_BATCH`, `SET_TEMPERATURE`, `GET_STATUS`, and `SHUTDOWN`.
- `MCMC_implementation/tests/test_replica_worker_protocol.py`: protocol round-trip and oversized-frame tests.
- `MCMC_implementation/tests/test_replica_worker_batch.py`: localhost coordinator/worker round trip covering `REGISTER`, `GET_STATUS`, `RUN_BATCH`, `SET_TEMPERATURE`, and `SHUTDOWN`.

Behavior to validate:

1. `RUN_BATCH` rejects non-integer values and values below 2; valid batches call `adapter.run_batch` via `await asyncio.to_thread(...)`.
2. Every command reply is a `STATUS` JSON object with `ok`, `replica_id`, `temperature`, `energy`, proposal/batch counts, and an error `message` when applicable.
3. The worker accepts a `REGISTER_ACK` but does not require one before subsequent commands.
4. The worker owns one adapter only; it does not run adapters concurrently in one process.
5. `SET_TEMPERATURE` is protocol metadata only. It updates the adapter label/status, but it deliberately does **not** change Niya's MCMC acceptance rule.

Explicitly not implemented:

- No edits to `MCMC_implementation/gstatsMCMC/MCMC.py` (Niya's science implementation is unchanged).
- No `CHECKPOINT` wire command, state/bed transfer, C++ coordinator, YAML config loader, two-replica harness, or telemetry stack.
- No scientifically tempered local acceptance hook. See `pt_temperature_energy_investigation.md`; Option A is deferred pending an approved non-Niya integration point.

Validation commands:

```text
conda activate gstatsMCMC
cd MCMC_implementation
python -m pytest tests/test_replica_worker_protocol.py tests/test_replica_worker_batch.py tests/test_adapter_batch_equivalence.py -v
python -m workers.replica_worker --help
```

This implementation was syntax-checked. The dependency-free protocol test passed locally (2 tests). The MCMC integration test requires the `gstatsMCMC` environment because the default local Python lacks `gstatsim`.
Audience: Justin (review / questions) → handoff agent (implement accurately).

Related:

- `docs/specification.md` — Milestone 5 (worker), Milestone 6–7 (toy PT / CRF temp exchange), §33 next actions
- `docs/pt_temperature_energy_investigation.md` — temperature is metadata until accept injects `T`
- `MCMC_implementation/adapters/topography_mcmc_adapter.py` — science control plane
- `MCMC_implementation/adapters/spectral_rng_overlay.py` — routes spectral `np.random.normal` through `RF.rng` during her call only

---

## 1. What we are building

A **Python replica worker**: one OS process that owns **one** PT replica.

It sits between:

```text
coordinator (Python toy now → C++/TCP later)
        │  async network I/O (commands / replies)
        ▼
replica_worker.py          ← this deliverable
        │  sync calls into adapter (CPU-bound science)
        ▼
TopographyMCMCAdapter
        │
        ▼
Niya chain_crf.run(K)  (unchanged science; source of truth)
```

Roles:

| Piece | Role |
|--------|------|
| **Worker** | Proxy / lifecycle: dial coordinator, handle commands, drive one adapter, reply with status |
| **Adapter** | Tool: `run_batch`, get/set temperature, energy, checkpoint/restore |
| **Coordinator** | Decides swaps; worker does **not** decide who swaps with whom |
| **Niya MCMC** | Proposals + accept/reject; do not refactor into `step()` |

Language decision (locked):

- Worker = **Python**
- Network wait = `asyncio` **from the start** (so the process can accept/control traffic while structured for non-blocking I/O)
- Science `run_batch` = **blocking**; run it in `asyncio.to_thread(...)` (or equivalent) so the event loop is not stuck during MCMC
- C++ = coordinator/TCP later, **not** the worker
- MVP exchange = **temperature assignment swap**; beds stay on the replica (no bed-on-wire required)

---

## 2. Constraints the implementer must respect

1. **One replica per process** — required for safety with `spectral_rng_overlay` (it temporarily redirects global `np.random.normal`). Do not run two adapters concurrently in one process.
2. **Do not edit Niya’s** `MCMC.py` **for worker features** — science is source of truth; overlays stay in adapter layer.
3. `run(n)` **proposal count** — Niya records index 0 as start; proposals are on `1..n-1`. Worker must pass `n_iterations >= 2` into `run_batch`.
4. **Temperature today** — `set_temperature` stores/reports `T` only; her Metropolis rule does not use `T` yet. Worker still must support get/set for protocol + Milestone 7 wiring.
5. **No pickle as long-term wire format** — use **length-prefixed frames** (header + payload). Payload may be JSON for control messages; optional binary beds later.
6. **Observability** — out of scope for v1 of this plan (logging design deferred). Optional minimal `print`/stderr status is OK for debugging; do not build a full telemetry stack in the first PR.

---

## 3. Data the worker handles

### Owned locally (never required on MVP wire)

- `TopographyMCMCAdapter` instance
- Underlying `chain_crf` + `RandField` (built at init)
- Bed + chain RNG + RF RNG (via adapter checkpoint)
- Replica id, current temperature label, batch counter

### Process start (DECIDED: CLI / local init)

Science setup happens **before** networking:

1. Parse CLI / env / local YAML (`replica_id`, `T`, seeds, config path, `coordinator_host:port`)
2. Build `chain` + `rf` locally (synthetic helper in tests; portable config later)
3. `adapter.initialize(...)`
4. Connect outbound → send `REGISTER`
5. Then handle coordinator commands

**No network `INIT` command** in v1.

### On the wire (MVP)

**Worker → coordinator (first message):**

| Message | Meaning |
|---------|---------|
| `REGISTER` | Announce `replica_id`, initial `T` (science already initialized locally) |

**Coordinator → worker (commands):**

| Command | Meaning |
|---------|---------|
| `RUN_BATCH` | `{ "n_iterations": K }` → `adapter.run_batch(K)` |
| `SET_TEMPERATURE` | `{ "temperature": T }` → `adapter.set_temperature(T)` |
| `GET_STATUS` | Return energy/T/metadata without advancing |
| `CHECKPOINT` | Return or persist adapter checkpoint (optional v1) |
| `SHUTDOWN` | Clean exit |

**Outbound replies (illustrative):**

```text
replica_id
ok / error
temperature
energy                  # after at least one successful RUN_BATCH
proposals_completed
batches_completed
message                 # error detail if any
```

Beds / RNG blobs: optional later; **not** required for temperature-exchange MVP.

---

## 4. Suggested module shape

Path: `MCMC_implementation/workers/replica_worker.py` (replace TODO stub).

Suggested structure (implementer may split files if clearer):

```text
workers/
  __init__.py                 # REQUIRED for python -m workers.replica_worker
  replica_worker.py           # CLI entry + asyncio main
  protocol.py                 # length-prefixed encode/decode (recommended split)
```

Also useful for tests (not the HiPerGator smoke scripts):

```text
workers/testing_coordinator.py   # OR helpers inside tests/ — localhost listener stand-in
```

Core types (conceptual):

```text
ReplicaWorkerConfig
  replica_id: int
  coordinator_host: str       # outbound connect target
  coordinator_port: int
  temperature: float
  rng_seed: int               # passed to adapter.initialize
  rf_seed: int                # optional; build_synthetic_crf_pair(rf_seed=...)
  use_synthetic: bool = True  # v1 default; --config YAML later

ReplicaWorker
  adapter: TopographyMCMCAdapter
  async def handle_command(msg) -> reply
  async def run_batch_async(K)   # to_thread(adapter.run_batch, K)
  def apply_temperature(T)
  def status() -> dict
```

### Wire schema (Phase 0 — concrete enough to implement)

**Frame**

```text
uint32 length  (big-endian)  = number of payload bytes
payload        (UTF-8 JSON object for all Phase 0 messages)
```

Default **max payload size**: `1_048_576` bytes (1 MiB). If declared length exceeds max → close connection / error (do not allocate unbounded).

**Common reply fields** (worker → coordinator after each command, and optionally after REGISTER ack handling if coordinator sends nothing first):

```json
{
  "type": "STATUS",
  "ok": true,
  "replica_id": 0,
  "temperature": 1.0,
  "energy": null,
  "proposals_completed": 0,
  "batches_completed": 0,
  "message": null
}
```

`energy` may be `null` until the first successful `RUN_BATCH`.

**REGISTER** (worker → coordinator, first message after connect):

```json
{"type": "REGISTER", "replica_id": 0, "temperature": 1.0}
```

Coordinator may reply with `{"type": "REGISTER_ACK", "ok": true}` or immediately begin sending commands. Implementer: accept either; if no ACK, just wait for the next framed command.

**Commands** (coordinator → worker):

```json
{"type": "RUN_BATCH", "n_iterations": 5}
{"type": "SET_TEMPERATURE", "temperature": 2.0}
{"type": "GET_STATUS"}
{"type": "SHUTDOWN"}
```

**CHECKPOINT** is optional; skip in Phase 0 unless trivial.

After `RUN_BATCH` / `SET_TEMPERATURE` / `GET_STATUS`, worker replies with a `STATUS` object as above (`ok: false` + `message` on errors). After `SHUTDOWN`, reply `STATUS` then close.

Validate `n_iterations >= 2` before calling adapter; on violation return `ok: false` without crashing the process if possible.

Package entry — **DECIDED: `python -m ...`**

Canonical launch (cwd or `PYTHONPATH` includes `MCMC_implementation/`):

```text
cd MCMC_implementation
python -m workers.replica_worker \
  --replica-id 0 \
  --temperature 1.0 \
  --coordinator-host 127.0.0.1 \
  --coordinator-port 7000 \
  --config path/to/config.yaml   # optional later; synthetic OK for v1 tests
```

Requirements for implementers:

- `workers/` must be a package (`workers/__init__.py`)
- `replica_worker.py` must support `python -m workers.replica_worker` via `if __name__ == "__main__"` / `__main__` block
- Do **not** document `python workers/replica_worker.py` as the primary entry (file path OK for debugging only)
- Matches adapter test convention: `MCMC_implementation` on `sys.path`

---

## 5. Network mode for v1 — DECIDED

**Decision (2026-10-24): workers connect outbound (Option B).**

| Role | Behavior |
|------|----------|
| **Coordinator** (C++ later; Python stand-in now) | **Listens** on host:port |
| **Each replica worker** | **Connects out** to the coordinator, then registers (`HELLO` / `REGISTER`) |

Why (HiPerGator research + platform fit):

- External access is via login gateway only; compute nodes are not a public server fleet.
- Direct interactive access to compute nodes is prohibited; coordinator should not live on login nodes dialing into arbitrary compute listeners.
- Multi-node MPI works inside SLURM allocations → intra-job TCP is the realistic path.
- Spec star topology + `REGISTER` messages match “workers dial coordinator.”
- See `docs/hipergator_outbound_connect_smoke_test.md` for a short on-cluster proof before building the full worker.

Not chosen: worker-listen (Option A) as the platform contract. Localhost demos may still temporarily invert roles for debugging, but production protocol = **connect outbound**.

Transport for v1 — **DECIDED: length-prefixed frames**

- Worker: `asyncio.open_connection(coordinator_host, port)`
- Coordinator stand-in: `asyncio.start_server`
- Framing: fixed-width length header (recommend **4-byte big-endian uint32** = payload byte count), then exactly that many payload bytes
- Control payloads: UTF-8 JSON objects (not JSON lines — no newline delimiter framing)
- Optional later: same length prefix with a binary/type tag for bed blobs
- Max frame size: enforce a cap (reject/close if length exceeds limit)
- Keep schema boring so C++ can reimplement the same framing later

Do **not** block the event loop on `run_batch`; always:

```text
await asyncio.to_thread(adapter.run_batch, K)
```

---

## 6. Main loop pseudocode

```text
async def main(config):
    chain, rf = build_chain_pair(config)          # synthetic OK for v1 tests
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=..., temperature=config.T)

    reader, writer = await asyncio.open_connection(
        config.coordinator_host, config.coordinator_port
    )
    await write_message(writer, {
        "type": "REGISTER",
        "replica_id": config.replica_id,
        "temperature": adapter.get_temperature(),
    })

    while not shutdown:
        msg = await read_message(reader)          # async wait on network
        reply = await dispatch(msg)
        await write_message(writer, reply)

async def dispatch(msg):
    if msg.type == RUN_BATCH:
        result = await asyncio.to_thread(adapter.run_batch, msg.K)
        return status_from(adapter, result)
    if msg.type == SET_TEMPERATURE:
        adapter.set_temperature(msg.T)
        return status_from(adapter)
    if msg.type == GET_STATUS:
        return status_from(adapter)
    if msg.type == SHUTDOWN:
        ...
```

Local smoke test without C++:

- Start a tiny coordinator that listens
- Start one worker that connects outbound, REGISTERs, then handles RUN_BATCH / SET_TEMPERATURE
- Assert energy/T remain coherent

HiPerGator precondition:

- Run `docs/hipergator_outbound_connect_smoke_test.md` before relying on multi-node worker dial-in.

---

## 7. Implementation phases

### Phase 0 — Skeleton (this milestone’s first PR)

- Replace stub with importable worker + CLI
- Worker **connects outbound** to a localhost coordinator stand-in
- Local CLI init, then outbound connect + `REGISTER`; commands: `RUN_BATCH`, `SET_TEMPERATURE`, `GET_STATUS`, `SHUTDOWN`
- Init via `build_synthetic_crf_pair` (already on adapter module) for tests
- Unit/integration test: worker dials coordinator ↔ command round-trip
- Optional: confirm HiPerGator outbound smoke test passed (separate plan)

### Phase 1 — Ready for toy / two-replica PT harness

- Stable message schema documented in this file or `docs/wire_protocol.md` stub
- Two worker processes at different `T`; Python coordinator script swaps temperatures only
- Still no C++

### Phase 2 — C++ coordinator handoff (later milestone)

- Same length-prefixed framing; C++ speaks the same header + JSON (or binary) payload
- Worker code should need little change

Out of scope until asked:

- Full logging/observability stack
- Portable Stancomb YAML `initialize(config)` (adapter still takes live chain/rf)
- Injecting `T` into Niya accept/reject
- Bed payload exchange
- Multiple replicas in one process

---

## 8. Tests to add

| Test | Intent |
|------|--------|
| `tests/test_replica_worker_protocol.py` | Encode/decode + dispatch of SET_TEMP / GET_STATUS without MCMC if possible |
| `tests/test_replica_worker_batch.py` | Localhost client: RUN_BATCH returns energy; SET_TEMP reflected in status |
| Optional | Two workers + tiny coordinator temp swap (can live under Milestone 7) |

Reuse synthetic chain builder; keep runtime short (`K` small, e.g. 3–6).

---

## 9. Definition of done (worker v1)

- [x] `replica_worker.py` is a runnable Python entry point (not a TODO stub)
- [x] Worker connects **outbound** to coordinator; asyncio waits on the socket without busy-spinning
- [x] `RUN_BATCH` calls adapter via `asyncio.to_thread`
- [x] `SET_TEMPERATURE` / `GET_STATUS` work
- [x] One-replica-per-process documented in module docstring
- [x] Localhost worker integration test added (run in `gstatsMCMC` env)
- [x] No edits to Niya science loop; temperature remains metadata for worker protocol.
- [ ] This plan’s “Agent Context” section updated if decisions diverge

---

## 10. Open questions (Justin)

Resolve before or during Phase 0; note answers here:

1. Worker listen vs connect-out (Option A vs B)? **DECIDED: connect-out (Option B).**
2. JSON lines vs length-prefixed frames? **DECIDED: length-prefixed frames** (4-byte BE length + payload; JSON control bodies for MVP).
3. Network `INIT` vs CLI/local init? **DECIDED: CLI/local init** (no network `INIT`; worker `REGISTER`s after local setup).
4. Package entry? **DECIDED: `python -m workers.replica_worker`** with cwd/`PYTHONPATH` = `MCMC_implementation/`.

---

# Agent Context (handoff)

**Give the implementing agent this entire markdown file**, not only this section. Read §1–§10 first; this section is a checklist + pitfalls.

## Scope boundary for this handoff

Implement **Phase 0 only** from this document:

- `workers/` package + `python -m workers.replica_worker`
- length-prefixed JSON protocol helpers
- outbound connect + REGISTER + command loop
- localhost coordinator stand-in for tests
- pytest coverage

Do **not** in the same PR unless Justin asks:

- HiPerGator SLURM scripts (that is `docs/hipergator_outbound_connect_smoke_test.md` — separate handoff)
- Milestone 6 toy PT / Milestone 7 multi-replica harness
- C++ coordinator
- Stancomb YAML config loader
- Observability stack
- Editing Niya `MCMC.py`

If both plans are attached: prefer implementing **smoke scripts first** only if Justin says so; otherwise **worker Phase 0 on localhost** does not require HiPerGator PASS.

## Project intent

Build a distributed MCMC state-exchange runtime around Niya’s geostatistical MCMC **without** rewriting her internal loop into `step()`. Python adapter wraps `run(n)` in batches; C++ later coordinates PT over TCP. MVP PT swaps **temperatures**, not beds.

## What already exists (do not redo)

- `MCMC_implementation/adapters/topography_mcmc_adapter.py`
  - Import: `from adapters.topography_mcmc_adapter import TopographyMCMCAdapter, build_synthetic_crf_pair` (with `MCMC_implementation` on path)
  - `initialize(chain, rf, rng_seed=..., temperature=...)`
  - `run_batch(n_iterations)` → Niya `chain.run(...)` with live Generator; resumes bed between batches
  - `get_energy` / `get_temperature` / `set_temperature` / `get_metadata`
  - `checkpoint` / `restore_checkpoint` (bed + chain RNG + RF RNG)
  - `export_state` / `import_state` optional
  - `build_synthetic_crf_pair(...)` for tests — **use this for v1 worker init**
  - Importing the adapter installs `spectral_rng_overlay` automatically
  - Energy refreshed from full bed loss after each batch
- `MCMC_implementation/adapters/spectral_rng_overlay.py` — not thread-safe across concurrent adapters in one process
- `MCMC_implementation/tests/test_adapter_batch_equivalence.py` — pattern for `sys.path` insert of `MCMC_implementation`
- Worker stub only: `MCMC_implementation/workers/replica_worker.py` (`# TODO: ...`) — **no `workers/__init__.py` yet; create it**
- Docs: `docs/specification.md`, `docs/pt_temperature_energy_investigation.md`, this plan, smoke-test plan

## Locked decisions (do not reopen)

| Topic | Decision |
|-------|----------|
| Worker language | Python |
| Network wait | asyncio; `run_batch` via `asyncio.to_thread` |
| Dial direction | Worker **connects outbound**; coordinator **listens** |
| Framing | **4-byte big-endian uint32 length + UTF-8 JSON payload** (not JSON lines) |
| Max frame | 1 MiB default |
| Init | **CLI/local only**; no network `INIT` |
| Entry | `cd MCMC_implementation && python -m workers.replica_worker ...` |
| MVP swap | Temperature assignment; beds stay local |
| Science edits | Do not modify Niya’s loop / spectral body for this task |
| Logging | Minimal stderr/print OK; no telemetry framework |

## Exact deliverables checklist

- [x] `MCMC_implementation/workers/__init__.py`
- [x] `MCMC_implementation/workers/protocol.py` (or equivalent) — `encode_frame(obj) -> bytes`, `async read_frame(reader) -> dict`
- [x] `MCMC_implementation/workers/replica_worker.py` — argparse CLI + asyncio main loop per §6
- [x] Localhost coordinator fixture implemented inside worker integration test
- [x] `tests/test_replica_worker_protocol.py` — frame round-trip; invalid oversized length rejected
- [x] `tests/test_replica_worker_batch.py` — start coordinator, start worker task/process, REGISTER, RUN_BATCH (K=3..6), SET_TEMPERATURE, GET_STATUS, SHUTDOWN
- [x] Module docstring: one replica per process; connect-outbound; length-prefixed framing

## CLI flags minimum

```text
--replica-id
--temperature
--coordinator-host
--coordinator-port
--rng-seed          (optional, default 0)
```

Synthetic chain by default (no `--config` required in Phase 0).

## Import / path pitfalls

- Run and test with cwd `MCMC_implementation` or insert that directory on `sys.path` (same as adapter tests).
- Adapter import pulls `gstatsMCMC` — needs conda env `gstatsMCMC` with project deps.
- Batch tests will be slower than pure protocol tests (MCMC); keep `n_iterations` small.

## Critical invariants

- `n_iterations >= 2` for `run_batch`
- Continuous vs batched: `continuous_n = 1 + n_batches * (batch_n - 1)`
- Temperature metadata ≠ tempered accept until Option A (deferred)
- Do not run two adapters concurrently in one process (spectral overlay)

## Implementation rules for the agent

1. Phase 0 only; minimal files; no drive-by refactors.
2. Prefer teaching-clear code over clever abstractions.
3. Update this plan’s DoD checkboxes if you complete them.
4. Conventional commits only if Justin asks (`feat:` / `test:`).
5. Do not commit secrets or HiPerGator account names with credentials.

## Suggested commit message

```text
feat: add asyncio replica worker with length-prefixed protocol
```

## Env / verify

```text
conda activate gstatsMCMC
cd MCMC_implementation
python -m pytest tests/test_adapter_batch_equivalence.py tests/test_replica_worker_protocol.py tests/test_replica_worker_batch.py -v
python -m workers.replica_worker --help
```

## User preference

Justin wants to **understand** designs; when uncertain, follow this plan rather than inventing new architecture. Ask before expanding scope past Phase 0.
