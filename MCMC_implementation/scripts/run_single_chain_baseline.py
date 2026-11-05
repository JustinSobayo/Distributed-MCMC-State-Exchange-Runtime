"""Run from any cwd: python /path/to/run_single_chain_baseline.py --config ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarks.single_chain_baseline import run_baseline  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible single-chain T=1 cold baseline.")
    parser.add_argument("--config", type=Path, required=True, help="Baseline YAML profile")
    parser.add_argument("--output-dir", type=Path, help="Override output directory (relative to repository)")
    args = parser.parse_args(argv)
    try:
        run_baseline(args.config, output_dir=args.output_dir)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.exit(2, f"baseline: {exc}\n")


if __name__ == "__main__":
    main()
