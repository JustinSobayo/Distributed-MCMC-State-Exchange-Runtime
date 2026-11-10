"""Plot a Stancomb single-chain baseline archive into repo-root figures/.

Example:
  python MCMC_implementation/scripts/plot_single_chain_baseline.py \\
    --run-dir benchmarks/20261110_094921_BASELINE_stancomb_single_cold \\
    --output-dir figures
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_REPO = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarks.plot_single_chain_baseline import render_run  # noqa: E402


def _resolve(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (_REPO / path).resolve()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Plot Stancomb single-chain cold baseline diagnostics."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Archive with batch_metrics.csv, summary.json, fingerprint.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO / "figures",
        help="Directory for PNGs/PDFs (default: repo-root figures/)",
    )
    parser.add_argument(
        "--prefix",
        default="stancomb_single_cold",
        help="Output filename prefix",
    )
    args = parser.parse_args(argv)
    try:
        manifest = render_run(
            _resolve(args.run_dir),
            _resolve(args.output_dir),
            prefix=args.prefix,
        )
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        parser.exit(2, f"plot_single_chain_baseline: {exc}\n")
    print(json.dumps({"ok": True, "manifest": manifest["manifest_path"]}, indent=2))
    for key, path in manifest["figures"].items():
        if key.endswith("_png"):
            print(path)


if __name__ == "__main__":
    main()
