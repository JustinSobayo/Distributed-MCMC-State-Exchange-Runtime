#!/usr/bin/env bash
# Sequential Stancomb campaign: 4-cold baseline r2000, then 4-replica PT r2000.
# Ladder: [1.0, 1.01, 1.025, 1.05] (dense cold end; prior T1.35 froze).
# Run from repo root on a compute node with conda env active and >=4 CPUs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

LOG_DIR="${ROOT}/results/campaign_logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/stancomb_long_campaign_${STAMP}.log"

echo "campaign start $(date -Is)  log=${LOG}" | tee -a "$LOG"
echo "hostname=$(hostname)  pwd=${ROOT}" | tee -a "$LOG"

run_one () {
  local label="$1"
  local cfg="$2"
  echo "" | tee -a "$LOG"
  echo "===== START ${label}  $(date -Is) =====" | tee -a "$LOG"
  echo "config=${cfg}" | tee -a "$LOG"
  "${PY:-python}" MCMC_implementation/scripts/run_two_replica_pt.py --config "$cfg" 2>&1 | tee -a "$LOG"
  echo "===== DONE  ${label}  $(date -Is) =====" | tee -a "$LOG"
}

run_one "four_replica_baseline_cold_r2000_T1.05match" \
  "MCMC_implementation/configs/four_replica_stancomb_baseline_cold.yaml"

run_one "four_replica_pt_r2000_T1.05" \
  "MCMC_implementation/configs/four_replica_stancomb_pt.yaml"

echo "" | tee -a "$LOG"
echo "campaign complete $(date -Is)" | tee -a "$LOG"
echo "outputs:" | tee -a "$LOG"
echo "  results/four_replica_stancomb_baseline_cold_r2000_T1.05match" | tee -a "$LOG"
echo "  results/four_replica_stancomb_pt_r2000_T1.05" | tee -a "$LOG"
