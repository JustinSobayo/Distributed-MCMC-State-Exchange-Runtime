# Distributed MCMC State-Exchange Runtime


## Code-Aware 8-Week Study, Implementation, Validation, and Benchmark Specification


**Primary scientific case study:** Stancomb-Wills Glacier subglacial-topography reconstruction 
**Canonical scientific implementation:** Niya Shao `geostatisticalMCMC` subtree 
**Legacy/reference implementation:** Bakari Kerr Stancomb-Wills package, notebooks, data, and saved outputs 
**Primary first target:** CPU large-scale `chain_crf` (wrapped, not refactored)
**Project duration:** 8 weeks
**Execution progression:** local CPU → adapter batch wrapper → local TCP/PT (temperature exchange) → OCI container → Apptainer + SLURM on HiPerGator → optional GPU backend
**Integration principle:** The runtime integrates with existing MCMC applications through a minimal adapter interface rather than requiring researchers to refactor their scientific sampler around the distributed system.


---






# 0. What Changed After the Repository Audit


The project should **not** start by writing a new MCMC implementation, a new multiprocessing implementation, a GPU speedup, or a rewrite of Niya Shao's internal MCMC iteration loop.


The repository audit established that the codebase already contains:


- a complete scientific MCMC implementation from Niya Shao;
- large-scale CRF MCMC (`chain_crf`);
- small-scale SGS MCMC (`chain_sgs`);
- existing independent multiprocessing using `multiprocessing.Pool(...).starmap(...)`;
- a partial PyTorch GPU implementation for the large-scale CRF chain;
- Bakari Kerr's Stancomb-Wills notebooks, gridded data, figures, saved large/small-scale bed products, and small-chain snapshots;
- no implemented state adapter/wrapper;
- no parallel-tempering logic;
- no C++/TCP runtime;
- no container build;
- no SLURM scripts;
- no executable tests.


**Updated design decision (post-advisor clarification):**


Niya's MCMC implementation is treated as an **external / unchanged scientific workload**.


Do **not**:


- extract or rewrite the internal loop into a custom `step()` API inside Niya's package;
- refactor `chain_crf.run` / `chain_sgs.run` for the distributed system;
- force researchers to restructure their sampler around the runtime.


Do:


- wrap the existing `run(n_iter)` interface with a Python adapter;
- run finite batches such as `run(K)`;
- capture bed/topography + energy after each batch;
- preserve RNG/checkpoint state between batches;
- expose temperature to the distributed runtime;
- resume after a parallel-tempering exchange.


Therefore the project contribution is:


> **Take an existing scientifically meaningful MCMC workload, integrate it through a minimal adapter/wrapper, validate parallel tempering via temperature exchange, then provide a reusable C++/TCP + SLURM execution layer around it — without requiring the scientific sampler to be rewritten.**


This is a stronger platform design than requiring every scientific application to expose a custom `step()` refactor.


---


# 1. Final Project Goal


The final system should support this execution path:


```text
Stancomb-Wills scientific inputs
       ↓
Niya MCMC (unchanged scientific code)
  chain_crf / chain_sgs run(n_iter)
       ↓
Python adapter/wrapper
  - run_batch(K)          # calls existing run(K)
  - get_energy()
  - get/set_temperature()
  - checkpoint / RNG state
  - optional export/import topography state
       ↓
replica worker(s) at assigned temperatures
       ↓
C++/TCP PT runtime
  - replica coordination
  - collect temperature + energy metadata
  - PT swap probability / decision
  - temperature exchange (MVP)
  - optional full-state transfer
  - metrics
       ↓
SLURM + Apptainer on HiPerGator
  (local CPU/Podman earlier in the progression)
       ↓
structured scientific + systems benchmark results
```


The C++ runtime must remain ignorant of glaciology-specific semantics.


It should understand only things such as:


```text
replica id
temperature / beta
iteration / batch index
energy
state version (optional)
payload metadata (optional)
opaque serialized state bytes (optional; not required for MVP swaps)
swap decision
timing/diagnostic metadata
```


The Python scientific adapter owns the scientific meaning of the state, the batch/resume lifecycle, and how temperature affects local acceptance.


**Key sentence:**


> The runtime integrates with existing MCMC applications through a minimal adapter interface rather than requiring researchers to refactor their scientific sampler around the distributed system.


---


# 2. Research Questions






## Primary scientific question


Can parallel-tempering state exchange between concurrently running Stancomb-Wills MCMC replicas improve exploration/convergence relative to independent MCMC chains enough to justify the additional communication and synchronization overhead?


## Systems question


Can the state-exchange mechanism be implemented as a reusable runtime so that the scientific code only needs a small adapter rather than embedded networking/distributed-systems logic?


## Performance questions


Measure:


- wall-clock runtime;
- MCMC iterations per second;
- communication latency;
- serialization/deserialization time;
- bytes transferred;
- synchronization wait time;
- state-exchange frequency;
- swap acceptance rate;
- local MCMC acceptance rate;
- CPU utilization;
- memory usage;
- scaling with replica count;
- time spent in scientific computation versus runtime overhead.






## Scientific-quality questions


Where statistically justified, compare:


- loss / mass-conservation residual;
- convergence/mixing diagnostics;
- accepted realization diversity;
- topographic roughness;
- cold-chain exploration;
- visits between modes or qualitatively distinct regions of state space.


---






# 3. Non-Negotiable Scientific Correctness Gates


There are three gates that must be passed before claiming that the glacier experiment is valid parallel tempering.


## Gate A — Meaning of `loss`


The imported code currently computes approximately:


```text
loss_mc = sum(residual^2) / (2 * sigma_mc^2)
loss_data = 0
loss = loss_mc + loss_data
```


and accepts using:


```text
min(1, exp(loss_current - loss_candidate))
```


This resembles treating `loss` as a negative-log-density-like energy, but the repository does **not** contain a complete derivation of:


- the posterior;
- priors;
- normalization;
- proposal-density terms;
- whether the CRF proposal is symmetric;
- whether the SGS proposal is symmetric.


Before glacier PT:


- document the target distribution mathematically;
- confirm whether `loss` can be used as energy `E(x)`;
- confirm the correct temperature convention;
- confirm whether the proposal needs a Hastings correction;
- get research-advisor/domain sign-off.


**Do not make scientific PT claims before this gate passes.**


## Gate B — Finite batch runs preserve the original chain


Do **not** require extracting Niya's loop into `step()`.


Instead, validate that repeated finite batches preserve scientific behavior when RNG state and starting state are preserved:


```text
original run(100)
```


must match:


```text
run(K) then run(K) then ... totaling 100 iterations
```


for the fields that define the scientific trajectory (for example bed, loss history, accept/reject history, block history, RNG progression), under fixed seeds and identical inputs.


If batching changes the trajectory, the adapter must capture whatever extra checkpoint/RNG state is required until batching is equivalent. Only if batching is impossible without a tiny scientific extension may a **minimal** extension point be added — never a large refactor of the sampler.


If that gate fails, state exchange / temperature exchange cannot be trusted.


## Gate C — Exchange semantics are consistent


### MVP preferred exchange: temperature assignment swap


For the initial PT implementation, prefer swapping **temperature assignments** between replicas rather than physically transferring the full topography state, as long as this is mathematically equivalent for the implementation.


After an accepted swap:


```text
replica_A.temperature <-> replica_B.temperature
```


each replica continues from its current bed with the newly assigned temperature, and the next local acceptance rule must use that temperature.


### Optional capability: physical state import/export


