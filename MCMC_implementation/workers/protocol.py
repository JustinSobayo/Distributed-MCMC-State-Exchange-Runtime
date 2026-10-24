"""Length-prefixed UTF-8 JSON framing for replica-worker control messages."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

MAX_FRAME_SIZE = 1_048_576
_HEADER = struct.Struct("!I")


class ProtocolError(ValueError):
    """Raised for malformed, non-object, or oversized protocol frames."""


def encode_frame(message: dict[str, Any], *, max_frame_size: int = MAX_FRAME_SIZE) -> bytes:
    """Encode one JSON object with a four-byte big-endian payload length."""
    if not isinstance(message, dict):
        raise ProtocolError("protocol messages must be JSON objects")
    try:
        payload = json.dumps(message, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"message is not JSON serializable: {exc}") from exc
    if len(payload) > max_frame_size:
        raise ProtocolError(f"frame exceeds maximum size of {max_frame_size} bytes")
    return _HEADER.pack(len(payload)) + payload


async def read_frame(reader: asyncio.StreamReader, *, max_frame_size: int = MAX_FRAME_SIZE) -> dict[str, Any]:
    """Read exactly one length-prefixed JSON object from an asyncio stream."""
    header = await reader.readexactly(_HEADER.size)
    (payload_size,) = _HEADER.unpack(header)
    if payload_size > max_frame_size:
        raise ProtocolError(f"frame exceeds maximum size of {max_frame_size} bytes")
    try:
        decoded = json.loads((await reader.readexactly(payload_size)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ProtocolError("protocol messages must be JSON objects")
    return decoded


async def write_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    """Write one frame and wait until it has been handed to the transport."""
    writer.write(encode_frame(message))
    await writer.drain()
