"""Python TCP coordinator for N-replica temperature-exchange PT."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from workers.exchange import ExchangeDecision, decide_temperature_exchange
from workers.pairing import neighbor_pairs, pairs_for_config  # noqa: F401
from workers.protocol import ProtocolError, read_frame, write_frame

REPO_ROOT = Path(__file__).resolve().parents[2]

_ALLOWED_PAIRINGS = frozenset({"two_replica", "neighbor_odd_even"})


def _resolve_data_dir(path: str | Path):
    # Lazy import: keeps config validation usable without gstatsim installed.
    from adapters.stancomb_crf import resolve_data_dir

    return resolve_data_dir(path)


def _science_fingerprint(science: dict[str, Any]) -> tuple[Any, ...]:
    from workers.problem_factory import science_fingerprint

    return science_fingerprint(science)


@dataclass
class WorkerConn:
    replica_id: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    temperature: float
    science: dict[str, Any]


def load_pt_config(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise ValueError("configuration must be a YAML mapping")
    return validate_pt_config(config), raw


def validate_pt_config(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "experiment": {"name": "n_replica_pt", "seed": 1234},
        "science": {
            "problem": "synthetic",
            "backend": "cpu",
            "config": None,
            "data_dir": "MCMC_implementation/data",
            "sigma_mc": 3.0,
            "rows": 24,
            "cols": 24,
            "resolution": 500.0,
        },
        "sampling": {
            "replicas": 2,
            "temperatures": [1.0, 2.0],
            "batch_n_iterations": 11,
            "rounds": 5,
            "warmup_rounds": 0,
        },
        "exchange": {"enabled": True, "pairing": "neighbor_odd_even"},
        "logging": {"terminal": True, "log_every_rounds": 1},
        "runtime": {
            "coordinator_host": "127.0.0.1",
            "coordinator_port": 5000,
            "round_timeout_seconds": 600,
            "register_timeout_seconds": 1800,
            "output_dir": "results/n_replica_pt_synthetic",
        },
    }
    unknown = set(config) - set(defaults)
    if unknown:
        raise ValueError(f"unknown configuration sections: {sorted(unknown)}")
    resolved: dict[str, Any] = {}
    for section, values in defaults.items():
        supplied = config.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"{section} must be a mapping")
        allowed = set(values) | ({"rng_seed", "rf_seed", "coordinator_seed"} if section == "experiment" else set())
        if set(supplied) - allowed:
            raise ValueError(f"unknown {section} settings: {sorted(set(supplied) - allowed)}")
        resolved[section] = {**values, **supplied}

    exp = resolved["experiment"]
    science = resolved["science"]
    sampling = resolved["sampling"]
    exchange = resolved["exchange"]
    logging = resolved["logging"]
    runtime = resolved["runtime"]

    seed = _int(exp["seed"], "experiment.seed")
    exp["rng_seed"] = _int(exp.get("rng_seed", seed), "experiment.rng_seed")
    exp["rf_seed"] = _int(exp.get("rf_seed", seed + 1), "experiment.rf_seed")
    exp["coordinator_seed"] = _int(exp.get("coordinator_seed", seed + 99), "experiment.coordinator_seed")
    if not isinstance(exp["name"], str) or not exp["name"].strip():
        raise ValueError("experiment.name must be a nonempty string")

    if science["backend"] not in ("cpu", "cuda"):
        raise ValueError("science.backend must be cpu or cuda")
    if science["backend"] == "cuda":
        raise ValueError("CUDA PT is not wired yet; use backend: cpu")
    if science["config"] is not None:
        raise ValueError("science.config must be null for the shipped builders")
    if science["problem"] not in ("synthetic", "stancomb"):
        raise ValueError("science.problem must be synthetic or stancomb")
    if not isinstance(science["data_dir"], str) or not science["data_dir"].strip():
        raise ValueError("science.data_dir must be a nonempty path")
    sigma_mc = science["sigma_mc"]
    if isinstance(sigma_mc, bool) or not isinstance(sigma_mc, (int, float)) or not math.isfinite(sigma_mc) or sigma_mc <= 0:
        raise ValueError("science.sigma_mc must be a positive finite number")
    science["sigma_mc"] = float(sigma_mc)
    if science["problem"] == "synthetic":
        for axis in ("rows", "cols"):
            _int(science[axis], f"science.{axis}", 8)
        resolution = science["resolution"]
        if (
            isinstance(resolution, bool)
            or not isinstance(resolution, (int, float))
            or not math.isfinite(resolution)
            or resolution <= 0
        ):
            raise ValueError("science.resolution must be positive and finite")
    else:
        data_root = _resolve_data_dir(science["data_dir"])
        if not data_root.is_dir():
            raise ValueError(f"science.data_dir is not a directory: {data_root}")
        csv_path = data_root / "StancombWillsDataGridded.csv"
        bed_path = data_root / "sgs_bed.txt"
        if not csv_path.is_file():
            raise ValueError(f"Stancomb CSV missing under data_dir: {csv_path}")
        if not bed_path.is_file():
            raise ValueError(f"Stancomb sgs_bed.txt missing under data_dir: {bed_path}")
        science["data_dir"] = str(data_root)

    replicas = _int(sampling["replicas"], "sampling.replicas", 2)
    temps = sampling["temperatures"]
    if not isinstance(temps, list) or len(temps) != replicas:
        raise ValueError(
            f"sampling.temperatures must be a list of length sampling.replicas ({replicas})"
        )
    temps_f = []
    for i, t in enumerate(temps):
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= 0:
            raise ValueError(f"sampling.temperatures[{i}] must be a positive finite number")
        temps_f.append(float(t))
    sampling["temperatures"] = temps_f
    if exchange["enabled"] and temps_f.count(1.0) != 1:
        raise ValueError("PT mode requires exactly one temperature equal to 1.0")
    _int(sampling["batch_n_iterations"], "sampling.batch_n_iterations", 2)
    _int(sampling["rounds"], "sampling.rounds", 1)
    _int(sampling["warmup_rounds"], "sampling.warmup_rounds", 0)
    if sampling["warmup_rounds"] > sampling["rounds"]:
        raise ValueError("sampling.warmup_rounds cannot exceed sampling.rounds")

    if not isinstance(exchange["enabled"], bool):
        raise ValueError("exchange.enabled must be a boolean")
    if exchange["pairing"] not in _ALLOWED_PAIRINGS:
        raise ValueError(
            "exchange.pairing must be one of: " + ", ".join(sorted(_ALLOWED_PAIRINGS))
        )
    if exchange["pairing"] == "two_replica" and replicas != 2:
        raise ValueError("exchange.pairing two_replica requires sampling.replicas == 2")

    if not isinstance(logging["terminal"], bool):
        raise ValueError("logging.terminal must be a boolean")
    _int(logging["log_every_rounds"], "logging.log_every_rounds", 1)

    if not isinstance(runtime["coordinator_host"], str) or not runtime["coordinator_host"].strip():
        raise ValueError("runtime.coordinator_host must be a nonempty string")
    port = _int(runtime["coordinator_port"], "runtime.coordinator_port", 0)
    if port > 65535:
        raise ValueError("runtime.coordinator_port must be <= 65535")
    # 0 means "ephemeral": the launcher/coordinator binds an OS-chosen free port.
    if (
        isinstance(runtime["round_timeout_seconds"], bool)
        or not isinstance(runtime["round_timeout_seconds"], (int, float))
        or not math.isfinite(runtime["round_timeout_seconds"])
        or runtime["round_timeout_seconds"] <= 0
    ):
        raise ValueError("runtime.round_timeout_seconds must be positive")
    if (
        isinstance(runtime["register_timeout_seconds"], bool)
        or not isinstance(runtime["register_timeout_seconds"], (int, float))
        or not math.isfinite(runtime["register_timeout_seconds"])
        or runtime["register_timeout_seconds"] <= 0
    ):
        raise ValueError("runtime.register_timeout_seconds must be positive")
    if not isinstance(runtime["output_dir"], str) or not runtime["output_dir"].strip():
        raise ValueError("runtime.output_dir must be a nonempty path")
    return resolved


def _int(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _resolve_output_dir(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (REPO_ROOT / path)


class PTCoordinator:
    """Synchronous N-replica coordinator: batch barrier → neighbor swaps → assign T."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.n_replicas = int(config["sampling"]["replicas"])
        self.rng = np.random.default_rng(config["experiment"]["coordinator_seed"])
        self.workers: dict[int, WorkerConn] = {}
        self._register_event = asyncio.Event()
        self._done_event = asyncio.Event()
        self._client_errors: list[BaseException] = []
        self.round_logs: list[dict[str, Any]] = []
        self.swap_attempts = 0
        self.swap_accepts = 0
        self.swap_attempts_by_edge: dict[str, int] = {}
        self.swap_accepts_by_edge: dict[str, int] = {}

    @property
    def ordered_ids(self) -> list[int]:
        return sorted(self.workers)

    @staticmethod
    def _edge_key(i: int, j: int) -> str:
        return f"{min(i, j)}-{max(i, j)}"

    async def _on_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Accept REGISTER, then park until the experiment finishes.

        After registration, only ``run()`` reads/writes these streams so the
        accept callback and the round loop never race on the same reader.
        """
        peer = writer.get_extra_info("peername")
        try:
            register = await read_frame(reader)
            if register.get("type") != "REGISTER":
                raise ProtocolError(f"expected REGISTER, got {register.get('type')!r}")
            replica_id = register.get("replica_id")
            temperature = register.get("temperature")
            if isinstance(replica_id, bool) or not isinstance(replica_id, int):
                raise ProtocolError("REGISTER.replica_id must be an int")
            if replica_id in self.workers:
                raise ProtocolError(f"duplicate REGISTER for replica_id={replica_id}")
            if replica_id < 0 or replica_id >= self.n_replicas:
                raise ProtocolError(
                    f"REGISTER.replica_id must be in [0, {self.n_replicas - 1}], got {replica_id}"
                )
            if len(self.workers) >= self.n_replicas:
                raise ProtocolError(f"coordinator already has {self.n_replicas} replicas")
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not math.isfinite(temperature)
                or temperature <= 0
            ):
                raise ProtocolError("REGISTER.temperature must be a positive number")
            science = {
                "problem": register.get("problem"),
                "bed_shape": register.get("bed_shape"),
                "data_dir": register.get("data_dir"),
                "sigma_mc": register.get("sigma_mc"),
            }
            if science["problem"] not in ("synthetic", "stancomb"):
                raise ProtocolError("REGISTER.problem must be synthetic or stancomb")
            shape = science["bed_shape"]
            if (
                not isinstance(shape, list)
                or len(shape) != 2
                or any(isinstance(x, bool) or not isinstance(x, int) or x < 1 for x in shape)
            ):
                raise ProtocolError("REGISTER.bed_shape must be [rows, cols] positive ints")
            self.workers[replica_id] = WorkerConn(
                replica_id=replica_id,
                reader=reader,
                writer=writer,
                temperature=float(temperature),
                science=science,
            )
            await write_frame(writer, {"type": "REGISTER_ACK", "ok": True})
            if len(self.workers) == self.n_replicas:
                self._register_event.set()
            await self._done_event.wait()
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError, OSError) as exc:
            self._client_errors.append(exc)
            self._register_event.set()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            if self.config["logging"]["terminal"]:
                print(f"PT coordinator client error from {peer}: {exc}", flush=True)

    async def _command(self, worker: WorkerConn, message: dict[str, Any]) -> dict[str, Any]:
        await write_frame(worker.writer, message)
        reply = await read_frame(worker.reader)
        if reply.get("type") != "STATUS":
            raise RuntimeError(f"expected STATUS from replica {worker.replica_id}, got {reply.get('type')!r}")
        if not reply.get("ok", False):
            raise RuntimeError(
                f"replica {worker.replica_id} reported failure: {reply.get('message')}"
            )
        return reply

    def _assert_matching_science(self) -> dict[str, Any]:
        """Require identical worker science fingerprints matching the YAML problem."""
        workers = [self.workers[rid] for rid in self.ordered_ids]
        fingerprints = [_science_fingerprint(w.science) for w in workers]
        if len(set(fingerprints)) != 1:
            raise RuntimeError(
                "worker science fingerprints disagree: "
                + ", ".join(f"replica {w.replica_id}={w.science}" for w in workers)
            )
        meta = dict(workers[0].science)
        expected_problem = self.config["science"]["problem"]
        if meta["problem"] != expected_problem:
            raise RuntimeError(
                f"workers registered problem={meta['problem']!r} but config has {expected_problem!r}"
            )
        if expected_problem == "stancomb":
            expected_dir = str(_resolve_data_dir(self.config["science"]["data_dir"]))
            expected_sigma = float(self.config["science"]["sigma_mc"])
            if meta.get("data_dir") != expected_dir:
                raise RuntimeError(
                    f"worker data_dir {meta.get('data_dir')!r} != config {expected_dir!r}"
                )
            if meta.get("sigma_mc") != expected_sigma:
                raise RuntimeError(
                    f"worker sigma_mc {meta.get('sigma_mc')!r} != config {expected_sigma!r}"
                )
            if tuple(meta["bed_shape"]) != (500, 500):
                raise RuntimeError(
                    f"Stancomb bed_shape expected [500, 500], got {meta['bed_shape']}"
                )
        return meta

    async def _assign_initial_temperatures(self) -> None:
        temps = list(self.config["sampling"]["temperatures"])
        for replica_id, temperature in zip(self.ordered_ids, temps, strict=True):
            worker = self.workers[replica_id]
            reply = await self._command(
                worker, {"type": "SET_TEMPERATURE", "temperature": temperature}
            )
            worker.temperature = float(reply["temperature"])

    def _cold_worker_id(self) -> int | None:
        cold = [w.replica_id for w in self.workers.values() if abs(w.temperature - 1.0) < 1e-12]
        if len(cold) == 1:
            return cold[0]
        return None

    async def _run_round(self, round_index: int) -> dict[str, Any]:
        n_iterations = self.config["sampling"]["batch_n_iterations"]
        timeout = float(self.config["runtime"]["round_timeout_seconds"])
        ids = self.ordered_ids
        workers = [self.workers[rid] for rid in ids]

        async def run_one(worker: WorkerConn) -> tuple[WorkerConn, dict[str, Any], float]:
            t0 = time.perf_counter()
            status = await self._command(
                worker, {"type": "RUN_BATCH", "n_iterations": n_iterations, "round": round_index}
            )
            return worker, status, (time.perf_counter() - t0) * 1000.0

        t_coord0 = time.perf_counter()
        batch_results = await asyncio.wait_for(
            asyncio.gather(*(run_one(w) for w in workers)),
            timeout=timeout,
        )
        # Preserve ordered_ids order.
        by_id = {w.replica_id: (w, status, compute_ms) for w, status, compute_ms in batch_results}
        ordered = [by_id[rid] for rid in ids]

        energies: list[float] = []
        compute_ms: list[float] = []
        batches: list[dict[str, Any]] = []
        for worker, status, t_ms in ordered:
            energy = status.get("energy")
            if (
                isinstance(energy, bool)
                or not isinstance(energy, (int, float))
                or not math.isfinite(energy)
            ):
                raise RuntimeError(
                    f"replica {worker.replica_id} must report a finite energy after RUN_BATCH"
                )
            energies.append(float(energy))
            compute_ms.append(float(t_ms))
            batches.append(status)

        t_before = [w.temperature for w, _, _ in ordered]
        swap_details: list[dict[str, Any]] = []
        any_accepted = False
        top_decision: ExchangeDecision | None = None

        if self.config["exchange"]["enabled"]:
            pair_idxs = pairs_for_config(
                self.config["exchange"]["pairing"], len(ids), round_index
            )
            for ia, ib in pair_idxs:
                wa, wb = ordered[ia][0], ordered[ib][0]
                u = float(self.rng.random())
                decision = decide_temperature_exchange(
                    wa.temperature,
                    wb.temperature,
                    energies[ia],
                    energies[ib],
                    u,
                )
                edge = self._edge_key(wa.replica_id, wb.replica_id)
                self.swap_attempts += 1
                self.swap_attempts_by_edge[edge] = self.swap_attempts_by_edge.get(edge, 0) + 1
                detail = {
                    "i": wa.replica_id,
                    "j": wb.replica_id,
                    **decision.as_dict(),
                }
                if decision.accepted:
                    self.swap_accepts += 1
                    self.swap_accepts_by_edge[edge] = self.swap_accepts_by_edge.get(edge, 0) + 1
                    new_a, new_b = wb.temperature, wa.temperature
                    reply_a = await self._command(
                        wa, {"type": "SET_TEMPERATURE", "temperature": new_a}
                    )
                    reply_b = await self._command(
                        wb, {"type": "SET_TEMPERATURE", "temperature": new_b}
                    )
                    wa.temperature = float(reply_a["temperature"])
                    wb.temperature = float(reply_b["temperature"])
                    any_accepted = True
                swap_details.append(detail)
                if top_decision is None:
                    top_decision = decision

        t_coord_ms = (time.perf_counter() - t_coord0) * 1000.0
        record: dict[str, Any] = {
            "round": round_index,
            "replica_ids": list(ids),
            "E": energies,
            "T_before": t_before,
            "T": [w.temperature for w, _, _ in ordered],
            "a_local": [b.get("a_local") for b in batches],
            "a_local_cumulative": [b.get("a_local_cumulative") for b in batches],
            "accepted_this_batch": [b.get("accepted_this_batch") for b in batches],
            "attempted_this_batch": [b.get("attempted_this_batch") for b in batches],
            "exchange_enabled": self.config["exchange"]["enabled"],
            "swap": any_accepted,
            "swaps": swap_details,
            "cold_worker": self._cold_worker_id(),
            "t_compute_ms": compute_ms,
            "t_coord_ms": t_coord_ms,
        }
        # N=2 plotter contract: surface the single pair decision at top level.
        if top_decision is not None and len(ids) == 2:
            record.update(top_decision.as_dict())
        elif top_decision is not None:
            # Multi-pair: keep aggregate flags; expose first pair scalars for logs.
            record.update(
                {
                    "log_ratio": top_decision.log_ratio,
                    "p_swap": top_decision.p_swap,
                    "accepted": any_accepted,
                    "u": top_decision.u,
                }
            )
        else:
            record.update({"log_ratio": None, "p_swap": None, "accepted": False, "u": None})
        return record

    async def run(self) -> dict[str, Any]:
        host = self.config["runtime"]["coordinator_host"]
        port = self.config["runtime"]["coordinator_port"]
        output_dir = _resolve_output_dir(self.config["runtime"]["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        server = await asyncio.start_server(self._on_client, host, port)
        sockets = server.sockets or []
        bound_port = sockets[0].getsockname()[1] if sockets else port
        self.config["runtime"]["coordinator_port"] = bound_port
        if self.config["logging"]["terminal"]:
            print(
                f"PT coordinator listening on {host}:{bound_port}; "
                f"waiting for {self.n_replicas} REGISTER frames",
                flush=True,
            )

        try:
            register_timeout = float(self.config["runtime"]["register_timeout_seconds"])
            if self.config["logging"]["terminal"]:
                print(
                    f"PT coordinator waiting up to {register_timeout:.0f}s for "
                    f"{self.n_replicas} REGISTER frames "
                    "(Stancomb chain build can exceed a couple minutes)",
                    flush=True,
                )
            try:
                await asyncio.wait_for(self._register_event.wait(), timeout=register_timeout)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"timed out after {register_timeout:.0f}s waiting for worker REGISTER "
                    f"(got {len(self.workers)}/{self.n_replicas}). Stancomb setup is slow; raise "
                    "runtime.register_timeout_seconds or check worker logs."
                ) from exc
            if self._client_errors:
                raise RuntimeError(f"worker registration failed: {self._client_errors[0]}")
            if len(self.workers) != self.n_replicas:
                raise RuntimeError(
                    f"expected {self.n_replicas} workers, registered {len(self.workers)}"
                )
            missing = [i for i in range(self.n_replicas) if i not in self.workers]
            if missing:
                raise RuntimeError(f"missing REGISTER for replica_id(s): {missing}")
            science_meta = self._assert_matching_science()
            if self.config["logging"]["terminal"]:
                print(
                    f"PT science fingerprint ok: problem={science_meta['problem']} "
                    f"bed_shape={science_meta['bed_shape']} "
                    f"data_dir={science_meta.get('data_dir')} "
                    f"sigma_mc={science_meta.get('sigma_mc')}",
                    flush=True,
                )
            await self._assign_initial_temperatures()
            rounds = self.config["sampling"]["rounds"]
            log_every = self.config["logging"]["log_every_rounds"]
            for round_index in range(rounds):
                record = await self._run_round(round_index)
                self.round_logs.append(record)
                if self.config["logging"]["terminal"] and (
                    round_index % log_every == 0 or round_index + 1 == rounds
                ):
                    decision = "ACCEPT" if record["swap"] else "REJECT"
                    if not record["exchange_enabled"]:
                        decision = "DISABLED"
                    n_pair = len(record.get("swaps") or [])
                    print(
                        f"round={round_index}  E={tuple(record['E'])}  T={tuple(record['T'])}  "
                        f"cold_worker={record['cold_worker']}  "
                        f"a_local={tuple(record['a_local'])}  "
                        f"pairs={n_pair}  p_swap={record['p_swap']}  swap={decision}",
                        flush=True,
                    )

            for worker in self.workers.values():
                await self._command(worker, {"type": "SHUTDOWN"})
        finally:
            self._done_event.set()
            for worker in list(self.workers.values()):
                worker.writer.close()
                try:
                    await worker.writer.wait_closed()
                except Exception:
                    pass
            server.close()
            await server.wait_closed()

        science_meta = {
            rid: self.workers[rid].science for rid in self.ordered_ids
        } if self.workers else {}
        a_swap_by_edge = {
            edge: (self.swap_accepts_by_edge.get(edge, 0) / attempts)
            for edge, attempts in self.swap_attempts_by_edge.items()
            if attempts > 0
        }
        summary = {
            "experiment_name": self.config["experiment"]["name"],
            "rounds": self.config["sampling"]["rounds"],
            "replicas": self.n_replicas,
            "exchange_enabled": self.config["exchange"]["enabled"],
            "exchange_pairing": self.config["exchange"]["pairing"],
            "temperatures_initial": list(self.config["sampling"]["temperatures"]),
            "swap_attempts": self.swap_attempts,
            "swap_accepts": self.swap_accepts,
            "a_swap": (self.swap_accepts / self.swap_attempts) if self.swap_attempts else None,
            "swap_attempts_by_edge": dict(self.swap_attempts_by_edge),
            "swap_accepts_by_edge": dict(self.swap_accepts_by_edge),
            "a_swap_by_edge": a_swap_by_edge,
            "final_temperatures": {
                str(rid): self.workers[rid].temperature for rid in self.ordered_ids
            },
            "cold_worker": self._cold_worker_id(),
            "science": science_meta.get(self.ordered_ids[0]) if self.ordered_ids else None,
            "resolved_config": self.config,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        with (output_dir / "round_metrics.csv").open("w", newline="") as handle:
            if self.round_logs:
                writer = csv.DictWriter(handle, fieldnames=list(self.round_logs[0].keys()))
                writer.writeheader()
                for row in self.round_logs:
                    flat = {
                        key: (json.dumps(value) if isinstance(value, (list, dict)) else value)
                        for key, value in row.items()
                    }
                    writer.writerow(flat)
        (output_dir / "round_metrics.json").write_text(json.dumps(self.round_logs, indent=2) + "\n")
        if self.config["logging"]["terminal"]:
            print(
                f"PT DONE  rounds={summary['rounds']}  swap_attempts={summary['swap_attempts']}  "
                f"a_swap={summary['a_swap']}  output={output_dir}",
                flush=True,
            )
        return summary


async def run_coordinator(config: dict[str, Any]) -> dict[str, Any]:
    return await PTCoordinator(config).run()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Python N-replica PT coordinator.")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config, _ = load_pt_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.exit(2, f"pt-coordinator: {exc}\n")
    asyncio.run(run_coordinator(config))


if __name__ == "__main__":
    main()
