"""Run the Python PT coordinator: python scripts/run_pt_coordinator.py --config ..."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.pt_coordinator import main  # noqa: E402


if __name__ == "__main__":
    main()
