#!/bin/bash
#SBATCH --job-name=net_smoke_two_nodes
#SBATCH --account=GLY4930
#SBATCH --qos=GLY4930
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/blue/GLY4930/justinsobayo/mcmc_runtime/net_smoke/%x-%j.out

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/net_smoke" && pwd)"
PORT="${NET_SMOKE_PORT:-7000}"
COORD_HOST="$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)"
WORKER_HOST="$(scontrol show hostnames "$SLURM_JOB_NODELIST" | sed -n '2p')"

srun --nodes=1 --nodelist="$COORD_HOST" --ntasks=1 --exclusive python3 "$SCRIPT_DIR/coord_listen.py" --port "$PORT" --expect 1 &
COORD_PID=$!
sleep 2
srun --nodes=1 --nodelist="$WORKER_HOST" --ntasks=1 --exclusive python3 "$SCRIPT_DIR/worker_dial.py" --host "$COORD_HOST" --port "$PORT" --replica-id 1
wait "$COORD_PID"
