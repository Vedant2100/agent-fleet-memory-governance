# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-09T00:24:05.223064+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v13-a16eabd3c02e.zip](https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v13-a16eabd3c02e.zip).
Google Drive ZIP: https://drive.google.com/file/d/1DHS7u1-q0xtUrfRuLaUtd-rcVGyE9mmG/view?usp=drivesdk
GitHub ZIP: https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v13-a16eabd3c02e.zip
Drive evidence manifest: https://drive.google.com/file/d/1Pj6Z3sn2hxTI9HGllegs73yGU-w8ltjf/view?usp=drivesdk
Bundle SHA-256: `9259aab5845a3c2a387d3ea9874225fd8849e026789a52f39d2a012b7e93faaf`; size: 4443207 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 10 | 10 | 1 |
| C_RANDOM_MATCHED | 9 | 9 | 1 |
| D_JEV_WRITE | 10 | 10 | 1 |
| E_JEV_WRITE_READ | 9 | 9 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 37 to 38/40 grades.

- `sympy__sympy-9384 / B_SHARE_ALL`: patch applied=True, resolved=False, F2P 0/2, P2P 320/320.

## Validation issues

- missing 2 treatment grades
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
