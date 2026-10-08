#!/usr/bin/env bash
#SBATCH --job-name=fmc-luna-treatments
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=3-00:00:00
#SBATCH --export=NONE
#SBATCH --output=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_paper_treatments_%j.out
#SBATCH --error=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_paper_treatments_%j.err

set -euo pipefail
set +x
umask 077

ROOT=/home/csgrad/vbork001/fleet-mem-contextbench
PYTHON=/home/csgrad/vbork001/miniconda3/bin/python
CONTEXTBENCH=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench-luna-regrade-clean2
TARGETS=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet
SWEEDIT=/home/csgrad/vbork001/benchmarks/SWE-Edit
SWEEDIT_ENV=/home/csgrad/vbork001/.venv-sweedit-run
PYTHON_PREFIX=/home/csgrad/vbork001/miniconda3
OPENAI_ENV=/home/csgrad/vbork001/chainswe-organizational-knowledge/.env
JEV_ENV=/home/csgrad/vbork001/.config/fleet-mem-contextbench/jev.env

[[ -x "$PYTHON" && -d "$CONTEXTBENCH" && -f "$TARGETS" && -d "$SWEEDIT" && -x "$SWEEDIT_ENV/bin/python" ]]
[[ -f "$OPENAI_ENV" && "$(stat -c '%a' "$OPENAI_ENV")" == 600 ]]
[[ -f "$JEV_ENV" && ! -L "$JEV_ENV" && "$(stat -c '%a' "$JEV_ENV")" == 600 ]]
[[ -n "${SLURM_JOB_ID:-}" ]]

set -a
source "$OPENAI_ENV"
source "$JEV_ENV"
set +a
[[ -n "${OPENAI_API_KEY:-}" ]]
[[ -n "${TYPESAFE_API_KEY:-}" ]]

JEV_BASE_URL="${TYPESAFE_BASE_URL:-https://api.typesafe.ai}"
JEV_API_HOST="$("$PYTHON" -c 'from urllib.parse import urlparse; import sys; print(urlparse(sys.argv[1]).hostname or "")' "$JEV_BASE_URL")"
[[ -n "$JEV_API_HOST" ]]
getent ahostsv4 "$JEV_API_HOST" >/dev/null || { echo "Jev API DNS preflight failed for $JEV_API_HOST" >&2; exit 68; }
JEV_HTTP_STATUS="$(curl --connect-timeout 10 --max-time 20 -sSI -o /dev/null -w '%{http_code}' "${JEV_BASE_URL%/}/v1/models" || true)"
case "$JEV_HTTP_STATUS" in
  200|401|403|404|405) ;;
  *) echo "Jev API HTTPS preflight failed (HTTP $JEV_HTTP_STATUS) for $JEV_API_HOST" >&2; exit 69;;
esac

JOB_TMP_BASE="$(realpath "${SLURM_TMPDIR:-/tmp}")"
FS_TYPE="$(findmnt -n -o FSTYPE -T "$JOB_TMP_BASE")"
case "${FS_TYPE,,}" in
  nfs*|lustre*|gpfs*|beegfs*|panfs*|ceph*|cifs*|smb*)
    echo "Refusing non-local Apptainer scratch: $FS_TYPE at $JOB_TMP_BASE" >&2; exit 67;;
esac
JOB_TMP="$JOB_TMP_BASE/fmc-luna-treatments-${SLURM_JOB_ID}"
mkdir -m 700 -p "$JOB_TMP/apptainer-cache" "$JOB_TMP/xdg-cache"
export TMPDIR="$JOB_TMP" APPTAINER_TMPDIR="$JOB_TMP" APPTAINER_CACHEDIR="$JOB_TMP/apptainer-cache"
export XDG_CACHE_HOME="$JOB_TMP/xdg-cache" PYTHONDONTWRITEBYTECODE=1
export FLEET_MEM_JEV_CONFIG="$JEV_ENV"
export FMC_JOB_TMP="$JOB_TMP"
export FMC_TARGETS_PARQUET="$TARGETS"
export FMC_CONTEXTBENCH_ROOT="$CONTEXTBENCH"
export FMC_SWEEDIT_ROOT="$SWEEDIT"
export FMC_SWEEDIT_ENV="$SWEEDIT_ENV"
export FMC_PYTHON_PREFIX="$PYTHON_PREFIX"
export FMC_TREATMENT_ATTEMPT=attempt-0003
export FMC_PRIOR_ATTEMPT=attempt-0002
export FMC_REUSE_DECISIONS_FROM=attempt-0002

cd "$ROOT"
"$PYTHON" artifacts/development/run_luna_paper_treatments.py
