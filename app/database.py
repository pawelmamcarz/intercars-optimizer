"""
Database layer — Turso (libsql) with graceful fallback.

When TURSO_DATABASE_URL is set → uses cloud SQLite via libsql.
When not set → DB_AVAILABLE=False, app falls back to in-memory demo data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional import — libsql may not be installed
# ---------------------------------------------------------------------------
try:
    import libsql  # type: ignore

    _LIBSQL_INSTALLED = True
except ImportError:
    _LIBSQL_INSTALLED = False

DB_AVAILABLE = bool(settings.turso_database_url) and _LIBSQL_INSTALLED


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _connect():
    """Create a new libsql connection."""
    if not DB_AVAILABLE:
        raise RuntimeError("Database not configured")

    kwargs = {}
    if settings.turso_auth_token:
        kwargs["auth_token"] = settings.turso_auth_token

    return libsql.connect(settings.turso_database_url, **kwargs)


def get_db():
    """FastAPI Dependency — yields a DB connection or None."""
    if not DB_AVAILABLE:
        yield None
        return
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    name TEXT NOT NULL,
    unit_cost REAL NOT NULL,
    logistics_cost REAL NOT NULL DEFAULT 0,
    lead_time_days REAL NOT NULL,
    compliance_score REAL NOT NULL,
    esg_score REAL NOT NULL,
    min_order_qty REAL NOT NULL DEFAULT 0,
    max_capacity REAL NOT NULL,
    served_regions TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demand (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    product_id TEXT NOT NULL,
    demand_qty REAL NOT NULL,
    destination_region TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS optimization_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    mode TEXT NOT NULL,
    lambda_param REAL NOT NULL,
    weights TEXT NOT NULL,
    objective_total REAL,
    allocations TEXT NOT NULL,
    solver_stats TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS p2p_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_name TEXT NOT NULL DEFAULT 'default',
    case_id TEXT NOT NULL,
    activity TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    resource TEXT,
    cost REAL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_suppliers_domain ON suppliers(domain);
CREATE INDEX IF NOT EXISTS idx_demand_domain ON demand(domain);
CREATE INDEX IF NOT EXISTS idx_results_domain ON optimization_results(domain);
CREATE INDEX IF NOT EXISTS idx_p2p_dataset ON p2p_events(dataset_name);
"""


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    if not DB_AVAILABLE:
        logger.info("Database not configured — running in demo-only mode")
        return

    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema initialised (Turso/libsql)")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD — Suppliers
# ---------------------------------------------------------------------------

def db_insert_suppliers(conn, domain: str, suppliers: list[dict]) -> int:
    """Insert supplier rows. Returns count inserted."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for s in suppliers:
        regions = json.dumps(s["served_regions"]) if isinstance(s["served_regions"], list) else s["served_regions"]
        conn.execute(
            """INSERT INTO suppliers
               (domain, supplier_id, name, unit_cost, logistics_cost,
                lead_time_days, compliance_score, esg_score,
                min_order_qty, max_capacity, served_regions, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [domain, s["supplier_id"], s["name"], s["unit_cost"],
             s.get("logistics_cost", 0), s["lead_time_days"],
             s["compliance_score"], s["esg_score"],
             s.get("min_order_qty", 0), s["max_capacity"], regions, now],
        )
        count += 1
    conn.commit()
    return count


def db_get_suppliers(conn, domain: str) -> list[dict]:
    """Fetch suppliers for a domain."""
    rows = conn.execute(
        "SELECT supplier_id, name, unit_cost, logistics_cost, lead_time_days, "
        "compliance_score, esg_score, min_order_qty, max_capacity, served_regions "
        "FROM suppliers WHERE domain = ? ORDER BY supplier_id",
        [domain],
    ).fetchall()
    result = []
    for r in rows:
        regions = json.loads(r[9]) if isinstance(r[9], str) else r[9]
        result.append({
            "supplier_id": r[0], "name": r[1], "unit_cost": r[2],
            "logistics_cost": r[3], "lead_time_days": r[4],
            "compliance_score": r[5], "esg_score": r[6],
            "min_order_qty": r[7], "max_capacity": r[8],
            "served_regions": regions,
        })
    return result


def db_delete_suppliers(conn, domain: str) -> int:
    """Delete all suppliers for a domain. Returns count deleted."""
    cur = conn.execute("DELETE FROM suppliers WHERE domain = ?", [domain])
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# CRUD — Demand
# ---------------------------------------------------------------------------

