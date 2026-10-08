# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-08T23:27:56.310203+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v7-ce0e455b7213.zip](https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v7-ce0e455b7213.zip).
Google Drive ZIP: https://drive.google.com/file/d/1djiMZRkxokdpAqeVrG4Fm7bI6A4N8AXe/view?usp=drivesdk
GitHub ZIP: https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v7-ce0e455b7213.zip
Drive evidence manifest: https://drive.google.com/file/d/18rYXm-EPP15fWyFeXdrXiRrRRQ2UWWlI/view?usp=drivesdk
Bundle SHA-256: `b05ce5effdcf9025ffaef7e132f84f76e8d78e4829e728f0c94f32945dc88b54`; size: 4164168 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 8 | 8 | 1 |
| C_RANDOM_MATCHED | 8 | 8 | 1 |
| D_JEV_WRITE | 8 | 8 | 1 |
| E_JEV_WRITE_READ | 8 | 8 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 31 to 32/40 grades.

- `sympy__sympy-16953 / D_JEV_WRITE`: patch applied=True, resolved=False, F2P 0/11, P2P 443/443.

## Validation issues

- missing 8 treatment grades
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
