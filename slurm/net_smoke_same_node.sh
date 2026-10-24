#!/bin/bash
#SBATCH --job-name=net_smoke_same_node
#SBATCH --account=GLY4930
#SBATCH --qos=GLY4930
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/blue/GLY4930/justinsobayo/mcmc_runtime/net_smoke/%x-%j.out

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/net_smoke" && pwd)"
HOST="$(hostname)"
PORT="${NET_SMOKE_PORT:-7000}"

srun --nodes=1 --ntasks=1 --exclusive python3 "$SCRIPT_DIR/coord_listen.py" --port "$PORT" --expect 1 &
COORD_PID=$!
sleep 2
srun --nodes=1 --ntasks=1 --exclusive python3 "$SCRIPT_DIR/worker_dial.py" --host "$HOST" --port "$PORT" --replica-id 0
wait "$COORD_PID"
