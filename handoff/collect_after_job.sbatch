#!/usr/bin/env bash
#SBATCH --job-name=fleetmem-handoff
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --output=/home/csgrad/vbork001/fleet-mem-evidence/handoff-%j.out
#SBATCH --error=/home/csgrad/vbork001/fleet-mem-evidence/handoff-%j.err

set -euo pipefail

SOURCE=/home/csgrad/vbork001/fleet-mem-contextbench
REPO=/home/csgrad/vbork001/fleet-mem-handoff
OUTPUT=/home/csgrad/vbork001/fleet-mem-evidence
EXPERIMENT_COMMIT=1cedbc0035cb867cfebde398019e313c2a5b02cb

# This job has an afterany dependency on 289898. It reads its outputs only.
python3 "$SOURCE/artifacts/development/build_luna_six_arm_table.py" || true
python3 "$REPO/handoff/collect_evidence.py" \
  --source-root "$SOURCE" --handoff-repo "$REPO" \
  --output-root "$OUTPUT" --job-id 289898 \
  --experiment-commit "$EXPERIMENT_COMMIT"
python3 "$REPO/handoff/publish_github_fallback.py" \
  --output-root "$OUTPUT" --handoff-repo "$REPO"
