"""One-replica-per-process asyncio worker for temperature-exchange PT.

The worker connects outbound to a coordinator and uses four-byte big-endian,
length-prefixed UTF-8 JSON frames. One process may own only one adapter because
the spectral RNG overlay temporarily redirects a NumPy global during MCMC.
"""

from __future__ import annotations

import argparse
import asyncio
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.topography_mcmc_adapter import TopographyMCMCAdapter
from workers.problem_factory import build_replica_chain, science_metadata
from workers.protocol import ProtocolError, read_frame, write_frame


@dataclass(frozen=True)
class ReplicaWorkerConfig:
    replica_id: int
    temperature: float
    coordinator_host: str
    coordinator_port: int
    rng_seed: int = 0
    rf_seed: int = 1
    problem: str = "synthetic"
    data_dir: str | None = None
    sigma_mc: float = 3.0
    rows: int = 24
    cols: int = 24
    resolution: float = 500.0


class ReplicaWorker:
    """Dispatch coordinator commands to one initialized MCMC adapter."""

    def __init__(
        self,
        config: ReplicaWorkerConfig,
        adapter: TopographyMCMCAdapter,
        science: dict[str, Any],
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.science = science
        self._shutdown = False

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown

    def status(self, *, ok: bool = True, message: str | None = None) -> dict[str, Any]:
        metadata = self.adapter.get_metadata()
        attempted = int(metadata["attempted_this_batch"])
        accepted = int(metadata["accepted_this_batch"])
        a_local = (accepted / attempted) if attempted else None
        a_local_cum = (
            metadata["accepted_completed"] / metadata["proposals_completed"]
            if metadata["proposals_completed"]
            else None
        )
        return {
            "type": "STATUS",
            "ok": ok,
            "replica_id": self.config.replica_id,
            "temperature": metadata["temperature"],
            "energy": metadata["energy"],
            "proposals_completed": metadata["proposals_completed"],
            "accepted_completed": metadata["accepted_completed"],
            "accepted_this_batch": accepted,
            "attempted_this_batch": attempted,
            "a_local": a_local,
            "a_local_cumulative": a_local_cum,
            "batches_completed": metadata["batches_completed"],
            "message": message,
        }

    def register_message(self) -> dict[str, Any]:
        return {
            "type": "REGISTER",
            "replica_id": self.config.replica_id,
            "temperature": self.adapter.get_temperature(),
            **self.science,
        }

    async def dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        command = message.get("type")
        try:
            if command == "RUN_BATCH":
                n_iterations = message.get("n_iterations")
                if isinstance(n_iterations, bool) or not isinstance(n_iterations, int) or n_iterations < 2:
                    raise ValueError("n_iterations must be an integer >= 2")
                await asyncio.to_thread(self.adapter.run_batch, n_iterations)
            elif command == "SET_TEMPERATURE":
                temperature = message.get("temperature")
                if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature):
                    raise ValueError("temperature must be a positive number")
                self.adapter.set_temperature(float(temperature))
            elif command == "GET_STATUS":
                pass
            elif command == "SHUTDOWN":
                self._shutdown = True
            else:
                raise ValueError(f"unsupported command: {command!r}")
            return self.status()
        except (TypeError, ValueError, RuntimeError) as exc:
            return self.status(ok=False, message=str(exc))

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await write_frame(writer, self.register_message())
        try:
            while not self._shutdown:
                message = await read_frame(reader)
                if message.get("type") == "REGISTER_ACK":
                    continue
                await write_frame(writer, await self.dispatch(message))
        except (asyncio.IncompleteReadError, ConnectionError, ProtocolError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()


def build_worker(config: ReplicaWorkerConfig) -> ReplicaWorker:
    chain, rf = build_replica_chain(
        config.problem,
        rf_seed=config.rf_seed,
        chain_seed=config.rng_seed,
        data_dir=config.data_dir,
        sigma_mc=config.sigma_mc,
        rows=config.rows,
        cols=config.cols,
        resolution=config.resolution,
    )
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=config.rng_seed, temperature=config.temperature)
    science = science_metadata(
        config.problem,
        chain,
        data_dir=config.data_dir,
        sigma_mc=config.sigma_mc,
    )
    return ReplicaWorker(config, adapter, science)


async def run_worker(config: ReplicaWorkerConfig) -> None:
    worker = build_worker(config)
    reader, writer = await asyncio.open_connection(config.coordinator_host, config.coordinator_port)
    await worker.serve(reader, writer)


def parse_args(argv: list[str] | None = None) -> ReplicaWorkerConfig:
    parser = argparse.ArgumentParser(description="Run one outbound MCMC replica worker.")
    parser.add_argument("--replica-id", required=True, type=int)
    parser.add_argument("--temperature", required=True, type=float)
    parser.add_argument("--coordinator-host", required=True)
    parser.add_argument("--coordinator-port", required=True, type=int)
    parser.add_argument("--rng-seed", type=int, default=0)
    parser.add_argument("--rf-seed", type=int, default=1)
    parser.add_argument("--problem", choices=("synthetic", "stancomb"), default="synthetic")
    parser.add_argument("--data-dir", default=None, help="Stancomb data directory (repo-relative OK)")
    parser.add_argument("--sigma-mc", type=float, default=3.0)
    parser.add_argument("--rows", type=int, default=24, help="Synthetic grid rows")
    parser.add_argument("--cols", type=int, default=24, help="Synthetic grid cols")
    parser.add_argument("--resolution", type=float, default=500.0, help="Synthetic cell size")
    args = parser.parse_args(argv)
    if not math.isfinite(args.temperature) or args.temperature <= 0:
        parser.error("--temperature must be positive")
    if not 1 <= args.coordinator_port <= 65535:
        parser.error("--coordinator-port must be between 1 and 65535")
    if not math.isfinite(args.sigma_mc) or args.sigma_mc <= 0:
        parser.error("--sigma-mc must be positive")
    if args.problem == "stancomb" and not args.data_dir:
        parser.error("--data-dir is required when --problem stancomb")
    return ReplicaWorkerConfig(
        replica_id=args.replica_id,
        temperature=args.temperature,
        coordinator_host=args.coordinator_host,
        coordinator_port=args.coordinator_port,
        rng_seed=args.rng_seed,
        rf_seed=args.rf_seed,
        problem=args.problem,
        data_dir=args.data_dir,
        sigma_mc=args.sigma_mc,
        rows=args.rows,
        cols=args.cols,
        resolution=args.resolution,
    )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(run_worker(parse_args(argv)))


if __name__ == "__main__":
    main()
