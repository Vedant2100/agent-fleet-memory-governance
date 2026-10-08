# Local worker evidence ledger

**Status:** development record. This ledger does not modify a frozen task,
source card, candidate pool, evaluator, treatment, or Oracle go/no-go rule.
No memory treatment has run.

## Why this ledger exists

The original Luna resolution gate and the later PDA-05 mechanics screen answer
different questions. A model that misses either threshold has not thereby
produced an invalid trajectory. Its patch, submission behavior, patch
applicability, canonical grade, FAIL_TO_PASS result, and PASS_TO_PASS result
remain evidence about the worker configuration.

In particular, a later development screen must not erase or relabel an earlier
Ollama run as if it never occurred. The status in a qualification summary means
only that the model did or did not meet that summary's stated screen.

## Current local evidence

All rows used the frozen three-task qualification order, the fixed SWE-Edit
worker interface, xhigh reasoning setting, and the canonical evaluator.

| Model | Valid upstream `finish` submissions | Graded applicable patches | Canonical task evidence | Screen status | Interpretation retained for selection |
|---|---:|---:|---|---|---|
| `glm-4.7-flash:q4_K_M` | 0/3 | 1/3 | Django: F2P 0/6; P2P 68/166 | PDA-05 did not pass | Its attempted patch and severe regression are retained. The run does not establish reliable submission behavior. |
| `qwen3.6:35b-coding` | 1/3 | 3/3 | SymPy 21309: F2P 1/2, P2P 320/320. Django 34176: F2P 1/6, P2P 154/166. SymPy 16953: F2P 0/11, P2P 443/443. | PDA-05 did not pass | This is the strongest completed Ollama coding evidence so far: two partial fixes and one regression-free partial fix. Its two missing `finish` calls remain an operational risk, not an invalidation of its graded patches. |
| `qwen3.8:27b` | 1/3 | 1/3 | SymPy 21309 could not be canonically applied because it overlapped the frozen test patch. Django 34176: F2P 1/6, P2P 166/166, but no `finish`. SymPy 16953: no patch at the response cap. | PDA-05 did not pass | Retain the partial Django result and the patch-overlap diagnosis. Its only `finish` submission was not canonically applicable, so it has no mechanically valid applicable grade under PDA-05. |
| `laguna-xs-2.1:q4_K_M` | 0/3 | 1/3 | Django 34176: F2P 0/6, P2P 166/166, patch applied but no `finish`. SymPy 21309 had a CUDA illegal-memory-access error; SymPy 16953 had no patch after 100 responses. | PDA-05 did not pass | The Django patch is retained as a real partial trajectory and executable grade. It is not a valid submitted run under the upstream contract. |
| `qwen3-coder-next:q4_K_M` | 0/3 | 0/3 | All three worker attempts timed out after 1,845 s with 12, 2, and 3 API responses and no patch. The 51.7 GB model was run in a 96 GB Slurm job that ended `OUT_OF_MEMORY`. The follow-up job (289555) stopped before inference: Slurm recorded 96 GB despite the script's 192 GB request, and Ollama model pull failed because registry DNS was unavailable. | Infrastructure-limited; no canonical task outcomes | Do not read either attempt as a coding-quality failure. Job 289555 produced no model responses, patches, or task grades. |
| `muse-glimmer:30b` | At least 1 submitted patch; a complete three-task record is unavailable. | 1 canonical applicable grade in the archived pair | SymPy 21309: F2P 1/2, P2P 200/320; Django attempt had no patch. A later SymPy patch was saved but not graded before its job was cancelled. | Development evidence only | Preserve the graded partial result and its 120 P2P nonpasses; do not claim a full qualification. |
| `north-mini-code-1.0:q4_K_M` | No valid finish observed | 0/2 | Repeated local CUDA illegal-memory-access errors interrupted both recorded task attempts; no canonical grades. | Infrastructure-invalid | No coding-quality conclusion. |
| `devstral:24b` | No task attempt | 0/0 | The model pull was interrupted; no worker trajectory or canonical grade exists. | Infrastructure-incomplete | No coding-quality conclusion. |

The underlying machine-readable records are
[`glm_4.7_flash_qualification_289376.json`](../artifacts/development/glm_4.7_flash_qualification_289376.json),
[`qwen3.6_qualification_289376.json`](../artifacts/development/qwen3.6_qualification_289376.json),
[`qwen3.8_qualification_289376.json`](../artifacts/development/qwen3.8_qualification_289376.json),
[`laguna_xs_2.1_qualification_289376.json`](../artifacts/development/laguna_xs_2.1_qualification_289376.json),
[`qwen3_coder_next_qualification_289376.json`](../artifacts/development/qwen3_coder_next_qualification_289376.json),
and the per-task records under
[`results/development/qwen3.8-candidate-289376/`](../results/development/qwen3.8-candidate-289376/).

## How selection remains defensible

The historical gate results remain exactly recorded. Candidate selection for a
development-only Oracle signal pilot must be frozen before that candidate sees
any Oracle memory. It may use this ledger's pre-treatment evidence, including
canonical partial outcomes and reliable use of the upstream submission
contract. It may not use an Oracle or governor outcome to select the worker.

The Oracle pilot itself remains stricter than this development ledger: every
paired target arm must make a valid submission, apply its patch, and receive a
canonical grade before its executable comparison is counted. A failed or
incomplete pair is reported as incomplete rather than as no memory effect.
