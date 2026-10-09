# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-08T22:58:12.468364+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip](https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip).
Google Drive ZIP: https://drive.google.com/file/d/1SkUHfJteVDErPT7ejxk_7dRMuYVbps6x/view?usp=drivesdk
GitHub ZIP: https://raw.githubusercontent.com/Vedant2100/agent-fleet-memory-governance/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v5-0e90bb7b8a47.zip
Drive evidence manifest: https://drive.google.com/file/d/1XCUuAz5kBbOBxRclRjFFeaXlIuC6AcHK/view?usp=drivesdk
ZIP SHA-256: `6e5f6532500cb60edc4b1a8383dab6e8028e852fa66e88cb6d1c681e0eaa0ffa`; size 4,109,251 bytes.
Drive ZIP size and SHA-256 verified by downloading and hashing the Drive bytes. The external manifest is 7,313 bytes; its SHA-256 `22b0935e232251ba3685d742bda416096d6110e99d83b5ae04cd8e5f3e936850` also matches the Drive readback.
Slurm job 289898: `RUNNING`; dependent completion watcher 290106 remains queued.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10/10 | 10 | 2 |
| B_SHARE_ALL | 8/10 | 8 | 1 |
| C_RANDOM_MATCHED | 8/10 | 8 | 1 |
| D_JEV_WRITE | 7/10 | 7 | 1 |
| E_JEV_WRITE_READ | 8/10 | 8 | 1 |
| F_ORACLE_RELATED_CEILING | 10/10 | 10 | 1 |
| G_LLM_WRITE | 0/10 | 0 | 0; outside amended A–F core |

New grade: `sympy__sympy-16953 / E_JEV_WRITE_READ`; patch applied, unresolved, F2P 0/11 and P2P 443/443. Total treatment coverage is 31/40; 9 grades remain.

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. The two failed child steps (.5 and .11) are preserved in Slurm accounting. G was listed in the earlier protocol and remains unrun.
