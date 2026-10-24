#!/usr/bin/env python3
"""Tiny stdlib TCP coordinator for the HiPerGator outbound-connect smoke test."""

from __future__ import annotations

import argparse
import socket
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Listen for smoke-test worker HELLO messages.")
    parser.add_argument("--port", type=int, default=0, help="TCP port to bind (0 selects one).")
    parser.add_argument("--expect", type=int, default=1, help="Number of workers to accept.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Accept/read timeout in seconds.")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if args.expect < 1:
        parser.error("--expect must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def main() -> int:
    args = parse_args()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", args.port))
            listener.listen(args.expect)
            listener.settimeout(args.timeout)
            host, port = listener.getsockname()
            print(f"COORDINATOR_LISTENING host={host} port={port} expect={args.expect}", flush=True)
            for number in range(1, args.expect + 1):
                connection, peer = listener.accept()
                with connection:
                    connection.settimeout(args.timeout)
                    with connection.makefile("rwb") as stream:
                        hello = stream.readline().decode("utf-8").rstrip("\r\n")
                        if not hello.startswith("HELLO from "):
                            print(f"ERROR invalid HELLO from {peer}: {hello!r}", file=sys.stderr, flush=True)
                            return 1
                        stream.write(b"ACK coordinator\n")
                        stream.flush()
                print(f"COORDINATOR_ACCEPTED client={number}/{args.expect} peer={peer[0]}:{peer[1]} hello={hello}", flush=True)
    except (OSError, TimeoutError) as exc:
        print(f"ERROR coordinator failed: {exc}", file=sys.stderr, flush=True)
        return 1
    print("SMOKE_TEST_COORDINATOR_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
