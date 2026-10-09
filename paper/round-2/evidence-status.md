# Round 2 evidence status — complete core pilot

- **Source:** frozen v15 archive published in PR #1 at commit `9e98a4ce6f9fd9f86fa550c5b30b1efd3f10c456`.
- **Google Drive ZIP:** https://drive.google.com/file/d/1yHAlOHJSMUvFWKAejrmIPB84oljdZ0sS/view
- **Archive SHA-256:** `260db688e040671dc9f2c7a095573992dc6ceda3b271ebe1852a2e90d19b4586` (independently checked against downloaded 4,571,951-byte archive).
- **Treatment completeness:** 40/40 B–E canonical grades: ten targets per policy. Independently verified the SHA-256 of all 40 archived canonical result JSON files against the treatment results ledger; 40/40 match.
- **A and F:** ten canonical grades each, sourced from the archived test-path-filtered regrade summary. These worker runs were executed separately from B–E.
- **Full matched task resolution:** A 2/10, B 1/10, C 1/10, D 1/10, E 1/10, F 1/10.
- **F2P tests passed:** A 9/48, B 7/48, C 8/48, D 13/48, E 7/48, F 8/48.
- **P2P tests preserved:** A 2145/2145, B–F each 2025/2145. A 120-test regression occurs on `sympy-21309` in B–F but not A.
- **Exposed record counts:** B 30, C 20, D 15, E 1; character/4 token estimates: 9,408; 6,267; 4,752; 315.
- **Source records:** 211 unique cards across eleven histories, 188 across the ten primary histories; 197/211 stored descriptions end with the truncation marker; 211/211 have unknown source-agent outcomes.
- **Selection:** 123/211 admitted; 15 read decisions, one EXPOSE. Related source appears in top-three retrieval for 8/10 targets, is admitted for 2/8 and exposed for 1/8. Six target-level admission rejections are only two unique source decisions.
- **Worker prompt check:** E shows zero memory on 9/10 targets, and those nine task prompts are byte-identical to A's archived prompts. Independent grades sometimes differ nonetheless.
- **G arm:** unrun and outside the amended A–F core. Full core evaluation coverage is not the same as full proposed experiment coverage.

This is a complete **exploratory core pilot**, not evidence that the policy improves resolution or that the manuscript is submission-ready.
