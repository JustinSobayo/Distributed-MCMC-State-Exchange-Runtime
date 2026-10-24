# Parallel tempering: temperature vs energy in Niya's MCMC

## Goal

Decide the minimal change needed so MVP temperature-exchange PT is scientifically meaningful when wrapping `chain_crf.run` / `chain_sgs.run` without rewriting the internal loop into `step()`.

## What the adapter does today

`TopographyMCMCAdapter` stores a replica temperature via `get_temperature` / `set_temperature` and reports energy from Niya's loss arrays after each `run_batch`.

Temperature is not injected into Niya's accept/reject rule; the adapter stores it as replica metadata only.

## Findings in `chain_crf.run` (`MCMC.py` ~1188–1194)

```python
if loss_prev > loss_next:
    acceptance_rate = 1
else:
    acceptance_rate = min(1, np.exp(loss_prev - loss_next))
u = rng.random()
if (u <= acceptance_rate):
    ...
```

- Acceptance is standard Metropolis on total loss (MC + data).
- There is no temperature in the current accept/reject rule; `sigma_mc` / data weights change the loss surface, not a PT schedule.
- Temperature cannot be applied outside the loop: each proposal compares `loss_prev` vs `loss_next` inside `run`.

## MVP decision

**Option A for real PT:** change the else-branch to

`acceptance_rate = min(1, np.exp((loss_prev - loss_next) / T))`

with `T` supplied per replica (adapter `get/set_temperature`), leaving the rest of `run(n_iter)` intact.

**Option B** (metadata-only T) is fine for TCP/wire demos before that one-line science hook exists.

## Status

- Accept site located; preferred science hook is Option A, but it is not implemented because Niya's source is immutable.
- Adapter implements Option B: temperature metadata plus energy reporting.
- A future approved adapter/subclass hook is required for scientifically tempered local acceptance.

## Related reproducibility note

Niya's `spectral_synthesis_field` draws FFT/nugget noise from global `np.random`. That is treated as source-of-truth science code and is **not** edited here.

For adapter checkpoint/batch resume, `adapters/spectral_rng_overlay.py` wraps her function and routes `np.random.normal` through `RF.rng` only during that call. Whether her global-`np.random` choice is scientifically preferred is deferred.

## Related files

- `MCMC_implementation/adapters/topography_mcmc_adapter.py`
- `MCMC_implementation/adapters/spectral_rng_overlay.py`
- `MCMC_implementation/gstatsMCMC/MCMC.py` (`chain_crf.run`, `spectral_synthesis_field`) — unchanged science
- `docs/specification.md` (Gates B/C, temperature-exchange MVP)
