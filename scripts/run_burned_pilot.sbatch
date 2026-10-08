#!/usr/bin/env bash
#SBATCH --job-name=fmc-burned
#SBATCH --partition=gpu
#SBATCH --account=amitroychowdhury
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=48:00:00

set -euo pipefail
umask 077

ROOT="${FMC_PROJECT_ROOT:-${SLURM_SUBMIT_DIR:-}}"
[[ -n "$ROOT" && -d "$ROOT" ]] || {
  echo "FMC_PROJECT_ROOT or SLURM_SUBMIT_DIR must identify the project checkout." >&2
  exit 63
}
ROOT="$(cd "$ROOT" && pwd -P)"
: "${FMC_STAGE:?Set FMC_STAGE to one frozen pilot stage}"
: "${FMC_PYTHON:?Set FMC_PYTHON to the Python with pyarrow and project dependencies}"
: "${FMC_CONTEXTBENCH_ROOT:?Set FMC_CONTEXTBENCH_ROOT to the pinned clean SWE-ContextBench checkout}"
: "${FMC_TARGETS_PARQUET:?Set FMC_TARGETS_PARQUET to the pinned Related_Lite parquet file}"

[[ -n "${SLURM_JOB_ID:-}" ]] || { echo "Run this script through sbatch." >&2; exit 64; }
[[ -x "$FMC_PYTHON" ]] || { echo "FMC_PYTHON is not executable." >&2; exit 65; }
[[ -d "$FMC_CONTEXTBENCH_ROOT" && -f "$FMC_TARGETS_PARQUET" ]] || {
  echo "Pinned ContextBench checkout or target parquet is unavailable." >&2; exit 66;
}

JOB_TMP_BASE="${SLURM_TMPDIR:-/tmp}"
JOB_TMP_BASE="$(realpath "$JOB_TMP_BASE")"
FS_TYPE="$(findmnt -n -o FSTYPE -T "$JOB_TMP_BASE")"
case "${FS_TYPE,,}" in
  nfs*|lustre*|gpfs*|beegfs*|panfs*|ceph*|cifs*|smb*)
    echo "Refusing non-local Apptainer scratch: $FS_TYPE at $JOB_TMP_BASE" >&2; exit 67;;
esac
JOB_TMP="$JOB_TMP_BASE/fmc-${SLURM_JOB_ID}"
mkdir -m 700 -p "$JOB_TMP/apptainer-cache" "$JOB_TMP/xdg-cache"
export TMPDIR="$JOB_TMP"
export APPTAINER_TMPDIR="$JOB_TMP"
export APPTAINER_CACHEDIR="$JOB_TMP/apptainer-cache"
export XDG_CACHE_HOME="$JOB_TMP/xdg-cache"
export PYTHONDONTWRITEBYTECODE=1

cd "$ROOT"
printf 'stage=%s\njob_id=%s\nhost=%s\nscratch=%s\nfilesystem=%s\n' \
  "$FMC_STAGE" "$SLURM_JOB_ID" "$(hostname)" "$JOB_TMP" "$FS_TYPE"
apptainer --version

OLLAMA_PID=""
cleanup() {
  if [[ -n "$OLLAMA_PID" ]]; then
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
    wait "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

start_local_ollama() {
  : "${FMC_OLLAMA_BIN:?Set FMC_OLLAMA_BIN to Ollama 0.34.4}"
  : "${FMC_OLLAMA_MODELS:?Set FMC_OLLAMA_MODELS to the frozen local model store}"
  [[ -x "$FMC_OLLAMA_BIN" && -d "$FMC_OLLAMA_MODELS" ]] || {
    echo "Ollama executable/model store is unavailable." >&2; exit 68;
  }
  export FLEET_MEM_JEV_CONFIG="${FMC_JEV_CONFIG:-$HOME/.config/fleet-mem-contextbench/jev.env}"
  export HOME="${FMC_OLLAMA_HOME:-$JOB_TMP_BASE/fmc-ollama-home-${SLURM_JOB_ID}}"
  mkdir -m 700 -p "$HOME"
  export OLLAMA_MODELS="$FMC_OLLAMA_MODELS"
  export OLLAMA_HOST=127.0.0.1:11434
  export OLLAMA_NO_CLOUD=1
  export OLLAMA_NUM_PARALLEL=1
  export OLLAMA_CONTEXT_LENGTH=16384
  unset OLLAMA_API_KEY OLLAMA_CLOUD_API_KEY
  "$FMC_OLLAMA_BIN" --version
  [[ "$("$FMC_OLLAMA_BIN" --version)" == *0.34.4* ]] || {
    echo "The frozen runtime requires Ollama 0.34.4." >&2; exit 69;
  }
  "$FMC_OLLAMA_BIN" serve >"$JOB_TMP/ollama-server.log" 2>&1 &
  OLLAMA_PID=$!
  for attempt in $(seq 1 90); do
    if "$FMC_PYTHON" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=1).read()' >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$OLLAMA_PID" >/dev/null 2>&1; then
      cat "$JOB_TMP/ollama-server.log" >&2
      echo "Ollama exited before becoming ready." >&2
      exit 70
    fi
    sleep 1
  done
  "$FMC_PYTHON" - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=10) as response:
    version = json.load(response)
