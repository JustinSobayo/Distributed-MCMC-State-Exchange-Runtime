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
from typing import Any

from adapters.topography_mcmc_adapter import TopographyMCMCAdapter, build_synthetic_crf_pair
from workers.protocol import ProtocolError, read_frame, write_frame


@dataclass(frozen=True)
class ReplicaWorkerConfig:
    replica_id: int
    temperature: float
    coordinator_host: str
    coordinator_port: int
    rng_seed: int = 0
    rf_seed: int = 1


class ReplicaWorker:
    """Dispatch coordinator commands to one initialized MCMC adapter."""

    def __init__(self, config: ReplicaWorkerConfig, adapter: TopographyMCMCAdapter) -> None:
        self.config = config
        self.adapter = adapter
        self._shutdown = False

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown

    def status(self, *, ok: bool = True, message: str | None = None) -> dict[str, Any]:
        metadata = self.adapter.get_metadata()
        return {
            "type": "STATUS", "ok": ok, "replica_id": self.config.replica_id,
            "temperature": metadata["temperature"], "energy": metadata["energy"],
            "proposals_completed": metadata["proposals_completed"],
            "batches_completed": metadata["batches_completed"], "message": message,
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
        await write_frame(writer, {"type": "REGISTER", "replica_id": self.config.replica_id,
                                   "temperature": self.adapter.get_temperature()})
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
    chain, rf = build_synthetic_crf_pair(rf_seed=config.rf_seed)
    adapter = TopographyMCMCAdapter()
    adapter.initialize(chain, rf, rng_seed=config.rng_seed, temperature=config.temperature)
    return ReplicaWorker(config, adapter)


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
    args = parser.parse_args(argv)
    if not math.isfinite(args.temperature) or args.temperature <= 0:
        parser.error("--temperature must be positive")
    if not 1 <= args.coordinator_port <= 65535:
        parser.error("--coordinator-port must be between 1 and 65535")
    return ReplicaWorkerConfig(**vars(args))


def main(argv: list[str] | None = None) -> None:
    asyncio.run(run_worker(parse_args(argv)))


if __name__ == "__main__":
    main()