Keep topography serialization/import/export as an optional capability for:


- checkpointing;
- migration;
- workloads that require physical state exchange;
- debugging.


If physical state transfer is used:


```text
state = replica_A.export_state()
replica_B.import_state(state)
```


the receiver must recompute any derived/cached quantities that depend on the bed (for CRF especially `mc_res`, `loss_prev`, `loss_prev_mc`, `loss_prev_data`). A received bed must never continue with stale residual/loss values from the previous local bed.


---


# 4. Canonical Codebase Decision


Use this as the canonical scientific package for new work:


```text
MCMC_implementation/geostatisticalMCMC/
```


Important files:


```text
MCMC_implementation/geostatisticalMCMC/gstatsMCMC/MCMC.py
MCMC_implementation/geostatisticalMCMC/gstatsMCMC/Topography.py
MCMC_implementation/geostatisticalMCMC/gstatsMCMC/MCMC_gpu.py
MCMC_implementation/geostatisticalMCMC/gstatsMCMC/gstatsim_custom/interpolate.py
MCMC_implementation/geostatisticalMCMC/largeScaleChain_multiprocessing.py
MCMC_implementation/geostatisticalMCMC/smallScaleChain_multiprocessing.py
MCMC_implementation/geostatisticalMCMC/largeScaleChain_multiprocessing_GPU.py
```


Treat this older package as reference/legacy unless deliberately reconciled:


```text
MCMC_implementation/gstatsMCMC/
```


Do not allow the current working directory or `PYTHONPATH` to silently choose between the two packages.


Add a reproducibility check that prints/imports the actual source file:


```python
import gstatsMCMC.MCMC
print(gstatsMCMC.MCMC.__file__)
```


Before every benchmark, record which package path is running.


---






# 5. Existing Scientific Workflow You Need to Understand


The current Stancomb-Wills workflow is approximately:


```text
T1_LoadData.ipynb
   ↓
StancombWillsDataGridded.csv
   ↓
T2_StatisticalAnalysis.ipynb
   ↓
variogram / SGS initialization
   ↓
sgs_bed.txt
   ↓
large-scale CRF MCMC
   ↓
lsc_bed.txt
   ↓
small-scale SGS MCMC
   ↓
final/saved realizations
```


The first implementation target should be the **large-scale CRF chain**, not `chain_sgs`.


Why:


- the audit found it simpler;
- the proposal mechanism is a random-field perturbation;
- its current state is easier to define;
- the GPU implementation also targets CRF;
- small-scale SGS has additional transform/trend/variogram/proposal-density complexity;
- PT statistical validity is already the biggest risk, so do not start with the harder sampler.


---






# 6. Study Phase A — MCMC Fundamentals






## Goal


Be able to explain one MCMC iteration without code or notes.


You should be able to define:


- state;
- chain;
- proposal;
- target distribution;
- likelihood;
- posterior;
- acceptance probability;
- rejected proposal;
- burn-in;
- autocorrelation;
- mixing;
- convergence;
- multiple independent chains;
- why accepting a worse state can be correct.






## Mental model


```text
current state x
     ↓
sample proposal x'
     ↓
evaluate target score
     ↓
calculate acceptance probability
     ↓
draw u ~ Uniform(0,1)
     ↓
accept x' or retain x
     ↓
next iteration
```


The chain is sequential internally:


```text
x0 → x1 → x2 → x3 → ...
```


Different chains may run concurrently:


```text
chain A: A0 → A1 → A2 → ...
chain B: B0 → B1 → B2 → ...
chain C: C0 → C1 → C2 → ...
```






## Videos






### Required 1 — Random Walk Metropolis


**Ben Lambert — An introduction to the Random Walk Metropolis algorithm**


