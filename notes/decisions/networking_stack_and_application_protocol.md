# Decision record: networking stack and application protocol

**Status:** Locked for MVP (Python coordinator + workers); C++ coordinator later must speak the same framing.  
**Date:** 2026-11-05  
**Related code:** `MCMC_implementation/workers/protocol.py`, `replica_worker.py`, `pt_coordinator.py`  
**Related plans:** `docs/replica_worker_implementation_plan.md`, `docs/hipergator_outbound_connect_smoke_test.md`

This note records **what we chose**, **what else we considered**, and **tradeoffs** at each layer of the stack used for parallel tempering (PT) control traffic.

---

## Stack overview (top → bottom)

```text
┌─────────────────────────────────────────────────────────────┐
│ Application protocol   length-prefixed UTF-8 JSON messages  │
│                        (REGISTER, RUN_BATCH, STATUS, …)     │
├─────────────────────────────────────────────────────────────┤
│ Transport             TCP (reliable byte stream + handshake)│
├─────────────────────────────────────────────────────────────┤
│ Network              IP (addressing / routing between hosts)│
├─────────────────────────────────────────────────────────────┤
│ Link                 Ethernet (or cluster fabric exposed    │
│                       as IP); frames on the local segment   │
└─────────────────────────────────────────────────────────────┘
```

PT science (tempered Metropolis, swap formula) sits **above** this stack. Networking only moves **control and scalar diagnostics** so the coordinator can barrier replicas and decide temperature exchanges.

---

## Important clarification: what is on the wire today

The application protocol carries **small control JSON**, not full MCMC state.

| On the wire (MVP) | Not on the wire (MVP) |
|-------------------|------------------------|
| `replica_id`, `temperature` | Bed topography arrays |
| Untempered `energy` \(E\) | RNG / spectral overlay state |
| Batch metrics (`a_local`, accept counts, …) | Full checkpoints (`export_state` exists on the adapter but is unused by PT) |
| Commands: `RUN_BATCH`, `SET_TEMPERATURE`, `SHUTDOWN`, … | Bed-swap payloads |

**RNG seeds** are set at process launch (CLI / YAML). The **coordinator RNG** (for swap uniform \(u\)) lives only in the coordinator process. Workers keep their own MCMC RNGs locally. Temperature-exchange PT deliberately **moves \(T\)**, not beds or RNG state.

If a future mode ships beds or checkpoints, the **framing** can stay length-prefixed while the **payload** becomes binary or mixed (JSON control + binary blob).

---

## 1. Application protocol

### Decision

**Length-prefixed frames** with a **4-byte big-endian** `uint32` **length** followed by a **UTF-8 JSON object**.

```text
| length (4 bytes, network order) | payload (length bytes, UTF-8 JSON) |
```

- Max payload: `MAX_FRAME_SIZE = 1_048_576` (1 MiB).
- Payload must be a JSON **object** (not array/primitive).
- Implemented in `MCMC_implementation/workers/protocol.py`.

### Why length-prefixing (message boundaries)

TCP is a **byte stream**: it does not preserve application message boundaries. One `recv` may return half a message, or two messages glued together. The application must define how to find the end of each message.

Length-prefixing answers: “read exactly 4 bytes → parse \(N\) → read exactly \(N\) bytes → parse payload.”

### Why JSON for the payload

| Reason | Detail |
|--------|--------|
| Debuggability | Frames are human-inspectable in logs / Wireshark-style dumps after decode |
| Language bridge | Python workers today; C++ coordinator later can use the same schema |
| Schema flexibility | Adding optional STATUS fields does not require regenerating stubs |
| Good enough size | Control messages are hundreds of bytes; JSON overhead is irrelevant next to MCMC batches |
| Explicit contract | `type` field dispatches commands; rejects non-objects and bad UTF-8 |

JSON is **not** chosen because it is the fastest encoding. It is chosen because control-plane clarity and cross-language MVP speed dominate.

### Alternatives considered (application framing + payload)

