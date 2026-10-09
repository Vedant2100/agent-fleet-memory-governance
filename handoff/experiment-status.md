# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-09T00:36:21.869430+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v14-4b0af188dd98.zip](https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v14-4b0af188dd98.zip).
Google Drive ZIP: https://drive.google.com/file/d/1MPsQyO1-8lCjJGMPrBdoR4IhYYiYTm2G/view?usp=drivesdk
GitHub ZIP: https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v14-4b0af188dd98.zip
Drive evidence manifest: https://drive.google.com/file/d/1I9bDbxhkj3hVUjyPFe9ryaQpDOen8J5_/view?usp=drivesdk
Bundle SHA-256: `4bf0d00359739a1805e8ff771fc51cc1d7ccc58477a39aebb09bfbdf417b8b3b`; size: 4496142 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 10 | 10 | 1 |
| C_RANDOM_MATCHED | 9 | 9 | 1 |
| D_JEV_WRITE | 10 | 10 | 1 |
| E_JEV_WRITE_READ | 10 | 10 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 38 to 39/40 grades.

- `sympy__sympy-9384 / E_JEV_WRITE_READ`: patch applied=True, resolved=False, F2P 0/2, P2P 320/320.

## Validation issues

- missing 1 treatment grades
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