if version.get("version") != "0.34.4":
    raise SystemExit(f"Unexpected Ollama server version: {version.get('version')!r}")
PY
}

prepare_mini_wrapper() {
  : "${FMC_MINI_PYTHON:?Set FMC_MINI_PYTHON to the pinned mini-SWE-agent Python interpreter}"
  [[ -x "$FMC_MINI_PYTHON" ]] || {
    echo "FMC_MINI_PYTHON is not executable." >&2; exit 71;
  }
  FMC_MINI_PYTHON="$(cd "$(dirname "$FMC_MINI_PYTHON")" && pwd -P)/$(basename "$FMC_MINI_PYTHON")"
  export FMC_MINI_PYTHON
  FMC_MINI_BIN="$JOB_TMP/mini"
  cat >"$FMC_MINI_BIN" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
: "${FMC_MINI_PYTHON:?FMC_MINI_PYTHON was not passed to the worker}"
exec "$FMC_MINI_PYTHON" -c 'import sys; from minisweagent.run.mini import app; sys.argv = ["mini", *sys.argv[1:]]; app()' "$@"
SH
  chmod 700 "$FMC_MINI_BIN"
  export FMC_MINI_BIN
}

case "$FMC_STAGE" in
  stage-images)
    "$FMC_PYTHON" scripts/stage_burned_pilot_images.py --job-tmp "$JOB_TMP" ;;
  controls)
    CONTROL_ARGS=()
    if [[ -n "${FMC_CONTROL_TARGET_IDS:-}" ]]; then
      IFS=':' read -r -a CONTROL_TARGETS <<< "$FMC_CONTROL_TARGET_IDS"
      CONTROL_ARGS+=(--target-ids "${CONTROL_TARGETS[@]}")
    fi
    "$FMC_PYTHON" scripts/run_burned_controls.py \
      --targets-parquet "$FMC_TARGETS_PARQUET" \
      --contextbench-root "$FMC_CONTEXTBENCH_ROOT" --job-tmp "$JOB_TMP" \
      --output "${FMC_CONTROL_OUTPUT:-results/burned-pilot/controls}" \
      --summary "${FMC_CONTROL_SUMMARY:-artifacts/burned-pilot/controls_summary.json}" \
      "${CONTROL_ARGS[@]}" ;;
  qualify)
    prepare_mini_wrapper
    start_local_ollama
    "$FMC_PYTHON" scripts/run_burned_qualification.py \
      --targets-parquet "$FMC_TARGETS_PARQUET" --contextbench-root "$FMC_CONTEXTBENCH_ROOT" \
      --job-tmp "$JOB_TMP" --mini-bin "$FMC_MINI_BIN" \
      --run-root "${FMC_QUALIFICATION_RUN_ROOT:-results/burned-pilot/qualification}" \
      --summary "${FMC_QUALIFICATION_SUMMARY:-artifacts/burned-pilot/qualification.json}" ;;
  source-jev)
    "$FMC_PYTHON" scripts/run_source_governor.py --governor jev ;;
  write-gate)
    "$FMC_PYTHON" scripts/run_burned_exposure_gate.py --stage write-check ;;
  source-llm)
    start_local_ollama
    "$FMC_PYTHON" scripts/run_source_governor.py --governor llm ;;
  exposure-freeze)
    "$FMC_PYTHON" scripts/run_burned_exposure_gate.py --stage finish ;;
  treatments)
    prepare_mini_wrapper
    start_local_ollama
    "$FMC_PYTHON" scripts/run_burned_experiment.py \
      --targets-parquet "$FMC_TARGETS_PARQUET" --contextbench-root "$FMC_CONTEXTBENCH_ROOT" \
      --job-tmp "$JOB_TMP" --mini-bin "$FMC_MINI_BIN" ;;
  *)
    echo "Unknown FMC_STAGE=$FMC_STAGE" >&2
    exit 64
    ;;
esac
