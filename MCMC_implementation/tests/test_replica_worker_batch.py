from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.protocol import read_frame, write_frame
from workers.replica_worker import ReplicaWorkerConfig, run_worker


def test_worker_outbound_batch_temperature_and_shutdown_round_trip():
    async def run():
        received_register = asyncio.get_running_loop().create_future()
        completed = asyncio.get_running_loop().create_future()

        async def coordinator(reader, writer):
            try:
                received_register.set_result(await read_frame(reader))
                await write_frame(writer, {"type": "REGISTER_ACK", "ok": True})
                await write_frame(writer, {"type": "GET_STATUS"})
                initial = await read_frame(reader)
                await write_frame(writer, {"type": "RUN_BATCH", "n_iterations": 3})
                after_batch = await read_frame(reader)
                await write_frame(writer, {"type": "SET_TEMPERATURE", "temperature": 2.0})
                after_temperature = await read_frame(reader)
                await write_frame(writer, {"type": "SHUTDOWN"})
                shutdown = await read_frame(reader)
                completed.set_result((initial, after_batch, after_temperature, shutdown))
            except Exception as exc:
                if not completed.done():
                    completed.set_exception(exc)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(coordinator, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        worker = asyncio.create_task(run_worker(ReplicaWorkerConfig(
            replica_id=7, temperature=1.0, coordinator_host="127.0.0.1",
            coordinator_port=port, rng_seed=7, rf_seed=8,
        )))
        try:
            register = await asyncio.wait_for(received_register, timeout=10)
            results = await asyncio.wait_for(completed, timeout=60)
            await asyncio.wait_for(worker, timeout=10)
        finally:
            server.close()
            await server.wait_closed()
            if not worker.done():
                worker.cancel()

        initial, after_batch, after_temperature, shutdown = results
        assert register == {"type": "REGISTER", "replica_id": 7, "temperature": 1.0}
        assert initial["ok"] and initial["energy"] is None
        assert after_batch["ok"] and after_batch["energy"] is not None
        assert after_batch["proposals_completed"] == 2
        assert after_temperature["temperature"] == 2.0
        assert shutdown["ok"]

    asyncio.run(run())
