#!/usr/bin/env python3
"""Normalize FalkorDB timestamp fields to ISO8601 strings."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Tuple, Optional

import redis

from flows.utils import iso_from_epoch_millis, is_isoformat_timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost", help="FalkorDB host (default: localhost)")
    parser.add_argument("--port", type=int, default=6379, help="FalkorDB port (default: 6379)")
    parser.add_argument("--graph", default="graphiti_migration", help="Graph name (default: graphiti_migration)")
    parser.add_argument("--dry-run", action="store_true", help="Report updates without executing them")
    return parser.parse_args()


def connect(host: str, port: int) -> redis.Redis:
    client = redis.Redis(host=host, port=port, decode_responses=True)
    client.ping()
    return client


def convert_epoch(value: Any) -> Tuple[Any, bool]:
    """Convert millisecond epochs to ISO strings when needed."""
    if value is None:
        return value, False
    if isinstance(value, str):
        stripped = value.strip()
        if is_isoformat_timestamp(stripped):
            return stripped, False
        if stripped.isdigit():
            return iso_from_epoch_millis(stripped), True
        return stripped, False
    if isinstance(value, (int, float)):
        return iso_from_epoch_millis(value), True
    return value, False


def update_node(client: redis.Redis, graph: str, node_id: int, payload: str, dry_run: bool) -> None:
    if dry_run:
        print(f"   🔸 [dry-run] MATCH (n) WHERE id(n) = {node_id} SET {payload}")
        return
    query = f"MATCH (n) WHERE id(n) = {node_id} SET {payload} RETURN n.uuid"
    client.execute_command("GRAPH.QUERY", graph, query)


def update_relationship(client: redis.Redis, graph: str, rel_id: int, payload: str, dry_run: bool) -> None:
    if dry_run:
        print(f"   🔸 [dry-run] MATCH ()-[r]->() WHERE id(r) = {rel_id} SET {payload}")
        return
    query = f"MATCH ()-[r]->() WHERE id(r) = {rel_id} SET {payload} RETURN r.uuid"
    client.execute_command("GRAPH.QUERY", graph, query)


def backfill_nodes(client: redis.Redis, graph: str, dry_run: bool) -> Tuple[int, int]:
    query = (
        "MATCH (n) WHERE n.created_at IS NOT NULL OR n.valid_at IS NOT NULL "
        "RETURN id(n), labels(n), n.uuid, n.created_at, n.valid_at"
    )
    result = client.execute_command("GRAPH.QUERY", graph, query)
    rows = result[1] if len(result) > 1 else []
    updated = 0
    examined = len(rows)

    for row in rows:
        node_id, labels, uuid_value, created_at, valid_at = row
        updates = []

        new_created, changed_created = convert_epoch(created_at)
        if changed_created:
            updates.append(f"n.created_at = '{new_created}'")

        new_valid, changed_valid = convert_epoch(valid_at)
        if changed_valid:
            updates.append(f"n.valid_at = '{new_valid}'")

        if updates:
            print(f"🔧 Node {uuid_value or node_id} {labels}: {'; '.join(updates)}")
            update_node(client, graph, node_id, ", ".join(updates), dry_run)
            updated += 1

    return examined, updated


def backfill_relationships(client: redis.Redis, graph: str, dry_run: bool) -> Tuple[int, int]:
    query = (
        "MATCH ()-[r]->() WHERE r.created_at IS NOT NULL OR r.valid_at IS NOT NULL OR r.observed_at IS NOT NULL "
        "RETURN id(r), type(r), r.uuid, r.created_at, r.valid_at, r.observed_at"
    )
    result = client.execute_command("GRAPH.QUERY", graph, query)
    rows = result[1] if len(result) > 1 else []
    updated = 0
    examined = len(rows)

    for row in rows:
        rel_id, rel_type, rel_uuid, created_at, valid_at, observed_at = row
        updates = []

        new_created, changed_created = convert_epoch(created_at)
        if changed_created:
            updates.append(f"r.created_at = '{new_created}'")

        new_valid, changed_valid = convert_epoch(valid_at)
        if changed_valid:
            updates.append(f"r.valid_at = '{new_valid}'")

        new_observed, changed_observed = convert_epoch(observed_at)
        if changed_observed:
            updates.append(f"r.observed_at = '{new_observed}'")

        if updates:
            identifier = rel_uuid or f"id={rel_id}"
            print(f"🔧 Relationship {identifier} [{rel_type}]: {'; '.join(updates)}")
            update_relationship(client, graph, rel_id, ", ".join(updates), dry_run)
            updated += 1

    return examined, updated


def main() -> None:
    args = parse_args()

    try:
        client = connect(args.host, args.port)
    except Exception as exc:  # pragma: no cover - direct feedback for operators
        print(f"❌ Failed to connect to FalkorDB: {exc}")
        sys.exit(1)

    print(f"ℹ️  Connected to FalkorDB at {args.host}:{args.port} (graph: {args.graph})")
    if args.dry_run:
        print("ℹ️  Running in dry-run mode. No updates will be applied.")

    node_examined, node_updated = backfill_nodes(client, args.graph, args.dry_run)
    rel_examined, rel_updated = backfill_relationships(client, args.graph, args.dry_run)

    print("\n📊 Backfill summary:")
    print(f"   Nodes examined: {node_examined}, updated: {node_updated}")
    print(f"   Relationships examined: {rel_examined}, updated: {rel_updated}")


if __name__ == "__main__":
    main()
