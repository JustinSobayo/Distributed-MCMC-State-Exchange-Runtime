"""Python TCP coordinator for two-replica temperature-exchange PT."""

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
from workers.protocol import ProtocolError, read_frame, write_frame

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class WorkerConn:
    replica_id: int
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    temperature: float


def load_pt_config(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise ValueError("configuration must be a YAML mapping")
    return validate_pt_config(config), raw


def validate_pt_config(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "experiment": {"name": "two_replica_pt", "seed": 1234},
        "science": {
            "problem": "synthetic",
            "backend": "cpu",
            "config": None,
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
        "exchange": {"enabled": True, "pairing": "two_replica"},
        "logging": {"terminal": True, "log_every_rounds": 1},
        "runtime": {
            "coordinator_host": "127.0.0.1",
            "coordinator_port": 5000,
            "round_timeout_seconds": 600,
            "output_dir": "results/two_replica_pt_synthetic",
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
    if science["problem"] != "synthetic" or science["config"] is not None:
        raise ValueError("only problem: synthetic with science.config: null is wired")

    replicas = _int(sampling["replicas"], "sampling.replicas", 2)
    if replicas != 2:
        raise ValueError("MVP coordinator supports exactly sampling.replicas: 2")
    temps = sampling["temperatures"]
    if not isinstance(temps, list) or len(temps) != 2:
        raise ValueError("sampling.temperatures must be a list of length 2")
    temps_f = []
    for i, t in enumerate(temps):
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= 0:
            raise ValueError(f"sampling.temperatures[{i}] must be a positive finite number")
        temps_f.append(float(t))
    sampling["temperatures"] = temps_f
    if exchange["enabled"] and 1.0 not in temps_f:
        raise ValueError("PT mode requires exactly one cold temperature 1.0 in sampling.temperatures")
    if exchange["enabled"] and temps_f.count(1.0) != 1:
        raise ValueError("PT mode requires exactly one temperature equal to 1.0")
    _int(sampling["batch_n_iterations"], "sampling.batch_n_iterations", 2)
    _int(sampling["rounds"], "sampling.rounds", 1)
    _int(sampling["warmup_rounds"], "sampling.warmup_rounds", 0)
    if sampling["warmup_rounds"] > sampling["rounds"]:
        raise ValueError("sampling.warmup_rounds cannot exceed sampling.rounds")

    if not isinstance(exchange["enabled"], bool):
        raise ValueError("exchange.enabled must be a boolean")
    if exchange["pairing"] != "two_replica":
        raise ValueError("only exchange.pairing: two_replica is implemented")

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
    """Synchronous two-replica coordinator: batch barrier → swap decision → assign T."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.rng = np.random.default_rng(config["experiment"]["coordinator_seed"])
        self.workers: dict[int, WorkerConn] = {}
        self._register_event = asyncio.Event()
        self._done_event = asyncio.Event()
        self._client_errors: list[BaseException] = []
        self.round_logs: list[dict[str, Any]] = []
        self.swap_attempts = 0
        self.swap_accepts = 0

    @property
    def ordered_ids(self) -> list[int]:
        return sorted(self.workers)

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
            if len(self.workers) >= 2:
                raise ProtocolError("coordinator already has two replicas")
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not math.isfinite(temperature)
                or temperature <= 0
            ):
                raise ProtocolError("REGISTER.temperature must be a positive number")
            self.workers[replica_id] = WorkerConn(
                replica_id=replica_id,
                reader=reader,
                writer=writer,
                temperature=float(temperature),
            )
            await write_frame(writer, {"type": "REGISTER_ACK", "ok": True})
            if len(self.workers) == 2:
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
        wa, wb = self.workers[ids[0]], self.workers[ids[1]]

        async def run_one(worker: WorkerConn) -> tuple[WorkerConn, dict[str, Any], float]:
            t0 = time.perf_counter()
            status = await self._command(
                worker, {"type": "RUN_BATCH", "n_iterations": n_iterations, "round": round_index}
            )
            return worker, status, (time.perf_counter() - t0) * 1000.0

        t_coord0 = time.perf_counter()
        (wa, status_a, compute_a_ms), (wb, status_b, compute_b_ms) = await asyncio.wait_for(
            asyncio.gather(run_one(wa), run_one(wb)),
            timeout=timeout,
        )
        energy_a = status_a.get("energy")
        energy_b = status_b.get("energy")
        if (
            isinstance(energy_a, bool)
            or not isinstance(energy_a, (int, float))
            or not math.isfinite(energy_a)
            or isinstance(energy_b, bool)
            or not isinstance(energy_b, (int, float))
            or not math.isfinite(energy_b)
        ):
            raise RuntimeError("both workers must report finite energies after RUN_BATCH")

        # Keep batch diagnostics from RUN_BATCH; later SET_TEMPERATURE STATUS
        # replies intentionally leave energy/accept counters unchanged-but-stale.
        batch_a = status_a
        batch_b = status_b
        t_before = [wa.temperature, wb.temperature]

        decision: ExchangeDecision | None = None
        swapped = False
        if self.config["exchange"]["enabled"]:
            u = float(self.rng.random())  # [0, 1)
            decision = decide_temperature_exchange(
                wa.temperature, wb.temperature, float(energy_a), float(energy_b), u
            )
            self.swap_attempts += 1
            if decision.accepted:
                self.swap_accepts += 1
                new_a, new_b = wb.temperature, wa.temperature
                reply_a = await self._command(
                    wa, {"type": "SET_TEMPERATURE", "temperature": new_a}
                )
                reply_b = await self._command(
                    wb, {"type": "SET_TEMPERATURE", "temperature": new_b}
                )
                wa.temperature = float(reply_a["temperature"])
                wb.temperature = float(reply_b["temperature"])
                swapped = True

        t_coord_ms = (time.perf_counter() - t_coord0) * 1000.0
        record = {
            "round": round_index,
            "replica_ids": [wa.replica_id, wb.replica_id],
            "E": [float(energy_a), float(energy_b)],
            "T_before": t_before,
            "T": [wa.temperature, wb.temperature],
            "a_local": [batch_a.get("a_local"), batch_b.get("a_local")],
            "a_local_cumulative": [
                batch_a.get("a_local_cumulative"),
                batch_b.get("a_local_cumulative"),
            ],
            "accepted_this_batch": [
                batch_a.get("accepted_this_batch"),
                batch_b.get("accepted_this_batch"),
            ],
            "attempted_this_batch": [
                batch_a.get("attempted_this_batch"),
                batch_b.get("attempted_this_batch"),
            ],
            "exchange_enabled": self.config["exchange"]["enabled"],
            "swap": swapped,
            "cold_worker": self._cold_worker_id(),
            "t_compute_ms": [compute_a_ms, compute_b_ms],
            "t_coord_ms": t_coord_ms,
        }
        if decision is not None:
            record.update(decision.as_dict())
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
                f"PT coordinator listening on {host}:{bound_port}; waiting for 2 REGISTER frames",
                flush=True,
            )

        try:
            await asyncio.wait_for(self._register_event.wait(), timeout=120.0)
            if self._client_errors:
                raise RuntimeError(f"worker registration failed: {self._client_errors[0]}")
            if len(self.workers) != 2:
                raise RuntimeError(f"expected 2 workers, registered {len(self.workers)}")
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
                    print(
                        f"round={round_index}  E={tuple(record['E'])}  T={tuple(record['T'])}  "
                        f"cold_worker={record['cold_worker']}  "
                        f"a_local={tuple(record['a_local'])}  "
                        f"p_swap={record['p_swap']}  swap={decision}",
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

        summary = {
            "experiment_name": self.config["experiment"]["name"],
            "rounds": self.config["sampling"]["rounds"],
            "exchange_enabled": self.config["exchange"]["enabled"],
            "temperatures_initial": list(self.config["sampling"]["temperatures"]),
            "swap_attempts": self.swap_attempts,
            "swap_accepts": self.swap_accepts,
            "a_swap": (self.swap_accepts / self.swap_attempts) if self.swap_attempts else None,
            "final_temperatures": {
                str(rid): self.workers[rid].temperature for rid in self.ordered_ids
            },
            "cold_worker": self._cold_worker_id(),
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
    parser = argparse.ArgumentParser(description="Run the Python two-replica PT coordinator.")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config, _ = load_pt_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.exit(2, f"pt-coordinator: {exc}\n")
    asyncio.run(run_coordinator(config))


if __name__ == "__main__":
    main()