#### A. Newline-delimited JSON (JSON Lines / NDJSON)

**How it works:** Each message is one JSON value followed by `\n`. Reader accumulates bytes until newline, then `json.loads`.

| Pros | Cons |
|------|------|
| Trivial to type in a terminal | JSON strings may legally contain escaped newlines in some encodings; easy to get wrong |
| Easy to log line-by-line | No hard size cap unless you add one |
| | Binary beds later cannot be embedded cleanly |

**Why not:** We explicitly rejected JSON Lines in the worker plan in favor of length-prefixed frames so C++ and binary payloads stay straightforward.

#### B. Raw length-prefixed **binary** structs (hand-rolled bytes)

**How it works:** Fixed layout, e.g. `[msg_type u8][replica_id u32][energy f64][temperature f64]…` with `struct.pack` / C++ POD serialization.

| Pros | Cons |
|------|------|
| Compact, fast to parse | Schema changes break wire compatibility easily |
| No JSON parser dependency | Harder to debug; every language reimplements layout |
| Natural for beds/float arrays | Endianness and padding must be specified carefully |

**Why not for MVP control plane:** Premature optimization; control traffic is tiny. Binary remains a **future option for bed blobs** inside the same length-prefixed envelope.

#### C. Protobuf / FlatBuffers / Cap’n Proto

**How it works:** Interface Definition Language (IDL) defines messages; codegen produces serializers for Python/C++. Still usually framed (gRPC uses HTTP/2; raw protobuf often uses its own length prefix).

| Pros | Cons |
|------|------|
| Strong schema, versioning fields | Build/codegen overhead for a course/MVP repo |
| Excellent multi-language story | Heavier toolchain than `json` + `struct` |
| Efficient binary | Overkill when messages are small and schema is still moving |

**Why not yet:** Attractive if the control schema stabilizes and C++/Python both ship long-term. Can migrate later without changing TCP topology.

#### D. pickle / Python `marshal`

**How it works:** Serialize arbitrary Python objects to bytes.

| Pros | Cons |
|------|------|
| Fast for Python-only demos | **Unsafe** across trust boundaries; not a stable cross-language contract |
| | Ties the platform to Python forever |

**Why not:** Explicitly rejected as a long-term wire format in the worker plan.

#### E. HTTP/REST or WebSockets

**How it works:** HTTP request/response per command, or WebSocket messages (often text JSON).

| Pros | Cons |
|------|------|
| Ubiquitous tooling | Extra framing/headers; awkward for tight barriers |
| Easy auth proxies in some envs | Not how HPC intra-job control usually looks |
| | WebSocket still needs a message schema on top |

**Why not:** Unnecessary stack for processes inside one SLURM allocation speaking a private control plane.

#### F. MPI (Message Passing Interface)

**How it works:** Ranks in a single parallel job send/recv typed messages via the MPI library (often over a fast cluster fabric).

| Pros | Cons |
|------|------|
| Natural on HPC for SPMD codes | Different programming model than “workers dial a coordinator” |
| Highly optimized collectives | Harder to mix Python science workers + future C++ coordinator as separate processes with our topology |
| | Our locked design is outbound TCP connect, validated on HiPerGator |

**Why not for this runtime:** Platform decision was coordinator-listens / workers-dial-out over TCP so the science worker stays a normal Python process and the coordinator can be replaced independently.

#### G. gRPC

**How it works:** Protobuf schemas + HTTP/2 streams; stubs for client/server RPCs.

| Pros | Cons |
|------|------|
| Industry-standard RPC | Heavy dependency surface for MVP |
| Bidirectional streaming possible | Still “just” an application protocol on TLS/TCP |
| | Barrier-style PT maps fine to simpler custom RPC |

**Why not for MVP:** Same niche as protobuf—revisit if the API surface grows.

### Application-protocol tradeoff summary

