"""
Lightweight SQL migration system — works with both Turso HTTP and SQLite.

Each migration is a (version, description, sql_statements) tuple.
Applied migrations are tracked in a `_migrations` table.
Runs automatically at startup after init_db().
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Migration registry ────────────────────────────────────────────────────
# Append new migrations at the end. NEVER modify or remove existing ones.
# Format: (version, description, [sql_statements])

MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (1, "baseline — create migrations tracking table", [
        """CREATE TABLE IF NOT EXISTS _migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )""",
    ]),
    (2, "add tenant_id indexes on all tables", [
        "CREATE INDEX IF NOT EXISTS idx_orders_tenant ON orders(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_tenant ON supplier_profiles(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_tenant ON catalog_items(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_business_rules_tenant ON business_rules(tenant_id)",
    ]),
    (3, "add order_events index on timestamp for faster history queries", [
        "CREATE INDEX IF NOT EXISTS idx_order_events_ts ON order_events(order_id, timestamp)",
    ]),
]


def _get_applied_versions(client) -> set[int]:
    """Return set of already-applied migration versions."""
    try:
        rs = client.execute("SELECT version FROM _migrations")
        return {r[0] for r in rs.rows}
    except Exception:
        return set()


def run_migrations(client) -> int:
    """Apply pending migrations. Returns number of migrations applied."""
    applied = _get_applied_versions(client)
    count = 0

    for version, description, statements in MIGRATIONS:
        if version in applied:
            continue

        try:
            for sql in statements:
                client.execute(sql)

            now = datetime.now(timezone.utc).isoformat()
            client.execute(
                "INSERT INTO _migrations (version, description, applied_at) VALUES (?, ?, ?)",
                [version, description, now],
            )
            logger.info("Migration %d applied: %s", version, description)
            count += 1
        except Exception as e:
            logger.error("Migration %d failed: %s", version, e)
            break

    return count
