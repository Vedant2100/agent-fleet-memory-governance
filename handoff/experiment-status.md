# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-09T00:10:57.373114+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v12-42bedd5dbe50.zip](https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v12-42bedd5dbe50.zip).
Google Drive ZIP: https://drive.google.com/file/d/1QxoOFyLM0ptwoj1hAB-pV7eTPSWVJB_9/view?usp=drivesdk
GitHub ZIP: https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v12-42bedd5dbe50.zip
Drive evidence manifest: https://drive.google.com/file/d/1KLKVdcGma-fQEdRXt6yCQnN-5CcF8CrT/view?usp=drivesdk
Bundle SHA-256: `cf6ce6fd8fa0048883f6a22095b0985947372fd3bc567499d68fb552b5763e8f`; size: 4390249 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 9 | 9 | 1 |
| C_RANDOM_MATCHED | 9 | 9 | 1 |
| D_JEV_WRITE | 10 | 10 | 1 |
| E_JEV_WRITE_READ | 9 | 9 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 36 to 37/40 grades.

- `sympy__sympy-9384 / D_JEV_WRITE`: patch applied=True, resolved=False, F2P 0/2, P2P 320/320.

## Validation issues

- missing 3 treatment grades
- sympy__sympy-9384/D_JEV_WRITE: canonical result file missing
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