| Choice | Main win | Main cost |
|--------|----------|-----------|
| Length-prefixed framing | Correct message boundaries on TCP; C++-friendly | Slightly more code than “read a line” |
| JSON object payload | Readable, flexible, cross-language | Larger than binary; need `allow_nan=False` discipline |
| Small control messages only | Fast to implement; matches temperature-exchange MVP | Bed/RNG shipping deferred to a later payload mode |

---

## 2. Transport layer — TCP

### Decision

**TCP** for all coordinator ↔ worker control connections.

### Why TCP

| Property | Relevance |
|----------|-----------|
| **Reliable delivery** | Lost packets are retransmitted; we do not invent app-level retransmission for control RPCs |
| **Ordered byte stream** | Frames arrive in send order (per connection), which matches request/response sequencing |
| **Connection-oriented (3-way handshake)** | `SYN → SYN-ACK → ACK` establishes a session before REGISTER; failures surface as connect errors |
| **Ubiquitous on HiPerGator** | Works inside SLURM allocations; smoke-tested same-node and two-node |
| **Matches future C++ Asio stack** | Same BSD-sockets model |

The three-way handshake does **not** encrypt traffic and does **not** define messages. It only agrees that both sides are ready to exchange a reliable byte stream.

### Alternatives considered (transport)

#### UDP

**How it works:** Datagrams, no connection, no delivery guarantee, no order guarantee.

| Pros | Cons |
|------|------|
| Lower latency overhead in theory | Must build reliability, ordering, retries yourself |
| Good for loss-tolerant media | Wrong default for PT barriers (missing STATUS breaks the round) |

**Why not:** A lost or reordered control message corrupts the PT barrier. Reliability belongs in the transport for this use case.

#### QUIC

**How it works:** Reliable streams over UDP with TLS built in; used by HTTP/3.

| Pros | Cons |
|------|------|
| Modern, multiplexed, encrypted | Limited need inside a trusted allocation |
| | Operational complexity vs plain TCP for MVP |

**Why not:** Premature for intra-job HPC control.

#### Unix domain sockets

**How it works:** Socket API on a filesystem path; same host only.

| Pros | Cons |
|------|------|
| Faster same-node IPC | Cannot span two compute nodes |

**Why not as the only transport:** Two-node smoke test is a hard requirement. (Could be an optional same-node fast path later.)

### Topology decision (related)

**Coordinator listens; workers dial outbound.**  
Not: workers listen and coordinator connects in.

Validated by `scripts/net_smoke/` and `slurm/net_smoke_*.sh` on HiPerGator. This matches cluster firewall realities better than opening many worker listen ports.

---

## 3. Network layer — IP

### Decision

Use **IP** as provided by the OS/cluster (IPv4 on HiPerGator compute interconnects in practice).

### What IP does (high level)

IP is responsible for **addressing and routing** packets from one host to another across one or more networks. Each host has an IP address; routers forward packets hop-by-hop toward the destination.

In our setting:

- “Internet Protocol” does **not** mean traffic must traverse the public Internet.
- On HiPerGator, worker ↔ coordinator traffic typically stays on the **research cluster’s private IP fabric**.
- TCP segments are encapsulated in IP packets; we never manipulate IP headers from Python.

### Alternatives (rarely chosen by us)

| Option | Notes |
|--------|-------|
| IPv6 | Fine if the cluster offers it; app code should not hard-code address family assumptions beyond what `asyncio`/`getaddrinfo` resolves |
| Non-IP fabrics only (raw InfiniBand verbs, etc.) | Higher performance possible for bulk data; much more complex; not needed for small JSON control |

**Tradeoff:** IP + TCP is portable and good enough for control. If we ever ship large beds at high rate, we might revisit RDMA-style transports—but that is a different product milestone.

---

## 4. Link layer — what “the link” means here

### Decision

We do **not** implement a custom link layer. We use whatever the OS driver exposes under IP—typically **Ethernet** (or a cluster interconnect that is presented to applications as an Ethernet/IP interface).

### What the link layer does (high level)

The link layer moves **frames** between devices on the **same local network segment** (same switch/VLAN/subnet hop):

