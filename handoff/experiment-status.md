# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL — PARTIAL**, collected 2026-10-08T23:43:58.789143+00:00.

Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
Evidence bundle: [fleet-mem-aamas-2027-v9-92f648089344.zip](https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v9-92f648089344.zip).
Google Drive ZIP: https://drive.google.com/file/d/1PE3mj3F3geMoUFpoCy1qUe3wAnW0mY60/view?usp=drivesdk
GitHub ZIP: https://github.com/Vedant2100/agent-fleet-memory-governance/raw/refs/heads/handoff/aamas-2027-evidence/handoff/bundles/fleet-mem-aamas-2027-v9-92f648089344.zip
Drive evidence manifest: https://drive.google.com/file/d/1Mffn8TSljnfmcqw-w4kqspBBSNypRRdb/view?usp=drivesdk
Bundle SHA-256: `5f9c7ab36a4774ba3c5eea0266fa870ebf8b67a666e8686f10b1ed681adf35ae`; size: 4247865 bytes.
Drive size verified: True; Drive SHA-256 verified: True.
Slurm job 289898: `RUNNING`.

| Arm | Canonical grades | Applied | Resolved |
| --- | ---: | ---: | ---: |
| A_NO_MEMORY | 10 | 10 | 2 |
| B_SHARE_ALL | 8 | 8 | 1 |
| C_RANDOM_MATCHED | 8 | 8 | 1 |
| D_JEV_WRITE | 9 | 9 | 1 |
| E_JEV_WRITE_READ | 9 | 9 | 1 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |
| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |

This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.

## Latest evidence update

Treatment coverage increased from 33 to 34/40 grades.

- `scikit-learn__scikit-learn-13771 / E_JEV_WRITE_READ`: patch applied=True, resolved=False, F2P 2/5, P2P 18/18.

## Validation issues

- missing 6 treatment grades
- final treatment summary is absent or not COMPLETE with 40 grades
- six-arm paper table is absent
- Slurm job state is RUNNING
