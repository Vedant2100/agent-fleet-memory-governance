# Fleet-Mem AAMAS 2027 evidence status

**COLLECTED_COMPLETE**, collected 2026-10-09T00:49:41.120183+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v15-15703d8ecbb6.zip](https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v15-15703d8ecbb6.zip).
Google Drive ZIP: https://drive.google.com/file/d/1yHAlOHJSMUvFWKAejrmIPB84oljdZ0sS/view?usp=drivesdk
GitHub ZIP: https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v15-15703d8ecbb6.zip
Drive evidence manifest: https://drive.google.com/file/d/1PhkVWi1qe3bYcUeq-tTjeD6yZ--D4VBd/view?usp=drivesdk
Bundle SHA-256: `260db688e040671dc9f2c7a095573992dc6ceda3b271ebe1852a2e90d19b4586`; size: 4571951 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `COMPLETED`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 10 | 10 | 1 |
| C_RANDOM_MATCHED | 10 | 10 | 1 |
| D_JEV_WRITE | 10 | 10 | 1 |
| E_JEV_WRITE_READ | 10 | 10 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 39 to 40/40 grades.

- `sympy__sympy-9384 / C_RANDOM_MATCHED`: patch applied=True, resolved=False, F2P 0/2, P2P 320/320.
