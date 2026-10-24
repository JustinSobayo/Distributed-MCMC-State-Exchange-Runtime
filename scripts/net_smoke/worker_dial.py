#!/usr/bin/env python3
"""Tiny stdlib TCP worker for the HiPerGator outbound-connect smoke test."""

from __future__ import annotations

import argparse
import socket
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dial the smoke-test coordinator and exchange HELLO/ACK.")
    parser.add_argument("--host", required=True, help="Coordinator hostname or IP address.")
    parser.add_argument("--port", required=True, type=int, help="Coordinator TCP port.")
    parser.add_argument("--replica-id", required=True, help="Identifier included in the HELLO message.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Connection/read timeout in seconds.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def main() -> int:
    args = parse_args()
    hello = f"HELLO from worker-{args.replica_id}\n".encode("utf-8")
    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as connection:
            connection.settimeout(args.timeout)
            with connection.makefile("rwb") as stream:
                stream.write(hello)
                stream.flush()
                reply = stream.readline().decode("utf-8").rstrip("\r\n")
    except (OSError, TimeoutError) as exc:
        print(f"ERROR worker failed to connect to {args.host}:{args.port}: {exc}", file=sys.stderr, flush=True)
        return 1
    if reply != "ACK coordinator":
        print(f"ERROR unexpected coordinator reply: {reply!r}", file=sys.stderr, flush=True)
        return 1
    print(f"WORKER_ACK host={args.host} port={args.port} replica_id={args.replica_id} reply={reply}", flush=True)
    print("SMOKE_TEST_WORKER_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
