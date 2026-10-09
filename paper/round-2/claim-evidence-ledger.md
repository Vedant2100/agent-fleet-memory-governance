# Round 2 claim-to-evidence ledger

| Manuscript claim | Independently inspected source | Qualification |
| --- | --- | --- |
| 40/40 B–E grades across ten targets | v15 `runtime/results/development/paper-treatments-luna/attempt-0003/treatment_results.jsonl` and 40 per-run `evaluation/canonical_result.json` files | Every recorded canonical digest matched; separate A/F histories remain. |
| A 2/10, B–F 1/10 resolved | A/F `runtime/artifacts/development/luna_oracle_signal_289648_test_filtered_regrade.json`; B–E `treatment_results.jsonl` | Ten common targets; not a causal randomized trial. |
| F2P A 9, B 7, C 8, D 13, E 7, F 8 of 48 | Same canonical grades | Tests are clustered within tasks, not independent samples. |
| P2P A 2145, B–F 2025 of 2145 | Same canonical grades | 120-test loss concentrated on `sympy-21309`; prompt-identical A/E discrepancy. |
| 123/211 source records admitted; one of 15 read decisions EXPOSE | v15 `jev_write_decisions.jsonl`, `jev_read_decisions.jsonl` | These are custom binary Jev API decisions, **not** Jev-Mem's published algorithm. |
| 8/10 related sources retrieved, 2/8 admitted, 1/8 exposed | v15 `relationship_annotations.jsonl`, ten `pools/*.json`, and decision JSONL | Six target-level admission rejections correspond to two distinct source records; annotations do not prove usefulness. |
| 211 cards, 197 truncated, all outcomes unknown | Eleven v15 `runtime/artifacts/smoke/pools/*.json` and `memory_schema.py` | Direct deduplication by memory ID and count of descriptions ending in U+2026; earlier Round 1 critic's 198 count was off by one. |
| Ten target IDs correspond to eight resolving PRs | v15 relationship annotations | Two pairs of SymPy targets share PRs 17526 and 21309. |
| E exposes zero records and has same task prompt as A on 9/10 | Ten E treatment records and archived A/E `worker/task_prompt.txt` | Byte-identical prompts but differing grades demonstrate run-to-run comparability limits. |
| B/C/D/E expose 30/20/15/1 records and 9408/6267/4752/315 estimated tokens | `treatment_results.jsonl` `memory_count` and `memory_tokens_exposed` | Token numbers are character/4 estimates, not tokenizer outputs. |
| All B–E submitted patches lack test-file edits | Forty `worker/prediction.patch` files | Working trees may have test edits; the authoritative prediction patches do not. |
| Custom Jev API binary selector, not Jev-Mem | `source/src/fleet_mem_contextbench/governors/jev_system_one.py` | Uses TypeSafe SDK 0.7.2, model `jev-1.13.0`, custom Choice criteria; no Jev-Mem graph memory/retrieval. |
| No positive-control transfer or independent write/read effect | Experimental arms, archived grades, and missing Share-All+read cell | Must be described as limitations, not measured effects. |

Frozen archive: https://drive.google.com/file/d/1yHAlOHJSMUvFWKAejrmIPB84oljdZ0sS/view ; SHA-256 `260db688e040671dc9f2c7a095573992dc6ceda3b271ebe1852a2e90d19b4586`.
