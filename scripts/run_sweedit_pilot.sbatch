#!/usr/bin/env bash
#SBATCH --job-name=fmc-sweedit
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --export=NONE

set -euo pipefail
set +x
umask 077

ROOT="${FMC_PROJECT_ROOT:-${SLURM_SUBMIT_DIR:-}}"
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "Set FMC_PROJECT_ROOT or submit from the project root." >&2; exit 63; }
ROOT="$(cd "$ROOT" && pwd -P)"
: "${FMC_SWEEDIT_STAGE:?Set FMC_SWEEDIT_STAGE to smoke, qualify, or signal}"
: "${FMC_CONTEXTBENCH_ROOT:?Set the pinned clean SWE-ContextBench checkout}"
: "${FMC_TARGETS_PARQUET:?Set the pinned Related_Lite parquet file}"
: "${FMC_OPENAI_ENV_FILE:?Set the protected file that contains OPENAI_API_KEY}"
: "${SLURM_JOB_ID:?Submit this script with sbatch}"

[[ "$FMC_SWEEDIT_STAGE" == "qualify" || "$FMC_SWEEDIT_STAGE" == "smoke" || "$FMC_SWEEDIT_STAGE" == "diagnostic" || "$FMC_SWEEDIT_STAGE" == "diagnostic_resume" || "$FMC_SWEEDIT_STAGE" == "signal" ]] || {
  echo "Unknown FMC_SWEEDIT_STAGE=$FMC_SWEEDIT_STAGE" >&2; exit 64;
}
[[ -f "$FMC_OPENAI_ENV_FILE" && "$(stat -c '%a' "$FMC_OPENAI_ENV_FILE")" == "600" ]] || {
  echo "The OpenAI environment file must exist with mode 600." >&2; exit 65;
}
set -a
source "$FMC_OPENAI_ENV_FILE"
set +a
[[ -n "${OPENAI_API_KEY:-}" ]] || { echo "OPENAI_API_KEY was not loaded." >&2; exit 66; }

PYTHON="${FMC_PYTHON:-/home/csgrad/vbork001/miniconda3/bin/python}"
SWEEDIT_ROOT="${FMC_SWEEDIT_ROOT:-/home/csgrad/vbork001/benchmarks/SWE-Edit}"
SWEEDIT_ENV="${FMC_SWEEDIT_ENV:-/home/csgrad/vbork001/.venv-sweedit-run}"
PYTHON_PREFIX="${FMC_PYTHON_PREFIX:-/home/csgrad/vbork001/miniconda3}"
[[ -x "$PYTHON" && -x "$SWEEDIT_ENV/bin/python" && -d "$SWEEDIT_ROOT" ]] || {
  echo "Pinned experiment Python or SWE-Edit installation is unavailable." >&2; exit 67;
}

JOB_TMP_BASE="${SLURM_TMPDIR:-/tmp}"
JOB_TMP_BASE="$(realpath "$JOB_TMP_BASE")"
case "$JOB_TMP_BASE" in "$ROOT"|"$ROOT"/*) echo "Refusing project filesystem for Apptainer scratch." >&2; exit 68;; esac
FS_TYPE="$(findmnt -n -o FSTYPE -T "$JOB_TMP_BASE")"
case "${FS_TYPE,,}" in nfs*|lustre*|gpfs*|beegfs*|panfs*|ceph*|cifs*|smb*)
  echo "Refusing non-local Apptainer scratch: $FS_TYPE at $JOB_TMP_BASE" >&2; exit 69;; esac
JOB_TMP="$JOB_TMP_BASE/fmc-sweedit-${SLURM_JOB_ID}"
mkdir -m 700 -p "$JOB_TMP/apptainer-cache" "$JOB_TMP/xdg-cache"
export TMPDIR="$JOB_TMP" APPTAINER_TMPDIR="$JOB_TMP" APPTAINER_CACHEDIR="$JOB_TMP/apptainer-cache"
export XDG_CACHE_HOME="$JOB_TMP/xdg-cache" PYTHONDONTWRITEBYTECODE=1

cd "$ROOT"
printf 'stage=%s\njob_id=%s\nhost=%s\nscratch=%s\nfilesystem=%s\n' \
  "$FMC_SWEEDIT_STAGE" "$SLURM_JOB_ID" "$(hostname)" "$JOB_TMP" "$FS_TYPE"
apptainer --version

RUN_ROOT="${FMC_RUN_ROOT:-results/sweedit-pilot/${FMC_SWEEDIT_STAGE}-${SLURM_JOB_ID}}"
WORKER_CONFIG="${FMC_WORKER_CONFIG:-configs/sweedit_worker.json}"
SUMMARY="${FMC_SUMMARY:-artifacts/burned-pilot/sweedit_qualification.json}"
if [[ "$FMC_SWEEDIT_STAGE" == "signal" ]]; then
  SUMMARY="${FMC_SUMMARY:-artifacts/burned-pilot/signal_test.json}"
elif [[ "$FMC_SWEEDIT_STAGE" == "smoke" ]]; then
  SUMMARY="${FMC_SUMMARY:-artifacts/development/worker_smoke.json}"
elif [[ "$FMC_SWEEDIT_STAGE" == "diagnostic" ]]; then
  SUMMARY="${FMC_SUMMARY:-artifacts/development/sol_two_task_diagnostic.json}"
elif [[ "$FMC_SWEEDIT_STAGE" == "diagnostic_resume" ]]; then
  SUMMARY="${FMC_SUMMARY:-artifacts/development/sol_django_resume_289270.json}"
fi
TARGET_ARGS=()
if [[ -n "${FMC_TARGET_IDS:-}" ]]; then
  read -r -a TARGET_IDS <<< "$FMC_TARGET_IDS"
  TARGET_ARGS+=(--target-ids "${TARGET_IDS[@]}")
fi
"$PYTHON" scripts/run_sweedit_burned.py \
  --stage "$FMC_SWEEDIT_STAGE" \
  --targets-parquet "$FMC_TARGETS_PARQUET" \
  --contextbench-root "$FMC_CONTEXTBENCH_ROOT" \
  --job-tmp "$JOB_TMP" \
  --sweedit-root "$SWEEDIT_ROOT" \
  --sweedit-env "$SWEEDIT_ENV" \
  --python-prefix "$PYTHON_PREFIX" \
  --worker-config "$WORKER_CONFIG" \
  --run-root "$RUN_ROOT" \
  --summary "$SUMMARY" \
  "${TARGET_ARGS[@]}"
