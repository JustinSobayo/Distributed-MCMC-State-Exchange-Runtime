from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.protocol import MAX_FRAME_SIZE, ProtocolError, encode_frame, read_frame


def test_frame_round_trip():
    async def run():
        reader = asyncio.StreamReader()
        expected = {"type": "GET_STATUS", "replica_id": 4}
        reader.feed_data(encode_frame(expected))
        reader.feed_eof()
        assert await read_frame(reader) == expected

    asyncio.run(run())


def test_oversized_declared_frame_is_rejected_before_payload_read():
    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!I", MAX_FRAME_SIZE + 1))
        reader.feed_eof()
        with pytest.raises(ProtocolError, match="exceeds maximum"):
            await read_frame(reader)

    asyncio.run(run())
