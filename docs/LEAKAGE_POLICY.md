# Leakage and temporal policy

## Firewall

Source extraction and write governance may use only one source task, its source worker trajectory, source-side tool evidence, source-side provenance, and an official source outcome if available. They may not receive a target record or any target-derived feature.

The read governor receives the target's public issue text and the visible shared pool. It does not receive published relationship labels, target patch/test patch, hidden tests, later commits, or target outcomes. Pool membership is determined by repository and strict chronology, never by the relationship table.

Only the offline audit may inspect target reference patches and tests to calculate overlap. These fields stay under `artifacts/.../hidden` and are omitted from the governor payload and public manifest.

## Pair audit fields

The machine-readable audit records target/source IDs, repository, source and target task timestamps, strict chronology, same PR, same commit/base commit where available, source-in-target ancestry (unknown without history), explicit target references to source issue/PR, solution-hint indicators, file/symbol/patch overlap, published relation presence/type availability, source count, environment metadata/control status, leakage risk, stratum, and exact pool/exclusion reason.

The release's relation table has no normalized relation type. We preserve `PUBLISHED_RELATIONSHIP_TYPE_NOT_PROVIDED` and separately record whether its PR URLs match. We do not infer Git ancestry from task order or base-commit strings.

## Primary strata

Apply the following priority to each source-target pair:

1. `ENVIRONMENT_INVALID`: required executable target metadata is missing or a later canonical control fails. A construction-only smoke cannot establish this status.
2. `SAME_PR_OR_CORESOLUTION`: relation metadata shows the same PR.
3. `AMBIGUOUS_CHRONOLOGY`: either timestamp is missing or source timestamp is not strictly earlier.
4. `HIGH_HINT_LEAKAGE`: exact source solution text/identifier appears in public target description/hints, or hidden patch overlap exceeds the frozen threshold.
5. `EXPLICIT_PRIOR_REFERENCE`: the target statement directly names the source issue or PR.
6. `CLEAN_TEMPORAL`: strict earlier timestamp, distinct published PR when linked, and no automatic hint/reference flag.

The automatic solution-hint test requires an exact added source-patch line string in the public target description/hints; a separate patch-overlap threshold flags likely co-solutions. Shared identifiers, files, and symbols are retained as overlap/risk evidence but do not alone make a case leaked. These automatic flags are not semantic proof. Audit flags and unknowns are retained for sensitivity and case-study review; no row is silently deleted.

## Unknown values

Use JSON `null` with a reason when the release does not identify resolved commits, source completion times, Git ancestry, or official source outcomes. Do not replace unavailable evidence with `false`.
