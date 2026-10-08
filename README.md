# Fleet-Mem ContextBench

An experimental paper track on cross-worker memory governance using SWE-ContextBench's existing Lite tasks and executable evaluator. The current deliverable is a frozen 10-target primary paired pilot drawn from an unchanged 11-target audit universe. Matplotlib remains in the audit set but is nonprimary because its canonical semantic no-op control resolved. This is not a new task benchmark or a general relation-discovery system.

The experiment separates source-time write admission (`SHARE` / `DO_NOT_SHARE`) from target-time exposure (`EXPOSE` / `WITHHOLD`). The worker's outcome is scored by the unchanged SWE-ContextBench evaluator through Apptainer.

## Frozen pilot

The target set and candidate histories are generated from the pinned SWE-ContextBench Lite inputs. Target-derived audit data is excluded from this source release in accordance with `docs/LEAKAGE_POLICY.md`. The experimental protocol and assignment plan are recorded in `docs/EXPERIMENT_PROTOCOL.md` and `artifacts/burned-pilot/plan.json`. No target or pool replacement is allowed after governor or worker outcomes are observed.

Seven paired arms are preregistered: No Memory, Share-All, size-matched Random, Jev Write, Jev Write+Read, Oracle known-related ceiling, and a source-only deliberative LLM write baseline. The protocol requires evaluator controls and a three-task No-Memory worker qualification before treatment runs. Jev's source decisions are made once per unique candidate and frozen; random admission matches Jev's exact admitted count. All ordinary write arms use the same deterministic three-memory retrieval rule.

## Runtime requirements

- Python 3.11+ and `pyarrow==25.0.1` (`python -m pip install -e '.[test,worker,jev]'`)
- A clean checkout of SWE-ContextBench at the pinned commit in `src/fleet_mem_contextbench/build.py`
- Its pinned Lite parquet files at the revision recorded in `artifacts/smoke/manifests/source_provenance.json`
- Slurm, Apptainer, and the frozen SWE-ContextBench SIFs
- Ollama 0.34.4 with the frozen local worker/governor models
- A configured TypeSafe System One credential for the Jev arms

No Docker daemon is required. The Apptainer adapter substitutes image/container lifecycle calls while invoking the upstream `evaluate_instance` unchanged.

## Reproduce the burned pilot

Commands below assume the project root as the working directory. Keep all SIF downloads, Ollama model files, and worker scratch on the cluster's approved storage. The pilot plan must be regenerated and committed only before any treatment outcome is observed.

```bash
python -m pip install -e '.[test,worker,jev]'
python -m unittest discover -s tests -v
python scripts/freeze_burned_pilot.py
python scripts/configure_jev_credentials.py
```

Submit Apptainer image staging, evaluator controls, qualification, governor decisions, exposure freeze, then the paired treatment job using the commands and cluster variables documented in `docs/EXPERIMENT_PROTOCOL.md`. The source-decision and target-read runners journal each model call and refuse to replay an ambiguous decision. Worker/evaluator runs likewise refuse to replay an interrupted arm.

## Scope and reporting

The pilot reports per-target decisions and exposures, executable outcomes, FAIL_TO_PASS and PASS_TO_PASS, positive and negative transfer, preserved success and persistent failure, worker/context tokens, tool calls, latency, and governor costs. It ends with a stop/continue recommendation for a later study; completing this pilot does not authorize or launch the main study.

See [the experimental protocol](docs/EXPERIMENT_PROTOCOL.md), [design](docs/DESIGN.md), [leakage policy](docs/LEAKAGE_POLICY.md), [dataset card](docs/DATASET_CARD.md), and [prior-repository lessons](docs/PRIOR_REPO_LESSONS.md).
