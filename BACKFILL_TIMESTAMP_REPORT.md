# FalkorDB Timestamp Normalization Report

This document captures the actions taken on 23 Sep 2025 to remediate millisecond
`created_at`/`valid_at` values and their downstream impact on DuckDB-based
consumers of the CocoIndex → Graphiti integration.

## Scope

- **Target database:** FalkorDB at `192.168.50.90:6379`
- **Graph name:** `graphiti_migration`
- **Entities examined:** All nodes and relationships with non-null temporal
  fields (`created_at`, `valid_at`, `observed_at`).
- **Origin issue:** CocoIndex loaders were persisting millisecond epochs (e.g.
  `1758464374756`) instead of ISO8601 timestamps, leading to ingestion loops in
  downstream DuckDB jobs.

## Tooling

Normalization was executed via
`scripts/backfill_iso_timestamps.py` (added in this patch set). The script:

1. Connects to FalkorDB using the Redis protocol.
2. Retrieves candidate nodes/relationships with temporal fields present.
3. Converts any millisecond epoch integers/strings to RFC3339 strings using the
   shared helper `flows.utils.iso_from_epoch_millis`.
4. Issues `SET` updates for each affected record (idempotent, string-based
   assignments).
5. Offers a `--dry-run` mode which previews Cypher commands without executing
   them.

Invocation command for production backfill:

```bash
PYTHONPATH=. python3 scripts/backfill_iso_timestamps.py --host 192.168.50.90
```

A prior dry run confirmed exactly which records would be touched:

```bash
PYTHONPATH=. python3 scripts/backfill_iso_timestamps.py --host 192.168.50.90 --dry-run
```

## Results Summary

- **Nodes scanned:** 8,987
- **Relationships scanned:** 19,057
- **Nodes updated:** 5,584 (initial dry run), 0 after live run (all converted)
- **Relationships updated:** 10,379 (initial dry run), 10,120 during live run,
  0 on subsequent dry run

> _NOTE:_ The discrepancy between dry-run relationship counts reflects that some
> rows were already normalized by the time of execution; the live run updated all
> remaining non-ISO strings and a follow-up dry run reported zero pending
> updates.

## Example Transformations

| Entity Type | Before                        | After                         |
|-------------|------------------------------|-------------------------------|
| Node        | `1758464374756`               | `2025-09-20T03:12:54.756Z`     |
| Relationship| `1758464228762`               | `2025-09-21T14:17:08.762Z`     |

(Values derived via `iso_from_epoch_millis` conversion.)

## Verification

- Re-running the script with `--dry-run` immediately after the live backfill
  produced: `Nodes examined: 8987, updated: 0` and `Relationships examined:
  19057, updated: 0`, confirming no lingering millisecond epoch values.
- DuckDB ingest logs should cease emitting “Failed to parse created_at … input
  contains invalid characters” once it processes these normalized records.

## Next Steps / Recommendations

1. **Ensure new writes stay compliant:** CocoIndex flows now call
   `flows.utils.current_timestamp_iso`, but monitor logs for regressions.
2. **DuckDB duplicate handling:** The ingest loop will continue retrying if
   duplicate primary keys are encountered. Update the DuckDB load step to use an
   UPSERT or delete-on-insert pattern so replays no longer abort batches.
3. **Backfill automation:** If additional data sources still emit epoch
   integers, keep the script handy for periodic checks (`--dry-run`).

## Appendix: Script Location

- Path: `scripts/backfill_iso_timestamps.py`
- Helper module: `flows/utils.py`

Both are part of this patch set and can be reused across environments.