def db_insert_demand(conn, domain: str, items: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for d in items:
        conn.execute(
            """INSERT INTO demand (domain, product_id, demand_qty, destination_region, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [domain, d["product_id"], d["demand_qty"], d["destination_region"], now],
        )
        count += 1
    conn.commit()
    return count


def db_get_demand(conn, domain: str) -> list[dict]:
    rows = conn.execute(
        "SELECT product_id, demand_qty, destination_region FROM demand WHERE domain = ? ORDER BY product_id",
        [domain],
    ).fetchall()
    return [{"product_id": r[0], "demand_qty": r[1], "destination_region": r[2]} for r in rows]


def db_delete_demand(conn, domain: str) -> int:
    cur = conn.execute("DELETE FROM demand WHERE domain = ?", [domain])
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# CRUD — Optimization Results
# ---------------------------------------------------------------------------

def db_save_result(conn, domain: str, mode: str, lambda_param: float,
                   weights: dict, objective_total: float,
                   allocations: list[dict], solver_stats: dict) -> int:
    """Save optimization result. Returns row ID."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO optimization_results
           (domain, mode, lambda_param, weights, objective_total, allocations, solver_stats, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [domain, mode, lambda_param, json.dumps(weights),
         objective_total, json.dumps(allocations),
         json.dumps(solver_stats), now],
    )
    conn.commit()
    return cur.lastrowid


def db_get_results(conn, domain: Optional[str] = None, limit: int = 50) -> list[dict]:
    if domain:
        rows = conn.execute(
            "SELECT id, domain, mode, lambda_param, objective_total, created_at "
            "FROM optimization_results WHERE domain = ? ORDER BY id DESC LIMIT ?",
            [domain, limit],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, domain, mode, lambda_param, objective_total, created_at "
            "FROM optimization_results ORDER BY id DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [{"id": r[0], "domain": r[1], "mode": r[2], "lambda_param": r[3],
             "objective_total": r[4], "created_at": r[5]} for r in rows]


def db_get_result_detail(conn, result_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, domain, mode, lambda_param, weights, objective_total, "
        "allocations, solver_stats, created_at "
        "FROM optimization_results WHERE id = ?",
        [result_id],
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "domain": row[1], "mode": row[2], "lambda_param": row[3],
        "weights": json.loads(row[4]), "objective_total": row[5],
        "allocations": json.loads(row[6]), "solver_stats": json.loads(row[7]),
        "created_at": row[8],
    }


# ---------------------------------------------------------------------------
# CRUD — P2P Events
# ---------------------------------------------------------------------------

def db_insert_p2p_events(conn, dataset_name: str, events: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for e in events:
        conn.execute(
            """INSERT INTO p2p_events (dataset_name, case_id, activity, timestamp, resource, cost, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [dataset_name, e["case_id"], e["activity"], e["timestamp"],
             e.get("resource"), e.get("cost", 0), now],
        )
        count += 1
    conn.commit()
    return count


def db_get_p2p_events(conn, dataset_name: str = "default") -> list[dict]:
    rows = conn.execute(
        "SELECT case_id, activity, timestamp, resource, cost "
        "FROM p2p_events WHERE dataset_name = ? ORDER BY timestamp",
        [dataset_name],
    ).fetchall()
    return [{"case_id": r[0], "activity": r[1], "timestamp": r[2],
             "resource": r[3], "cost": r[4]} for r in rows]


def db_get_p2p_datasets(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT dataset_name, COUNT(*) as cnt, MIN(timestamp) as first_ts, MAX(timestamp) as last_ts "
        "FROM p2p_events GROUP BY dataset_name ORDER BY dataset_name"
    ).fetchall()
    return [{"dataset_name": r[0], "event_count": r[1],
             "first_event": r[2], "last_event": r[3]} for r in rows]


def db_delete_p2p_events(conn, dataset_name: str) -> int:
    cur = conn.execute("DELETE FROM p2p_events WHERE dataset_name = ?", [dataset_name])
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Seed demo data into DB
# ---------------------------------------------------------------------------

def seed_domain_data(conn, domain: str):
    """Copy hardcoded demo data for a domain into the DB."""
    from app.data_layer import get_domain_data
    data = get_domain_data(domain)

    # Clear existing
    db_delete_suppliers(conn, domain)
    db_delete_demand(conn, domain)

    # Insert
    suppliers = [s.model_dump() if hasattr(s, "model_dump") else s for s in data["suppliers"]]
    demand = [d.model_dump() if hasattr(d, "model_dump") else d for d in data["demand"]]

    s_count = db_insert_suppliers(conn, domain, suppliers)
    d_count = db_insert_demand(conn, domain, demand)

    return {"domain": domain, "suppliers_inserted": s_count, "demand_inserted": d_count}


def seed_p2p_demo(conn, dataset_name: str = "demo"):
    """Copy hardcoded P2P event log into DB."""
    from app.data_layer import get_p2p_demo_events

    db_delete_p2p_events(conn, dataset_name)
    count = db_insert_p2p_events(conn, dataset_name, get_p2p_demo_events())
    return {"dataset_name": dataset_name, "events_inserted": count}
