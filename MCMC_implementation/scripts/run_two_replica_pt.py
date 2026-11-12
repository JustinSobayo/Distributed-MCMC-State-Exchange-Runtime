"""Launch coordinator + N outbound workers as separate processes.

Workers must be separate OS processes: the spectral RNG overlay is process-global
and concurrent run_batch calls in one process are unsafe.

Filename kept for backward compatibility; supports sampling.replicas >= 2.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.pt_coordinator import load_pt_config  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _worker_cmd(
    *,
    python: str,
    config: dict,
    replica_id: int,
    temperature: float,
    host: str,
    port: int,
) -> list[str]:
    science = config["science"]
    exp = config["experiment"]
    cmd = [
        python,
        "-m",
        "workers.replica_worker",
        "--replica-id",
        str(replica_id),
        "--temperature",
        str(temperature),
        "--coordinator-host",
        host,
        "--coordinator-port",
        str(port),
        "--rng-seed",
        str(exp["rng_seed"] + replica_id),
        "--rf-seed",
        str(exp["rf_seed"] + replica_id),
        "--problem",
        str(science["problem"]),
        "--sigma-mc",
        str(science["sigma_mc"]),
        "--rows",
        str(science["rows"]),
        "--cols",
        str(science["cols"]),
        "--resolution",
        str(science["resolution"]),
    ]
    if science["problem"] == "stancomb":
        cmd.extend(["--data-dir", str(science["data_dir"])])
    return cmd


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run N-replica Python PT (coord + N workers).")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        config, _raw = load_pt_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.exit(2, f"n-replica-pt: {exc}\n")

    host = config["runtime"]["coordinator_host"]
    port = int(config["runtime"]["coordinator_port"])
    if port == 0:
        port = _free_port()
        config["runtime"]["coordinator_port"] = port

    # Materialize a resolved config so the coordinator process gets the bound port.
    resolved_path = Path(config["runtime"]["output_dir"])
    if not resolved_path.is_absolute():
        resolved_path = _ROOT.parent / resolved_path
    resolved_path.mkdir(parents=True, exist_ok=True)
    resolved_yaml = resolved_path / "resolved_launch_config.yaml"
    resolved_yaml.write_text(yaml.safe_dump(config, sort_keys=False))

    python = sys.executable
    coord_cmd = [
        python,
        str(_ROOT / "scripts" / "run_pt_coordinator.py"),
        "--config",
        str(resolved_yaml),
    ]
    temps = config["sampling"]["temperatures"]
    n_replicas = int(config["sampling"]["replicas"])
    if len(temps) != n_replicas:
        parser.exit(2, f"n-replica-pt: temperatures length {len(temps)} != replicas {n_replicas}\n")
    worker_cmds = [
        _worker_cmd(
            python=python,
            config=config,
            replica_id=replica_id,
            temperature=temperature,
            host=host,
            port=port,
        )
        for replica_id, temperature in enumerate(temps)
    ]

    if config["logging"]["terminal"]:
        print(
            f"n-replica-pt: replicas={n_replicas} problem={config['science']['problem']} "
            f"data_dir={config['science'].get('data_dir')} "
            f"sigma_mc={config['science'].get('sigma_mc')} "
            f"temps={temps} exchange={config['exchange']['enabled']} "
            f"pairing={config['exchange']['pairing']} port={port}",
            flush=True,
        )
        for cmd in worker_cmds:
            print(f"n-replica-pt worker cmd: {' '.join(cmd)}", flush=True)

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_ROOT) if not existing else f"{_ROOT}{os.pathsep}{existing}"

    coord = subprocess.Popen(coord_cmd, cwd=str(_ROOT), env=env)
    time.sleep(0.4)
    workers = [subprocess.Popen(cmd, cwd=str(_ROOT), env=env) for cmd in worker_cmds]
    codes = []
    try:
        codes.append(coord.wait())
        # Stancomb workers may take longer to tear down after SHUTDOWN.
        timeout = 120 if config["science"]["problem"] == "stancomb" else 30
        for proc in workers:
            codes.append(proc.wait(timeout=timeout))
    except subprocess.TimeoutExpired:
        for proc in workers:
            proc.kill()
        coord.kill()
        parser.exit(1, "n-replica-pt: worker shutdown timed out\n")
    if any(code != 0 for code in codes):
        parser.exit(1, f"n-replica-pt: nonzero exit codes {codes}\n")


if __name__ == "__main__":
    main()
