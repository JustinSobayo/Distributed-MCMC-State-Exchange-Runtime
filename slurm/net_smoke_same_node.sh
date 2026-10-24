#!/bin/bash
#SBATCH --job-name=net_smoke_same_node
#SBATCH --account=gly4930
#SBATCH --qos=gly4930
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=/blue/gly4930/justinsobayo/mcmc_runtime/net_smoke/%x-%j.out

set -euo pipefail

# SLURM copies this script to /var/spool/... so BASH_SOURCE is not the repo path.
# Run sbatch from the repo root so SLURM_SUBMIT_DIR points here.
REPO_ROOT="${SLURM_SUBMIT_DIR:-/blue/gly4930/justinsobayo/mcmc_runtime/Distributed-MCMC-State-Exchange-Runtime}"
SCRIPT_DIR="${REPO_ROOT}/scripts/net_smoke"
HOST="$(hostname)"

srun --nodes=1 --ntasks=1 --exclusive python3 "$SCRIPT_DIR/coord_listen.py" --port 7000 --expect 1 &
COORD_PID=$!
sleep 2
srun --nodes=1 --ntasks=1 --exclusive python3 "$SCRIPT_DIR/worker_dial.py" --host "$HOST" --port 7000 --replica-id 0
wait "$COORD_PID"
