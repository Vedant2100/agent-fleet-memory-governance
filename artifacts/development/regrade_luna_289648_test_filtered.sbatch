#!/usr/bin/env bash
#SBATCH --job-name=luna-filtered-regrade
#SBATCH --partition=batch
#SBATCH --array=0-7%8
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --export=ALL
#SBATCH --output=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_filtered_regrade_%A_%a.out
#SBATCH --error=/home/csgrad/vbork001/fleet-mem-contextbench/artifacts/development/luna_filtered_regrade_%A_%a.err

set -euo pipefail
ROOT=/home/csgrad/vbork001/fleet-mem-contextbench
PYTHON=/home/csgrad/vbork001/miniconda3/bin/python
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"

JOB_TMP_BASE="$(realpath "${SLURM_TMPDIR:-/tmp}")"
FS_TYPE="$(findmnt -n -o FSTYPE -T "$JOB_TMP_BASE")"
case "${FS_TYPE,,}" in
  nfs*|lustre*|gpfs*|beegfs*|panfs*|ceph*|cifs*|smb*)
    echo "Refusing non-local Apptainer scratch: $FS_TYPE at $JOB_TMP_BASE" >&2
    exit 67
    ;;
esac

echo "array_task=$SLURM_ARRAY_TASK_ID job=$SLURM_JOB_ID host=$(hostname)"
apptainer --version
"$PYTHON" artifacts/development/regrade_luna_289648_test_filtered.py --task-index "$SLURM_ARRAY_TASK_ID"
