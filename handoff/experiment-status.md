# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-08T22:58:12.468364+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip](https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip).
Google Drive ZIP: https://drive.google.com/file/d/1SkUHfJteVDErPT7ejxk_7dRMuYVbps6x/view?usp=drivesdk
GitHub ZIP: https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip
Drive evidence manifest: https://drive.google.com/file/d/1XCUuAz5kBbOBxRclRjFFeaXlIuC6AcHK/view?usp=drivesdk
Bundle SHA-256: `6e5f6532500cb60edc4b1a8383dab6e8028e852fa66e88cb6d1c681e0eaa0ffa`; size: 4109251 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.
Treatment coverage is 31/40; 9 grades remain. Newly completed: `sympy__sympy-16953 / E_JEV_WRITE_READ`—patch applied, unresolved, F2P 0/11 and P2P 443/443.
Failed Slurm child steps `.5` and `.11` are retained in the archive and accounting record.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 8 | 8 | 1 |
| C_RANDOM_MATCHED | 8 | 8 | 1 |
| D_JEV_WRITE | 7 | 7 | 1 |
| E_JEV_WRITE_READ | 8 | 8 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Outstanding treatment grades

- `scikit-learn__scikit-learn-13771`: B_SHARE_ALL, C_RANDOM_MATCHED, D_JEV_WRITE, E_JEV_WRITE_READ
- `sympy__sympy-16953`: D_JEV_WRITE
- `sympy__sympy-9384`: B_SHARE_ALL, C_RANDOM_MATCHED, D_JEV_WRITE, E_JEV_WRITE_READ

## Validation issues

- missing 9 treatment grades
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
