"""Launch coordinator + two outbound workers as separate processes.

Workers must be separate OS processes: the spectral RNG overlay is process-global
and concurrent run_batch calls in one process are unsafe.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run two-replica Python PT (coord + 2 workers).")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        config, raw = load_pt_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.exit(2, f"two-replica-pt: {exc}\n")

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
    seed = config["experiment"]["rng_seed"]
    rf_seed = config["experiment"]["rf_seed"]
    worker_cmds = []
    for replica_id, temperature in enumerate(temps):
        worker_cmds.append(
            [
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
                str(seed + replica_id),
                "--rf-seed",
                str(rf_seed + replica_id),
            ]
        )

    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    # Ensure MCMC_implementation is importable for `python -m workers.replica_worker`.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_ROOT) if not existing else f"{_ROOT}{__import__('os').pathsep}{existing}"

    coord = subprocess.Popen(coord_cmd, cwd=str(_ROOT), env=env)
    time.sleep(0.4)
    workers = [
        subprocess.Popen(cmd, cwd=str(_ROOT), env=env) for cmd in worker_cmds
    ]
    codes = []
    try:
        codes.append(coord.wait())
        for proc in workers:
            codes.append(proc.wait(timeout=30))
    except subprocess.TimeoutExpired:
        for proc in workers:
            proc.kill()
        coord.kill()
        parser.exit(1, "two-replica-pt: worker shutdown timed out\n")
    if any(code != 0 for code in codes):
        parser.exit(1, f"two-replica-pt: nonzero exit codes {codes}\n")


if __name__ == "__main__":
    main()
