#!/usr/bin/env bash
#SBATCH --job-name=fmc-luna-signal
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=3-00:00:00
#SBATCH --export=NONE
#SBATCH --output=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_oracle_signal_%j.out
#SBATCH --error=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_oracle_signal_%j.err

set -euo pipefail
set +x
umask 077

ROOT=/home/csgrad/vbork001/fleet-mem-contextbench
PYTHON=/home/csgrad/vbork001/miniconda3/bin/python
CONTEXTBENCH=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench
TARGETS=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet
SWEEDIT=/home/csgrad/vbork001/benchmarks/SWE-Edit
SWEEDIT_ENV=/home/csgrad/vbork001/.venv-sweedit-run
PYTHON_PREFIX=/home/csgrad/vbork001/miniconda3
WORKER_CONFIG=configs/sweedit_worker.json
ENV_FILE=/home/csgrad/vbork001/chainswe-organizational-knowledge/.env
[[ -x "$PYTHON" && -d "$CONTEXTBENCH" && -f "$TARGETS" && -d "$SWEEDIT" && -x "$SWEEDIT_ENV/bin/python" ]]
[[ -f "$ENV_FILE" && "$(stat -c '%a' "$ENV_FILE")" == 600 ]]
[[ -n "${SLURM_JOB_ID:-}" ]]

set -a
source "$ENV_FILE"
set +a
[[ -n "${OPENAI_API_KEY:-}" ]]

JOB_TMP_BASE="$(realpath "${SLURM_TMPDIR:-/tmp}")"
FS_TYPE="$(findmnt -n -o FSTYPE -T "$JOB_TMP_BASE")"
case "${FS_TYPE,,}" in
  nfs*|lustre*|gpfs*|beegfs*|panfs*|ceph*|cifs*|smb*)
    echo "Refusing non-local Apptainer scratch: $FS_TYPE at $JOB_TMP_BASE" >&2; exit 67;;
esac
JOB_TMP="$JOB_TMP_BASE/fmc-luna-signal-${SLURM_JOB_ID}"
mkdir -m 700 -p "$JOB_TMP/apptainer-cache" "$JOB_TMP/xdg-cache"
export TMPDIR="$JOB_TMP" APPTAINER_TMPDIR="$JOB_TMP" APPTAINER_CACHEDIR="$JOB_TMP/apptainer-cache"
export XDG_CACHE_HOME="$JOB_TMP/xdg-cache" PYTHONDONTWRITEBYTECODE=1

cd "$ROOT"
RUN_ROOT="results/development/oracle-signal-luna-${SLURM_JOB_ID}"
SUMMARY="artifacts/development/luna_oracle_signal_${SLURM_JOB_ID}.json"
"$PYTHON" artifacts/development/run_luna_oracle_signal.py \
  --stage signal \
  --targets-parquet "$TARGETS" \
  --contextbench-root "$CONTEXTBENCH" \
  --job-tmp "$JOB_TMP" \
  --sweedit-root "$SWEEDIT" \
  --sweedit-env "$SWEEDIT_ENV" \
  --python-prefix "$PYTHON_PREFIX" \
  --worker-config "$WORKER_CONFIG" \
  --run-root "$RUN_ROOT" \
  --summary "$SUMMARY"