[https://www.youtube.com/watch?v=U561HGMWjcw](https://www.youtube.com/watch?v=U561HGMWjcw)


Watch before modifying any MCMC code.


After watching, be able to explain:


- why samples are dependent;
- how a proposal is generated;
- why worse states can be accepted;
- why rejected proposals mean the current state repeats;
- how proposal step size affects exploration.






### Required 2 — Metropolis-Hastings


**Ben Lambert — Constrained parameters? Use Metropolis-Hastings**


Use the author-video collection:


[https://study.sagepub.com/lambert/student-resources/random-walk-metropolis/author-videos](https://study.sagepub.com/lambert/student-resources/random-walk-metropolis/author-videos)


Focus on why an asymmetric proposal changes the acceptance ratio.


This is directly relevant because the repository audit could not prove that all proposal kernels are symmetric.


## Required self-check


Explain these statements in your own words:


1. A state is one candidate model configuration, not the entire chain.
2. A chain is the ordered sequence of states.
3. Rejection means the chain remains at the previous state for another iteration.
4. MCMC samples a distribution; it is not just hill-climbing toward one optimum.
5. Separate chains can execute in parallel even though each individual chain is sequential.


**Do not move on until all five are intuitive.**


---






# 7. Study Phase B — Parallel Tempering






## Goal


Understand why temperature exists, what a replica is, and why there are two distinct acceptance decisions.


A replica is approximately:


```text
one running MCMC chain
+ one assigned temperature/beta
+ one current scientific state
+ one RNG
+ one execution identity
```






## Local MCMC acceptance


Each replica first performs ordinary MCMC.


```text
current state
→ proposal
→ local acceptance/rejection
→ finalized current state
```






## PT swap acceptance


Only at a completed iteration boundary:


```text
replica i current state
replica j current state
       ↓
PT swap acceptance test
       ↓
swap current configurations OR keep them
```


These are **two different accept/reject tests**.


## Temperature


If a target density is represented as:


```text
π(x)
```


a common tempered target is:


```text
πβ(x) ∝ π(x)^β
```


where:


```text
β = 1 / T
```


The `T=1`, `β=1` replica samples the original target.


Hotter chains have smaller beta and flatter target landscapes.


**Do not blindly apply this equation to the current glacier** `loss` **until the statistical gate is resolved.**


## Videos






### Required 1 — MH + Simulated Annealing + Parallel Tempering


**Ted Pavlic — Metropolis-Hastings MCMC & Simulated Annealing/Parallel Tempering**


[https://www.youtube.com/watch?v=0aPqZH2_03w](https://www.youtube.com/watch?v=0aPqZH2_03w)


Pay attention to:


- energy;
- temperature;
- flattening;
- barriers/modes;
- why parallel replicas use different temperatures;
- why exchanges help information move toward the cold chain.






### Required 2 — Geoscience PT


**EarthByte — Bayeslands MCMC and Parallel Tempering tutorial**


Resource page:


[https://www.earthbyte.org/bayeslands-resources/](https://www.earthbyte.org/bayeslands-resources/)


Watch **Part 3: MCMC and Parallel Tempering tutorial**.


This is especially relevant because it connects PT to a geoscientific inverse problem rather than only toy statistics.


## Required self-check


Without notes, draw:


```text
T=1
T=2
T=4
T=8
```


and explain:


- which replica represents the target distribution;
- why the hot replica moves through poor states more easily;
- why a swap happens only after local MCMC is finalized;
- what changes during a swap;
- what stays attached to the worker.


---






# 8. Code Study Phase — Understand Niya's Actual Implementation


Do not start rewriting Niya's loop. Study first, then wrap with an adapter.


Read these files in this order:


## 1. `MCMC.py`


Focus first on:


```text
chain.__init__
chain.loss
chain_crf
chain_crf.run
RandField
get_rfblock
initialization/factory functions
```


The audit traced the CRF iteration to approximately:


```text
MCMC.py:1247-1366
```


Conceptual flow:


```text
RF.get_rfblock()
       ↓
choose update location
       ↓
construct bed_next
       ↓
recompute candidate residual patch
       ↓
calculate loss_next
       ↓
reject invalid ice thickness
       ↓
calculate acceptance probability
       ↓
accept/reject
       ↓
update bed_c / mc_res / loss_prev
       ↓
record diagnostics
```






## 2. `Topography.py`


Understand:


```text
get_mass_conservation_residual
```


Know what scientific quantities enter the residual.


The audit identified the residual approximately as:


```text
∂[velx * (surf-bed)]/∂x
+
∂[vely * (surf-bed)]/∂y
+
dhdt
-
smb
```


Do not memorize the expression without confirming the code and scientific convention.


## 3. `largeScaleChain_multiprocessing.py`


Trace:


```text
parent config
→ dictionary/deepcopy
→ seed per chain
→ Pool.starmap
→ worker reconstructs chain
→ blocking run(n_iter)
→ result/checkpoint files
```


Understand the difference between:


**inter-chain parallelism**


```text
process 1 = chain 1
process 2 = chain 2
```


and:


**intra-chain parallelism**


```text
one chain divides internal numerical work among workers
```


The standard existing multiprocessing path is primarily **inter-chain**.


## 4. Bakari notebooks


Read:


```text
MCMC_implementation/notebooks/T1_LoadData.ipynb
MCMC_implementation/notebooks/T2_StatisticalAnalysis.ipynb
MCMC_implementation/notebooks/T3_LargeScaleChain.ipynb
MCMC_implementation/notebooks/T4_SmallScaleChain.ipynb
```


Your goal is to extract a portable, explicit Stancomb-Wills experiment configuration.


## Deliverable


Create:


```text
docs/scientific_code_walkthrough.md
```


It should explain one CRF iteration with exact code references.


---






# 9. Milestone 1 — Reproducible Stancomb-Wills CPU Baseline






## Objective


Before state exchange, prove you can run the canonical imported Niya implementation on the Stancomb-Wills prepared data.


The historical Bakari output cannot currently be treated as a bitwise reproducible benchmark because the audit found:


- exact historical seed/config provenance is incomplete;
- raw preprocessing files are missing;
- notebooks have personal Windows paths;
- saved outputs do not include rigorous runtime benchmark metadata.


Therefore redefine "match Bakari's benchmark" as:


> **Reproduce the same Stancomb-Wills scientific workflow/input product with an explicitly documented configuration, then establish a new reproducible baseline from that point forward.**


Do not claim exact historical replication unless you recover exact historical parameters and seeds.


## Required work


Create one portable config:


```text
MCMC_implementation/configs/stancomb_wills_crf_baseline.yaml
```


Record at minimum:


```text
input CSV path
initial bed path
grid dimensions
resolution
loss sigma
update mask
proposal/RF parameters
number of iterations
seed for chain RNG
seed for RF RNG
output directory
package source/version
git commit
```


Create a baseline runner that does not depend on notebook state.


## Required output manifest


Each run should produce something like:


```text
run_metadata.json
final_bed.npy
loss.npy
acceptance.npy
block_history.npy
timing.json
stdout.log
```


`run_metadata.json` should contain:


```text
git commit
Python version
dependency versions
machine/CPU
seed(s)
config hash
input file hashes
start/end timestamp
iteration count
canonical package path
```






## Definition of done


A fresh environment can run the same baseline twice with the same seeds and obtain the expected deterministic trajectory/output within the limits of the implementation.


---






# 10. Milestone 2 — Baseline Existing Multiprocessing






## Objective


Use Niya's existing multiprocessing implementation rather than rebuilding it.


Benchmark at least:


```text
1 independent chain
2 independent chains
N independent chains supported by local CPU
```


Do not confuse total throughput with single-chain speed.


Two chains running simultaneously may increase:


```text
aggregate samples / second
```


without reducing:


```text
time per iteration of one chain
```






## Record


For each experiment:


```text
number of processes
physical CPU count
wall time
iterations per chain
aggregate iterations
aggregate it/s
per-chain acceptance
peak RSS if practical
CPU utilization
```






## Deliverable


```text
results/baseline_cpu/
```


plus:


```text
docs/baseline_methodology.md
```






## Definition of done


You have a fair reference against which the later PT runtime can be compared.


---






# 11. Milestone 3 — Statistical Sign-Off Before PT


This milestone can block the entire glacier PT experiment.


Prepare a one-page technical note for the research advisor containing:


```text
current loss equation
current acceptance equation
CRF proposal mechanism
whether proposal is believed symmetric
proposed tempered target
proposed local tempered acceptance equation
proposed replica-swap equation
assumptions
open questions
```


Questions to explicitly resolve:


1. Is `loss` intended to be `-log π(x)` up to a constant?
2. Is the CRF proposal kernel symmetric?
3. If not, what proposal-density correction is required?
4. What exactly is being tempered: likelihood only, posterior, or the current energy surrogate?
5. Are priors intentionally omitted?
6. What temperature ladder convention should be used?
7. Is the cold chain (`T=1`) scientifically equivalent to the existing baseline?






## Definition of done


There is a written, defensible equation for:


```text
local tempered acceptance
```


and:


```text
replica swap acceptance
```


Do not proceed to glacier PT claims without this.


---






# 12. Milestone 4 — Validate Batch `run(K)` Equivalence + Temperature Investigation


## Objective


Treat Niya's MCMC as an unchanged external workload. Prove that the existing `run(n_iter)` interface can be driven in finite batches by a wrapper, and determine how temperature must affect local acceptance for PT.


Do **not** rewrite:


- mass-conservation residual;
- random-field generation;
- scientific data loaders;
- CRF / SGS proposal mathematics;
- Niya's internal iteration loop into a custom `step()` function.


## Required scientific investigation — temperature and energy


Do **not** assume the existing `loss` is automatically the correct PT energy.


Investigate and document:


1. What quantity is currently used in local accept/reject?
2. Is that quantity a valid energy `E(x)` for PT?
3. How must temperature `T` or inverse temperature `β = 1/T` enter the **local** MCMC acceptance rule?
4. Can temperature be injected through existing configuration, a thin wrapper, or a subclass without editing Niya's loop?
5. If not, what is the **smallest** extension point that makes tempered local acceptance possible?


Only if no wrapper/subclass path exists may a minimal scientific extension be proposed. Large refactors are out of scope.


Deliverable:


```text
docs/pt_temperature_energy_investigation.md
```


Advisor/domain sign-off is required before claiming glacier PT validity (ties to Gate A).


## Batch-equivalence validation


Using the unchanged scientific `run(n_iter)`:


```text
A: run(100)
B: run(10) x 10   (or run(K) chunks totaling 100)
```


Same seeds, same inputs. Compare trajectory-defining fields.


Also validate resume-after-pause:


```text
run(K)
capture checkpoint (bed + RNG + any required caches)
run(K) again
```


matches a continuous run of `2K` when checkpointing is correct.


## Definition of done


- batch `run(K)` equivalence is demonstrated or the missing checkpoint fields are identified and captured by the wrapper;
- temperature/energy investigation note exists with a concrete plan for tempered acceptance;
- no large rewrite of Niya's sampler was required.


---






# 13. Milestone 5 — Build the Python Adapter/Wrapper


Create:


```text
MCMC_implementation/adapters/topography_mcmc_adapter.py
MCMC_implementation/workers/replica_worker.py
```


The adapter wraps Niya-specific objects and exposes a runtime-facing interface. The scientific code remains the authority for proposals and (once temperature injection is solved) tempered local acceptance.


## Required adapter interface


```python
class TopographyMCMCAdapter:
    def initialize(self, config): ...
    def run_batch(self, n_iterations: int): ...
    def get_energy(self) -> float: ...
    def get_temperature(self) -> float: ...
    def set_temperature(self, temperature: float): ...
    def get_metadata(self) -> dict: ...
    def checkpoint(self) -> dict: ...          # bed + RNG + required caches
    def restore_checkpoint(self, ckpt: dict): ...

    # Optional — not required for MVP temperature-exchange PT
    def export_state(self) -> bytes: ...
    def import_state(self, payload: bytes): ...
```


`run_batch(K)` must call the existing scientific `run(K)` (or the minimal equivalent path), then capture current bed/topography and likelihood/energy.


## Adapter ownership


Python adapter owns:


```text
batch lifecycle around run(n_iter)
temperature assignment for the replica
energy reporting to the runtime
RNG / checkpoint preservation between batches
optional topography serialize/deserialize
scientific validation
dtype/shape conversion
scientific model version
```


C++ runtime should not know what a glacier bed means.


## Initial MVP exchange model


Prefer:


```text
replicas keep their topography
coordinator swaps temperature assignments
```


Optional schema for physical state transfer / checkpointing:


```text
state_schema_version
model_id
shape
dtype
iteration
energy
temperature
payload_length
payload_checksum
bed bytes
rng/checkpoint blob
```


Do not serialize whole Python class objects as the network protocol.


Avoid pickle as the long-term C++ wire format.


## Definition of done


- adapter can initialize a CRF replica from portable config;
- `run_batch(K)` advances the unchanged scientific chain;
- energy + temperature are readable/settable;
- checkpoint/restore preserves batch equivalence;
- optional export/import exists but is not required for the first PT path.


---


# 14. Milestone 6 — Python-Only Toy Parallel Tempering


This is an intentional change from the original plan.


Do **not** make the C++ networking layer the first place you debug PT mathematics.


First build a tiny PT implementation on a known toy distribution.


Example target:


```text
two separated Gaussian modes
```


Run:


```text
T=1
T=2
T=4
T=8
```


Verify:


- local tempered acceptance behaves as expected;
- swaps occur;
- hot replicas move between modes more easily;
- the `T=1` replica samples the intended target;
- exchange does not corrupt state;
- results are reproducible under fixed seeds.






## Why this matters


It separates:


```text
statistics bugs
```


from:


```text
networking bugs
```


If you build PT and TCP simultaneously, a wrong distribution could come from either layer.


## Definition of done


Toy PT passes sanity checks before glacier PT is enabled.


---






# 15. Milestone 7 — Python-Only Two-Replica CRF Temperature Exchange


Before C++:


```text
Replica 0: T=1
Replica 1: hotter T
```


Run locally in separate Python processes or a simple controlled harness.


Every `exchange_interval` completed iterations / batches:


```text
finish local run_batch(K)
       ↓
report temperature + energy
       ↓
calculate swap probability
       ↓
if accepted (MVP):
   swap temperature assignments
   continue from current beds
optional later:
   exchange bed states + recompute residual/loss
       ↓
continue
```






## Start small


Use:


```text
2 replicas
small iteration count
small exchange interval for testing
```


This experiment is for correctness, not scientific conclusions.


## Metrics


Record:


```text
exchange attempts
exchange accepted
swap acceptance rate
temperature of each replica before/after
energy of each replica before/after
iteration / batch index at each swap
optional state hash before/after
temperature-assign time
scientific batch time
```






## Definition of done


Two replicas can swap temperatures and resume batches repeatedly without trajectory corruption or deadlock.


---






# 16. Study Phase C — TCP and C++ Networking


Only after the scientific state interface is stable should you build transport.


## Concepts to understand


You need to know:


- IP address;
- port;
- client/server;
- socket;
- TCP stream;
- connection lifecycle;
- partial reads;
- partial writes;
- framing;
- network byte order;
- length prefixes;
- serialization;
- persistent connections;
- blocking vs asynchronous I/O;
- timeout;
- disconnect/reconnect;
- backpressure;
- checksums;
- latency vs bandwidth;
- loopback benchmarking.






## Required video 1


**Ozzadar Dev — TCP Client Server Application | C++**


[https://www.youtube.com/watch?v=DVMHEDhYEr4](https://www.youtube.com/watch?v=DVMHEDhYEr4)


Especially:


```text
CMake setup
TCP server/client
persistent connections
dropped connection handling
```






## Required video 2


**Richard Thomson — Getting Started with Boost.Asio**


[https://www.youtube.com/watch?v=XB3uEit5R_Y](https://www.youtube.com/watch?v=XB3uEit5R_Y)


Understand:


```text
io_context
handlers
asynchronous operations
buffer lifetime
```






## Required video 3


**Richard Thomson — TCP/IP Networking with Boost.Asio**


[https://www.youtube.com/watch?v=tyDWXT8-Ykc](https://www.youtube.com/watch?v=tyDWXT8-Ykc)


Focus on:


```text
long-lived connections
async reads
unknown-size data
error handling
```






## Required reference


Boost.Asio official tutorial:


[https://www.boost.org/latest/doc/html/boost_asio/tutorial.html](https://www.boost.org/latest/doc/html/boost_asio/tutorial.html)


---






# 17. Milestone 8 — Define the Wire Protocol Before C++ Implementation


Do not start by writing arbitrary `send()` calls.


Write:


```text
docs/wire_protocol.md
```






## Initial architecture


Prefer a central coordinator for the MVP:


```text
Replica 0 ──TCP──┐
Replica 1 ──TCP──┤
Replica 2 ──TCP──┼── Coordinator
Replica 3 ──TCP──┘
```


Why:


- simpler synchronization;
- one location owns pairing/swap decisions;
- easier metrics;
- easier debugging;
- avoids every worker discovering every other worker.






## Message types


Minimum useful set:


```text
HELLO / REGISTER
READY_FOR_EXCHANGE
ENERGY_REPORT
SWAP_DECISION
TEMPERATURE_ASSIGN          # MVP: apply swapped temperatures
STATE_REQUEST               # optional physical transfer
STATE_HEADER                # optional
STATE_PAYLOAD               # optional
STATE_APPLIED               # optional
HEARTBEAT
SHUTDOWN
ERROR
```






## MVP exchange optimization — temperature first


For the initial PT implementation, prefer swapping temperature assignments.


Always exchange metadata first:


```text
replica
temperature
iteration / batch index
energy
optional state size / hash
```


Coordinator computes whether the swap is accepted.


If accepted (MVP):


```text
swap temperature assignments between the paired replicas
do NOT transfer the topography payload
```


Optional / later:


```text
transfer state payload only when physical state exchange is required
(checkpointing, migration, or workloads that need bed movement)
```


This is one of the highest-value optimizations in the project and matches the adapter-based platform design.


## Framing


TCP is a byte stream; one `send()` does not equal one `recv()`.


Use an explicit frame such as:


```text
magic
protocol_version
message_type
header_length
payload_length
request_id
header
payload
```


Receiver must loop until the exact frame length is read.


## Definition of done


Two tiny C++ test programs can send variable-sized framed messages without assuming packet boundaries.


---






# 18. Milestone 9 — Local C++/TCP Runtime






## Step 1 — Echo/round-trip test


Before MCMC:


```text
client sends metadata
server returns it
```


Measure loopback RTT.


## Step 2 — Representative payload


Generate payloads near expected state size:


```text
~2 MiB
~4 MiB
~8 MiB
```


Measure:


```text
serialization time
send time
receive time
deserialize time
end-to-end state handoff
```






## Step 3 — Persistent connection


Do not reconnect for every exchange.


Compare:


```text
new TCP connection per exchange
```


against:


```text
persistent TCP connection
```


The real implementation should normally use persistent connections.


## Step 4 — Python/C++ integration


Python worker should be able to:


```text
run_batch(K) via adapter
report temperature + energy metadata
receive decision
if accepted (MVP):
   set_temperature(new_T)
   continue from current bed
optional path:
   export/import topography state
continue
```






## Step 5 — failure paths


Test:


```text
worker exits unexpectedly
coordinator exits
truncated payload
wrong protocol version
wrong payload length
checksum mismatch
timeout
duplicate request id
```






## Definition of done


Repeated two-replica exchanges can run for a long test without framing errors, incorrect payloads, deadlocks, or leaked connections.


---






# 19. TCP Performance Optimization Plan


Do not optimize before obtaining a correct baseline.


Order:


## Optimization 1 — Metadata first


Avoid state transfer when swap is rejected.


## Optimization 2 — Persistent sockets


Avoid handshake/connect cost at every exchange.


## Optimization 3 — Avoid unnecessary copies


Measure copies through:


```text
NumPy → Python bytes
Python → C++ boundary
C++ buffer
socket
receiver buffer
Python
NumPy
```


Do not assume zero-copy is necessary until measured.


## Optimization 4 — Binary state payload


Avoid textual CSV/JSON for the large numerical array.


Use JSON only for small metadata if desired.


## Optimization 5 — Async I/O if justified


A synchronous coordinator may be perfectly adequate for 2–8 replicas.


Only introduce asynchronous complexity if profiling shows coordinator blocking is meaningful.


## Optimization 6 — pairing strategy


Alternate adjacent pairs:


```text
exchange round A:
0↔1
2↔3


exchange round B:
1↔2
```


This avoids one replica participating in two simultaneous exchanges.


## Benchmark metrics


```text
RTT for metadata
accepted swap state-transfer latency
effective MB/s
serialization cost
restore/recompute cost
coordinator decision time
total exchange pause
percentage of runtime spent exchanging
```


---






# 20. Container Strategy


The original plan mentioned running Apptainer locally on the Mac.


Change that.


## Local Mac


Use:


```text
native environment for rapid development
or
Podman for OCI container build/test
```






## HiPerGator/Linux


Use:


```text
Apptainer
```


This preserves an industry-standard OCI development path while using the HPC-native runtime on UF compute.


Architecture:


```text
Containerfile
  ↓
Podman builds OCI image locally
  ↓
registry / image archive
  ↓
Apptainer pulls/builds SIF on Linux/HPC
  ↓
SLURM launches Apptainer workload
```






## Container milestones






### CPU first


Container must successfully run:


```text
fixed-seed CRF baseline
adapter tests
replica worker
```






### GPU later


Only after CPU/PT is stable, validate:


```text
Apptainer --nv
PyTorch CUDA
GPU CRF code
```






## Video


**HPC Café — Using Containers on HPC Systems with Apptainer**


A current hands-on session covering Apptainer and Slurm integration:


[https://www.fau.tv/series/hpc4fau-nhr-at-fau-s22/92-hpc-cafe-on-2025-06-24-using-containers-on-the-hpc-systems-at-nhr-at-fau-s25](https://www.fau.tv/series/hpc4fau-nhr-at-fau-s22/92-hpc-cafe-on-2025-06-24-using-containers-on-the-hpc-systems-at-nhr-at-fau-s25)


## Definition of done


The same CPU experiment config produces valid output:


```text
native/local
OCI local
Apptainer/HiPerGator
```


subject to documented floating-point/platform tolerances.


---






# 21. Study Phase D — What SLURM Allocation Actually Means (UFIT-RC / HiPerGator)


SLURM is not the MCMC parallelization algorithm.


SLURM performs:


```text
resource allocation
job scheduling
task launching
job monitoring
```


Your application performs:


```text
MCMC
PT
TCP state exchange
```


Source for course/cluster access conventions in this section:


```text
UFIT Research Computing — Orientation for Courses (Matt Gitzendanner)
plus UFIT-RC docs linked from that orientation
```


## Course allocation mental model


UFIT-RC course orientation states that a course is typically allocated resources such as:


```text
32 cores
256 GB RAM
2 TB Blue storage
GPUs as needed
```


Design and time experiments with those limits. Use resources efficiently.


Support process from the orientation:


```text
support requests should go through the course TA
if the TA cannot solve it, the TA opens the RC support request
```


By using the account you agree to the AUP:


[https://www.rc.ufl.edu/about/policies/](https://www.rc.ufl.edu/about/policies/)


No restricted data on HiPerGator.


New-user / class training entry point:


[https://docs.rc.ufl.edu/training/new_user_training/](https://docs.rc.ufl.edu/training/new_user_training/)


UF docs root:


[https://docs.rc.ufl.edu/](https://docs.rc.ufl.edu/)


## Account, QOS, and Blue path pattern


In the orientation slides, users with a HiPerGator account are told to:


1. make a personal folder under the class Blue space:


```text
/blue/<COURSE_GROUP>/<gatorlink>
```


2. submit jobs with the matching account and QOS:


```bash
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
```


`<COURSE_GROUP>` is the actual course/group account provided by UFIT-RC for your class. The orientation uses `pre1234` only as an example placeholder. Do not invent a group name; use the one assigned to the course.


Investment vs burst QOS (orientation):


```text
Investment QOS:  --qos=<COURSE_GROUP>
Burst QOS:       --qos=<COURSE_GROUP>-b
```


Burst notes from the orientation:


- available when idle resources exist;
- users choose higher priority vs larger pool;
- burst cannot include a GPU;
- 4-day time limit on burst.


Useful UFIT-RC inspection commands from the orientation:


```bash
module load ufrc
slurmInfo
showAllocation
blue_quota
home_quota
squeue --me
qos_to_burst
qos_to_main
```


## Login and storage rules (must follow)


SSH:


```bash
ssh <gatorlink>@hpg.rc.ufl.edu
```


Web interfaces from the orientation:


```text
Open OnDemand:  https://ood.rc.ufl.edu
JupyterHub:     https://jhub.rc.ufl.edu
```


Storage:


```text
/home/<gatorlink>                 40 GB
  - scripts, code, compiled apps
  - DO NOT use for job input/output
  - short snapshots under ~/.snapshot/

/blue/<COURSE_GROUP>/<gatorlink>  class Blue space (2 TB class pool in orientation)
  - ALL job input/output goes here
```


Orientation warnings:


- storage is for research/coursework data only;
- nothing is backed up;
- course accounts are deleted at end of semester.


Login-node policy:


```text
OK on login nodes:
  file management
  job submission / monitoring
  short interactive testing

NOT OK:
  long MCMC runs
  heavy compiles as a substitute for batch jobs
  GPU work on login nodes
```


IDE note from orientation: a remote IDE attached to a login server is still a login server. Follow login limits; no GPUs there. Prefer VS Code Server / Remote Tunnel guidance on UFIT-RC docs when needed.


## Asking SLURM for resources


Before every job, answer:


```text
How many CPUs, and how grouped?
How much RAM?
How long will it run?
How many GPUs (if any)?
What commands will run?
```


Basic script pattern from the orientation (adapt paths/account/QOS):


```bash
#!/bin/sh
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
#SBATCH --cpus-per-task=1
#SBATCH --mem=1gb
#SBATCH --time=00:05:00
#SBATCH --job-name=mcmc_test
#SBATCH --mail-type=ALL
#SBATCH --mail-user=<gatorlink>@ufl.edu
#SBATCH --output=serial_%j.out

pwd; hostname; date
module load python
# put heavy I/O under /blue/<COURSE_GROUP>/<gatorlink>/...
python /blue/<COURSE_GROUP>/<gatorlink>/path/to/script.py
date
```


Threaded single-node pattern:


```bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
```


Multi-task / MPI-style pattern from orientation:


```bash
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
```


Memory:


```text
--mem=1gb
--mem-per-cpu=1gb
use mb or gb
no decimals (use 1500mb, not 1.5gb)
```


Time formats accepted by SLURM (orientation):


```text
120
2:00:00
7-0
7-00:00
7-00:00:00
```


GPU requests:


```bash
#SBATCH --gpus=1
```


Course GPU policy from orientation:


```text
Courses should use ONLY L4 GPUs
See: https://docs.rc.ufl.edu/doc/GPU_Access
```


Submit / monitor:


```bash
sbatch my_job.sh
squeue --me
```


## Software environments


Orientation guidance:


- be careful with `pip install` on HiPerGator (can pollute `~/.local`);
- prefer conda/mamba isolated environments;
- scripts should start with `#!/usr/bin/env python` when appropriate;
- load modules in the job script (`module load ...`) before running.


For this project, Apptainer remains the HPC container target; local OCI development stays on Podman.


## Required video / docs


**CECI/CISM HPC — Introduction to Slurm workload manager**


[https://www.youtube.com/watch?v=QBQmrkVjDE4](https://www.youtube.com/watch?v=QBQmrkVjDE4)


UF scheduling guide:


[https://docs.rc.ufl.edu/quickstart/scheduling/](https://docs.rc.ufl.edu/quickstart/scheduling/)


UF QOS/allocation guide:


[https://docs.rc.ufl.edu/scheduler/qos_limits/](https://docs.rc.ufl.edu/scheduler/qos_limits/)


SLURM official quick start:


[https://slurm.schedmd.com/quickstart.html](https://slurm.schedmd.com/quickstart.html)


---






# 22. Milestone 10 — First HiPerGator Deployment


Do not start with multi-node PT.


Progress in this order, using UFIT-RC orientation conventions:


## Preconditions


```text
ssh <gatorlink>@hpg.rc.ufl.edu
mkdir -p /blue/<COURSE_GROUP>/<gatorlink>/mcmc_runtime
# all job I/O under that Blue path
# every sbatch includes --account and --qos for <COURSE_GROUP>
```


Keep code under `/home` or a checked-out repo path as convenient, but write outputs to Blue.


## Test A — one CPU task


```text
SLURM
→ one Apptainer container
→ one short CRF run via adapter.run_batch(K)
→ outputs on /blue/<COURSE_GROUP>/<gatorlink>/...
```


## Test B — two independent CPU tasks, one node


```text
task 0 → replica 0
task 1 → replica 1
```


No PT yet.


## Test C — two PT replicas, one node


Enable TCP coordinator + temperature exchange.


This isolates SLURM/container issues without adding cross-node networking.


## Test D — two replicas across nodes


Only now test network behavior across HiPerGator nodes.


Measure:


```text
metadata RTT
temperature-assign latency
optional state-transfer latency
bandwidth
exchange pause
```


## Test E — scale replica count


Try within the course allocation:


```text
2
4
8
...
```


but request only the resources actually needed.


Do not automatically allocate all 32 CPUs.


## Example conceptual request


If one replica uses one core:


```bash
#SBATCH --account=<COURSE_GROUP>
#SBATCH --qos=<COURSE_GROUP>
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=16gb
```


If a replica internally uses multiple CPU cores, resource requests must reflect that.


Do not oversubscribe CPUs by launching both many replicas and many multiprocessing children inside every replica without accounting for the product.


For GPUs later: request L4 only for course work, and remember burst QOS cannot include a GPU.


---


# 23. Important Parallelism Decision


You now have potentially **three** levels of parallelism.


## Level 1 — Multiple PT replicas


```text
Replica 0
Replica 1
Replica 2
Replica 3
```


This is your primary distributed level.


## Level 2 — Existing Python multiprocessing of independent chains


Niya's current code can launch multiple independent chains using a process pool.


For the PT runtime, do not automatically wrap a second Pool around every replica.


Decide whether:


```text
one SLURM task = one replica
```


is the cleanest initial model.


It probably is.


## Level 3 — Internal numerical parallelism


SGS/Numba/PyTorch/GPU operations may have their own parallel behavior.


Resource accounting must consider all levels.


For MVP:


> **One process/task per PT replica.**


Use Niya's multiprocessing implementation as a **baseline comparator**, not necessarily as the internal launcher for the distributed PT system.


---






# 24. Fair Benchmark Design


Do not compare:


```text
1 chain × 100,000 iterations
```


against:


```text
8 PT replicas × 100,000 iterations each
```


and claim PT is "better" without accounting for the 8× proposal/model-evaluation budget.


Report at least two views.


## Budget A — Equal total proposals/model evaluations


Example:


```text
baseline:
1 × 80,000


PT:
4 × 20,000
```


if scientifically comparable.


## Budget B — Equal wall-clock time


Ask:


> Under the same elapsed time, which method produces better useful exploration/convergence?






## Also report actual resource usage


```text
CPU cores
GPU count
node count
memory
wall time
total proposal count
```


This keeps the result scientifically honest.


---






# 25. Performance Result Structure


For every benchmark create one structured record:


```json
{
 "experiment_id": "...",
 "git_commit": "...",
 "config_hash": "...",
 "replicas": 4,
 "temperatures": [1.0, 1.5, 2.5, 4.0],
 "iterations_per_replica": 10000,
 "exchange_interval": 100,
 "total_wall_seconds": 0,
 "scientific_compute_seconds": 0,
 "exchange_wait_seconds": 0,
 "serialization_seconds": 0,
 "network_seconds": 0,
 "state_bytes": 0,
 "swap_attempts": 0,
 "swap_accepts": 0,
 "local_acceptance_rate": [],
 "hardware": {},
 "slurm_job_id": null
}
```


Do not rely on console output as the final benchmark record.


---






# 26. GPU Phase — Stretch Goal, Not MVP


The audit found:


- real PyTorch CRF computation;
- CUDA/MPS/CPU device selection;
- no GPU small-scale SGS;
- random-field proposal generation still includes CPU work;
- no explicit GPU ordinal assignment;
- no one-process-per-device policy;
- no CPU/GPU scientific-equivalence tests;
- no useful existing benchmark.


Therefore:


> Do not schedule the GPU phase until the CPU/PT experiment is working.






## GPU validation order


1. Run one CPU CRF fixed-seed baseline.
2. Run one GPU CRF experiment.
3. Compare outputs under defensible numerical tolerance.
4. Profile CPU↔GPU transfers.
5. Determine one process per GPU policy.
6. Test Apptainer GPU exposure.
7. Request one GPU through SLURM.
8. Only then test multiple GPU replicas.






## GPU research question


Keep separate:


```text
Does GPU accelerate the scientific kernel?
```


from:


```text
Does PT state exchange improve sampling?
```


and:


```text
Does the TCP runtime scale?
```


Do not mix all three changes into one benchmark.


---






# 27. Eight-Week Timeline


The dates below are relative. If starting immediately, treat Week 1 as the current project week.


## Week 1 — MCMC mastery + canonical baseline


Study:


- Random Walk Metropolis video
- Metropolis-Hastings video
- `MCMC.py`
- `Topography.py`
- Bakari `T3_LargeScaleChain.ipynb`


Implement:


- canonical import-path guard;
- portable Stancomb-Wills CRF config;
- short fixed-seed CPU baseline;
- structured run metadata.


Deliverables:


```text
docs/scientific_code_walkthrough.md
configs/stancomb_wills_crf_baseline.yaml
results/baseline_cpu/
```


Exit criteria:


- can explain every step of one CRF MCMC iteration;
- can run reproducibly without manual notebook state.


---






## Week 2 — Existing multiprocessing benchmark + PT math


Study:


- Niya `largeScaleChain_multiprocessing.py`
- Ted Pavlic PT video
- EarthByte Bayeslands PT material


Implement:


- repeatable 1/2/N independent-chain baseline harness;
- performance records;
- advisor statistical note.


Deliverables:


```text
docs/baseline_methodology.md
docs/pt_statistical_assumptions.md
results/multiprocessing_baseline/
```


Exit criteria:


- distinguish inter-chain from intra-chain parallelism;
- know exactly what existing multiprocessing already provides;
- PT target/energy question raised and documented.


---






## Week 3 — Batch wrapper + temperature investigation + adapter


Implement:


- adapter skeleton around unchanged `run(n_iter)`;
- `run_batch(K)` + checkpoint/RNG capture;
- `get/set_temperature` plumbing;
- optional export/import helpers;
- regression tests for batch equivalence.


Investigation:


```text
docs/pt_temperature_energy_investigation.md
```


Tests:


```text
run(100) vs run(10)x10
run(K)+checkpoint+run(K) vs run(2K)
fixed seed reproducibility
optional state import recomputes derived loss/residual
```


Deliverables:


```text
MCMC_implementation/adapters/topography_mcmc_adapter.py
MCMC_implementation/workers/replica_worker.py
MCMC_implementation/tests/...
docs/pt_temperature_energy_investigation.md
```


Exit criteria:


- no trajectory regression when batching `run(K)` at `T=1`;
- temperature/energy path is documented;
- no large Niya loop rewrite.


---






## Week 4 — PT correctness without TCP


Study:


- PT swap derivation;
- detailed balance;
- temperature ladder considerations;
- equivalence of temperature-assignment swap vs physical state swap for this implementation.


Implement:


1. toy two/multi-mode PT;
2. Python-only two-replica CRF temperature exchange via adapter;
3. exchange metrics.


Deliverables:


```text
tests/toy_pt/
results/local_python_pt/
```


Exit criteria:


- PT math passes toy validation;
- two CRF replicas can swap temperatures and resume batches correctly.


---






## Week 5 — C++/TCP protocol + local runtime


Study:


- Ozzadar C++ TCP video
- Boost.Asio introduction
- Boost.Asio TCP/IP networking


Implement:


- CMake build;
- coordinator;
- worker connection;
- versioned framing;
- metadata reports (temperature + energy);
- accepted-swap temperature assignment;
- optional state-transfer path;
- persistent sockets;
- error handling.


Benchmark:


```text
metadata RTT
temperature-assign latency
optional 2 MiB / 4 MiB payload path
persistent vs reconnect
```


Deliverables:


```text
cpp_runtime/
docs/wire_protocol.md
results/network_microbenchmarks/
```


Exit criteria:


- repeated local state transfers are correct;
- no packet-boundary assumptions;
- state hashes match sender/receiver.


---






## Week 6 — End-to-end local system + OCI container


Integrate:


```text
Python CRF worker
↔ C++ runtime
↔ Python CRF worker
```


Then containerize CPU path.


Local target:


```text
Podman OCI image
```


Benchmark:


```text
independent baseline
vs
PT + C++/TCP
```


on the same machine/resources.


Optimize only measured bottlenecks.


Deliverables:


```text
Containerfile
scripts/local_...
results/local_end_to_end/
```


Exit criteria:


- two replicas run end to end;
- overhead is decomposed;
- container output matches native baseline.


---






## Week 7 — Apptainer + SLURM + HiPerGator


Study:


- Apptainer HPC video
- Slurm lecture
- UFIT-RC Orientation for Courses (account/QOS/Blue/login rules)
- UF scheduling/QOS documentation


Deploy progressively on HiPerGator using:


```text
ssh <gatorlink>@hpg.rc.ufl.edu
--account=<COURSE_GROUP> --qos=<COURSE_GROUP>
I/O under /blue/<COURSE_GROUP>/<gatorlink>/...
```


Progression:


```text
1 task
2 independent tasks
2 PT tasks same node (temperature exchange)
2 PT tasks multi-node
4+ replicas
```


Capture:


```text
SLURM job ID
allocated nodes
CPU/memory
network timings
temperature-assign timings
optional state-transfer timings
scientific compute time
```


Deliverables:


```text
containers/
slurm/jobs/
results/hipergator/   # on Blue, not /home
docs/hipergator_runbook.md
```


Exit criteria:


- reproducible Apptainer + SLURM run with correct account/QOS;
- job I/O stays on Blue;
- multi-node temperature exchange works;
- resource requests are understood and justified within the course allocation.


---






## Week 8 — Scientific experiment + final analysis


Run controlled experiments varying:


```text
replica count
temperature ladder
exchange interval
```


Compare:


```text
sequential / reference
independent multiprocessing
PT distributed runtime
```


Report:


```text
systems overhead
scaling
swap behavior
MCMC acceptance
scientific convergence/exploration
mass-conservation loss/residual
ensemble diversity
```


If time remains:


```text
single-GPU validation
```


Do not sacrifice the CPU scientific study for GPU scope.


Deliverables:


```text
final benchmark tables
final plots
methods/results notes
poster-ready architecture diagram
reproducibility instructions
```


---






# 28. Suggested Weekly Time Allocation


If research time is limited, prioritize:


```text
35% understanding/scientific validation
35% implementation
20% testing/benchmarking
10% documentation
```


During TCP week:


```text
20% networking study
50% implementation
30% measurement/testing
```


During HiPerGator week:


```text
20% SLURM/Apptainer study
40% deployment
40% benchmark/debugging
```


---






# 29. Videos in Recommended Watch Order


Do not watch all videos before starting. Watch them immediately before the implementation phase that uses the concept.


## Before Week 1


1. **Ben Lambert — An introduction to the Random Walk Metropolis algorithm**
 [https://www.youtube.com/watch?v=U561HGMWjcw](https://www.youtube.com/watch?v=U561HGMWjcw)
2. **Ben Lambert — Metropolis-Hastings / constrained proposals**
 [https://study.sagepub.com/lambert/student-resources/random-walk-metropolis/author-videos](https://study.sagepub.com/lambert/student-resources/random-walk-metropolis/author-videos)






## Before Week 2 / Week 4


1. **Ted Pavlic — Metropolis-Hastings, simulated annealing, parallel tempering**
 [https://www.youtube.com/watch?v=0aPqZH2_03w](https://www.youtube.com/watch?v=0aPqZH2_03w)
2. **EarthByte — Bayeslands MCMC + Parallel Tempering tutorial**
 [https://www.earthbyte.org/bayeslands-resources/](https://www.earthbyte.org/bayeslands-resources/)






## Before Week 5


1. **Ozzadar Dev — TCP Client Server Application | C++**
 [https://www.youtube.com/watch?v=DVMHEDhYEr4](https://www.youtube.com/watch?v=DVMHEDhYEr4)
2. **Richard Thomson — Getting Started with Boost.Asio**
 [https://www.youtube.com/watch?v=XB3uEit5R_Y](https://www.youtube.com/watch?v=XB3uEit5R_Y)
3. **Richard Thomson — TCP/IP Networking with Boost.Asio**
 [https://www.youtube.com/watch?v=tyDWXT8-Ykc](https://www.youtube.com/watch?v=tyDWXT8-Ykc)






## Before Week 7


1. **CECI/CISM HPC — Introduction to Slurm workload manager**
 [https://www.youtube.com/watch?v=QBQmrkVjDE4](https://www.youtube.com/watch?v=QBQmrkVjDE4)
2. **HPC Café — Using Containers on HPC Systems with Apptainer**
 [https://www.fau.tv/series/hpc4fau-nhr-at-fau-s22/92-hpc-cafe-on-2025-06-24-using-containers-on-the-hpc-systems-at-nhr-at-fau-s25](https://www.fau.tv/series/hpc4fau-nhr-at-fau-s22/92-hpc-cafe-on-2025-06-24-using-containers-on-the-hpc-systems-at-nhr-at-fau-s25)


---






# 30. Things You Should Explicitly NOT Build Yet


Until the CPU/PT system works, do not spend project time on:


- rewriting Niya's MCMC loop into a custom `step()` API;


- Kubernetes;
- a web UI;
- automatic dependency detection;
- notebook ingestion;
- multi-user authentication;
- arbitrary scheduler backends;
- dynamic replica autoscaling;
- fault-tolerant distributed consensus;
- MPI rewrite;
- full SGS PT;
- multi-GPU scheduling;
- custom CUDA kernels;
- zero-copy networking;
- RDMA;
- compression unless payload benchmarks justify it.


These are all potential future extensions, not MVP requirements.


---






# 31. Final MVP Definition


The project is a successful MVP when all of the following are true:


- [ ] Canonical Niya CRF implementation runs on Stancomb-Wills prepared data **without rewriting Niya's loop**.
- [ ] Baseline is fixed-seed and reproducible.
- [ ] Existing independent multiprocessing baseline is benchmarked.
- [ ] Statistical meaning of the PT energy/acceptance and temperature effect is documented and approved.
- [ ] Repeated `run(K)` batches match a continuous `run(N)` when RNG/checkpoint state is preserved.
- [ ] Python adapter exposes `run_batch`, energy, temperature, and checkpoint/restore.
- [ ] Optional topography export/import exists for checkpointing/migration (not required for MVP swaps).
- [ ] Toy PT implementation is statistically sane.
- [ ] Two local CRF replicas can exchange **temperatures** and resume.
- [ ] C++/TCP coordinator uses framed persistent connections.
- [ ] Metadata (temperature + energy) is exchanged before any optional large payload.
- [ ] MVP accepted swaps assign temperatures rather than transferring beds.
- [ ] Local network overhead is measured.
- [ ] OCI container works locally.
- [ ] Apptainer image/workflow runs on HiPerGator.
- [ ] SLURM jobs use course `--account/--qos`, write I/O to `/blue/<COURSE_GROUP>/<gatorlink>/`, and avoid login-node compute.
- [ ] Two-replica PT works on HiPerGator.
- [ ] Multi-replica scaling is measured.
- [ ] PT is compared with independent multiprocessing under fair resource/proposal budgets.
- [ ] Results contain both systems metrics and scientific metrics.
- [ ] GPU evaluation is clearly labeled optional unless validated; course GPUs are L4-only if used.


---






# 32. Final Architecture You Should Be Able to Explain From Memory


```text
                        USER / EXPERIMENT CONFIG
                                  │
                                  ▼
                  Stancomb-Wills scientific inputs
                                  │
                                  ▼
                 Niya MCMC (unchanged scientific code)
                        run(n_iter) batches
                                  │
                                  ▼
                    Python Adapter / Wrapper
                  ┌─────────────────────────────┐
                  │ initialize                  │
                  │ run_batch(K)                │
                  │ get_energy                  │
                  │ get/set_temperature         │
                  │ checkpoint / RNG state      │
                  │ optional export/import bed  │
                  └────────────┬────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
         Replica 0          Replica 1          Replica N
          T = 1              T > 1              T >> 1
            │                  │                  │
            └────────────── TCP connections ─────┘
                               │
                               ▼
                      C++/TCP PT Runtime
                  ┌─────────────────────────────┐
                  │ worker registration         │
                  │ exchange scheduling         │
                  │ temperature + energy collect│
                  │ PT swap decision            │
                  │ temperature assignment      │
                  │ optional state transfer     │
                  │ runtime metrics             │
                  └────────────┬────────────────┘
                               │
                        execution backend
                    ┌──────────┴───────────┐
                    ▼                      ▼
                local CPU              HiPerGator
                / Podman OCI              SLURM
                                     --account/--qos
                                     I/O on /blue/...
                                            │
                                         Apptainer
```


You should be able to explain the responsibility of every box without saying that SLURM, TCP, multiprocessing, PT, CUDA, and containers are the same thing.


---






# 33. Immediate Next Actions


Do these before writing C++:


1. Watch the Random Walk Metropolis video.
2. Watch the Metropolis-Hastings video.
3. Read `chain.loss` and document whether it can serve as PT energy.
4. Trace one complete `chain_crf.run` iteration and list every RNG / cache field that must survive between batches.
5. Trace `get_mass_conservation_residual`.
6. Read the large-scale multiprocessing wrapper as a baseline comparator only.
7. Extract Bakari's Stancomb-Wills CRF configuration into a portable config.
8. Run one short fixed-seed canonical CRF baseline (`run(N)`).
9. Prove batch equivalence: `run(K)` chunks totaling `N` vs one `run(N)`.
10. Write `docs/pt_temperature_energy_investigation.md` and get advisor review.


**Start coding here (now):**


```text
1. MCMC_implementation/adapters/topography_mcmc_adapter.py
   - wrap chain_crf
   - run_batch(K) -> existing run(K)
   - checkpoint bed + RNG fields discovered above
   - get_energy / get_temperature / set_temperature stubs

2. MCMC_implementation/tests/test_adapter_batch_equivalence.py
   - fixed-seed continuous vs batched runs

3. Only after batch equivalence + temperature investigation:
   - replica_worker.py
   - toy PT
   - then C++/TCP
```


Do **not** begin by refactoring Niya's internal loop into `step()`.


For HiPerGator access preparation in parallel (non-blocking for adapter work):


```text
ssh <gatorlink>@hpg.rc.ufl.edu
create /blue/<COURSE_GROUP>/<gatorlink>/
confirm sbatch works with --account/--qos
keep job I/O off /home
```


---






# 34. Project Principle


When deciding what to work on, use this order:


```text
scientific correctness
       ↓
reproducibility
       ↓
state correctness
       ↓
PT correctness
       ↓
network correctness
       ↓
container portability
       ↓
distributed execution
       ↓
performance optimization
       ↓
GPU/stretch work
```


A fast distributed system that samples the wrong distribution is not a successful result.


A correct system whose PT improvement is negative can still be a valid and useful research result.