1. Takes an IP packet from the network layer.
2. Wraps it in a link frame (e.g. Ethernet: dest MAC, src MAC, ethertype, payload, FCS).
3. Transmits bits onto the wire/fiber.
4. The next hop (NIC or switch) receives the frame, checks integrity, and either delivers locally or forwards.

Switches forward on MAC addresses; routers (network layer) forward on IP addresses between segments.

**Examples of link technologies:** Ethernet (1/10/25/100 GbE), Wi‑Fi (not used on compute nodes), InfiniBand (sometimes with IP-over-IB so apps still see IP).

### Why we do not “choose” the link in application code

| Point | Detail |
|-------|--------|
| OS owns drivers | Python/`asyncio` opens a TCP socket; the kernel picks the interface and next hop |
| Cluster ops owns the fabric | HiPerGator networking is configured by site admins |
| Our job | Correct application framing + TCP timeouts + topology (dial-out) |

**Tradeoff:** We inherit the latency/bandwidth of the cluster Ethernet/fabric. We cannot fix a slow link in JSON. We *can* avoid amplifying problems (chatty protocols, huge unnecessary payloads, missing timeouts).

---

## 5. End-to-end picture for one PT round

```text
Worker A (Python)              Coordinator (Python)              Worker B (Python)
     |                                |                                |
     |  TCP connect (3-way)           |←──────── TCP connect ──────────|
     |──────── REGISTER (JSON) ──────►|◄──────── REGISTER ─────────────|
     |◄─────── REGISTER_ACK ──────────|──────── REGISTER_ACK ─────────►|
     |                                |                                |
     |◄────── RUN_BATCH ──────────────|──────── RUN_BATCH ────────────►|
     |   (local MCMC in thread)       |   barrier: wait both STATUS    |
     |──────── STATUS {E,T,…} ───────►|◄─────── STATUS {E,T,…} ────────|
     |                                |  decide_temperature_exchange   |
     |◄── SET_TEMPERATURE (maybe) ────|──── SET_TEMPERATURE (maybe) ──►|
     |──────── STATUS ───────────────►|◄─────── STATUS ────────────────|
```

All boxes labeled JSON are **application protocol** messages. All arrows ride **TCP/IP** over the cluster **link** fabric.

---

## 6. Performance note (why these choices are safe for MVP)

For two replicas:

- Swap Metropolis math: microseconds.
- JSON encode/decode of STATUS: typically microseconds to low tens of microseconds.
- One MCMC `run_batch`: milliseconds to seconds (dominates).

So JSON-on-TCP is **not** the scientific bottleneck. Replacing the coordinator with C++ later targets **orchestration durability and scale**, not a faster \(e^{(1/T_A-1/T_B)(E_A-E_B)}\).

---

## 7. Decision checklist (locked vs deferred)

| Item | Status |
|------|--------|
| Length-prefixed framing (4-byte BE + payload) | **Locked** |
| UTF-8 JSON object control payloads | **Locked** for MVP |
| TCP transport | **Locked** |
| Workers dial out / coordinator listens | **Locked** (smoke-tested) |
| Temperature-exchange (not bed-swap) on the wire | **Locked** for MVP |
| Protobuf / binary bed payloads | **Deferred** |
| C++ coordinator speaking same framing | **Planned** |
| RNG/bed state on the wire | **Deferred** (adapter checkpoint APIs exist locally) |
| Custom link-layer / RDMA | **Out of scope** |

---

## 8. One-paragraph summary (poster / report)

> Our PT control plane uses a custom **application protocol**—length-prefixed UTF-8 JSON—on top of **TCP/IP**. TCP provides a reliable, ordered byte stream after a three-way handshake; IP routes packets across cluster hosts; the link layer (typically Ethernet) moves frames on the local fabric. We rejected newline-delimited JSON, pickle, and UDP for correctness and portability reasons. JSON keeps small control messages debuggable and cross-language-ready while MCMC work remains the dominant cost. Beds and RNG state stay local in the temperature-exchange MVP; only energies, temperatures, commands, and metrics cross the network.
