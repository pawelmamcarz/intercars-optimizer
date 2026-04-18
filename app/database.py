"""
Database layer — Turso HTTP API with SQLite fallback.

Uses ONLY stdlib — zero external dependencies.
When TURSO_DATABASE_URL is set → calls Turso REST API.
When not set → uses local SQLite file (always available).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB mode detection
# ---------------------------------------------------------------------------

# Accept both FLOW_TURSO_* and plain TURSO_* env vars
_db_url = settings.turso_database_url or os.environ.get("TURSO_DATABASE_URL", "")
_db_token = settings.turso_auth_token or os.environ.get("TURSO_AUTH_TOKEN", "")
_USE_TURSO = bool(_db_url) and bool(_db_token)

# SQLite fallback path
_SQLITE_PATH = os.environ.get("SQLITE_PATH", str(Path(__file__).parent.parent / "data" / "flow_procurement.db"))

# DB is ALWAYS available now (Turso or SQLite)
DB_AVAILABLE = True

# Startup diagnostics
if _USE_TURSO:
    logger.info("DB mode: TURSO  url=%s", _db_url[:30] + "...")
else:
    os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)
    logger.info("DB mode: SQLite  path=%s", _SQLITE_PATH)


def _turso_url() -> str:
    """Convert libsql:// → https:// and append /v2/pipeline."""
    url = _db_url
    url = url.replace("libsql://", "https://").replace("ws://", "http://")
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/") + "/v2/pipeline"


def _encode_arg(val: Any) -> dict:
    """Encode a Python value to a Turso-typed parameter.

    Turso HTTP protocol rules:
    - integer values arrive as strings (JSON number can't reliably
      represent i64; the server parses the string back).
    - float values must be raw JSON numbers (f64). Sending '1800000.0'
      as a string triggers 'JSON parse error: invalid type: string,
      expected f64'. This cost us an hour during the libSQL switchover.
    """
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": str(int(val))}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    return {"type": "text", "value": str(val)}


def _decode_value(v: dict) -> Any:
    """Decode Turso typed value to Python."""
    t = v.get("type")
    if t == "null":
        return None
    val = v.get("value", "")
    if t == "integer":
        return int(val)
    if t == "float":
        return float(val)
    return val  # text, blob(as base64 str)


class TursoResult:
    """Lightweight result wrapper mimicking what we need."""
    __slots__ = ("columns", "rows", "rows_affected", "last_insert_rowid")

    def __init__(self, data: dict):
        self.columns = [c["name"] for c in data.get("cols", [])]
        self.rows = [
            tuple(_decode_value(cell) for cell in row)
            for row in data.get("rows", [])
        ]
        self.rows_affected = data.get("affected_row_count", 0)
        rid = data.get("last_insert_rowid")
        self.last_insert_rowid = int(rid) if rid is not None else None


class TursoClient:
    """Minimal sync Turso HTTP client using stdlib only."""

    def __init__(self, pipeline_url: str, auth_token: str):
        self._url = pipeline_url
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    def _post(self, requests_list: list[dict]) -> list[dict]:
        body = json.dumps({"requests": requests_list}).encode()
        req = urllib.request.Request(self._url, data=body, headers=self._headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Turso HTTP {e.code}: {err_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Turso connection error: {e.reason}") from e

        results = data.get("results", [])
        # Check for errors
        for r in results:
            if r.get("type") == "error":
                msg = r.get("error", {}).get("message", "Unknown Turso error")
                raise RuntimeError(f"Turso SQL error: {msg}")
        return results

    def execute(self, sql: str, args: list | None = None) -> TursoResult:
        """Execute a single SQL statement."""
        stmt: dict = {"sql": sql}
        if args:
            stmt["args"] = [_encode_arg(a) for a in args]
        results = self._post([
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ])
        result_data = results[0]["response"]["result"]
        return TursoResult(result_data)

    def batch(self, statements: list) -> list[TursoResult]:
        """Execute multiple SQL statements in one HTTP call.

        Each item can be:
          - a plain str (SQL with no args)
          - a tuple (sql, args_list)
        """
        requests_list = []
        for s in statements:
            if isinstance(s, str):
                requests_list.append({"type": "execute", "stmt": {"sql": s}})
            elif isinstance(s, (list, tuple)) and len(s) == 2:
                sql, args = s
                stmt: dict = {"sql": sql}
                if args:
                    stmt["args"] = [_encode_arg(a) for a in args]
                requests_list.append({"type": "execute", "stmt": stmt})
            else:
                raise ValueError(f"Invalid batch statement: {s!r}")
        requests_list.append({"type": "close"})

        results = self._post(requests_list)
        out = []
        for r in results:
            resp = r.get("response", {})
            if resp.get("type") == "execute":
                out.append(TursoResult(resp["result"]))
        return out


# ---------------------------------------------------------------------------
# SQLite client — same interface as TursoClient
# ---------------------------------------------------------------------------

class SQLiteClient:
    """Local SQLite client with the same execute/batch interface as TursoClient."""

    def __init__(self, db_path: str):
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def execute(self, sql: str, args: list | None = None) -> TursoResult:
        cur = self._conn.cursor()
        cur.execute(sql, args or [])
        self._conn.commit()

        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []

        data = {
            "cols": [{"name": c} for c in cols],
            "rows": [[{"type": _sqlite_type(v), "value": str(v) if v is not None else None} for v in row] for row in rows],
            "affected_row_count": cur.rowcount if cur.rowcount > 0 else 0,
            "last_insert_rowid": cur.lastrowid,
        }
        return TursoResult(data)

    def batch(self, statements: list) -> list[TursoResult]:
        results = []
        for s in statements:
            if isinstance(s, str):
                results.append(self.execute(s))
            elif isinstance(s, (list, tuple)) and len(s) == 2:
                results.append(self.execute(s[0], s[1]))
            else:
                raise ValueError(f"Invalid batch statement: {s!r}")
        return results


def _sqlite_type(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "float"
    return "text"


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if _USE_TURSO:
        _client = TursoClient(_turso_url(), _db_token)
        logger.info("Connected to Turso")
    else:
        _client = SQLiteClient(_SQLITE_PATH)
        logger.info("Connected to SQLite: %s", _SQLITE_PATH)
    return _client


def get_db():
    """FastAPI Dependency — yields a DB client (Turso or SQLite)."""
    yield _get_client()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA_STATEMENTS = [
    # ── Tenants (multi-tenant SaaS) ──
    """CREATE TABLE IF NOT EXISTS tenants (
        tenant_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'demo',
        is_active INTEGER DEFAULT 1,
        max_users INTEGER DEFAULT 10,
        max_catalog_items INTEGER DEFAULT 500,
        contact_email TEXT,
        features TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS suppliers (
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
        created_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    """CREATE TABLE IF NOT EXISTS demand (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        product_id TEXT NOT NULL,
        demand_qty REAL NOT NULL,
        destination_region TEXT NOT NULL,
        created_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    """CREATE TABLE IF NOT EXISTS optimization_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        mode TEXT NOT NULL,
        lambda_param REAL NOT NULL,
        weights TEXT NOT NULL,
        objective_total REAL,
        allocations TEXT NOT NULL,
        solver_stats TEXT NOT NULL,
        created_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    """CREATE TABLE IF NOT EXISTS p2p_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_name TEXT NOT NULL DEFAULT 'default',
        case_id TEXT NOT NULL,
        activity TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        resource TEXT,
        cost REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_domain ON suppliers(domain)",
    "CREATE INDEX IF NOT EXISTS idx_demand_domain ON demand(domain)",
    "CREATE INDEX IF NOT EXISTS idx_results_domain ON optimization_results(domain)",
    "CREATE INDEX IF NOT EXISTS idx_p2p_dataset ON p2p_events(dataset_name)",
    # ── Orders (buying module persistence) ──
    """CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'draft',
        requester TEXT,
        mpk TEXT,
        gl_account TEXT,
        items TEXT NOT NULL,
        subtotal REAL,
        discount REAL DEFAULT 0,
        shipping_fee REAL DEFAULT 0,
        total REAL,
        total_items INTEGER,
        delivery_days INTEGER,
        requires_manager_approval INTEGER DEFAULT 0,
        optimized_cost REAL,
        savings_pln REAL,
        domain_results TEXT,
        purchase_orders TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
    """CREATE TABLE IF NOT EXISTS order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        actor TEXT,
        note TEXT,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id)",
    # ── Supplier Profiles (supplier management module) ──
    """CREATE TABLE IF NOT EXISTS supplier_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        nip TEXT,
        country_code TEXT DEFAULT 'PL',
        data TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_nip ON supplier_profiles(nip)",
    # ── Users (JWT auth) ──
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'buyer',
        supplier_id TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        last_login TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
    # ── Catalog Items (backoffice) ──
    """CREATE TABLE IF NOT EXISTS catalog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category TEXT NOT NULL,
        delivery_days INTEGER DEFAULT 3,
        weight_kg REAL,
        unit TEXT DEFAULT 'szt',
        requires_approval INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        unspsc_code TEXT,
        unspsc_name TEXT,
        manufacturer TEXT,
        ean TEXT,
        created_at TEXT,
        updated_at TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_catalog_items_category ON catalog_items(category)",
    "CREATE INDEX IF NOT EXISTS idx_catalog_items_unspsc ON catalog_items(unspsc_code)",
    # ── Business Rules (backoffice) ──
    """CREATE TABLE IF NOT EXISTS business_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT NOT NULL,
        rule_key TEXT NOT NULL,
        config TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        description TEXT,
        created_at TEXT,
        updated_at TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'demo',
        UNIQUE(rule_type, rule_key)
    )""",
    # ── Workflow Steps (backoffice) ──
    """CREATE TABLE IF NOT EXISTS workflow_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_name TEXT NOT NULL DEFAULT 'order_approval',
        step_order INTEGER NOT NULL,
        condition_type TEXT NOT NULL,
        condition_value TEXT,
        approver_role TEXT NOT NULL,
        sla_hours INTEGER DEFAULT 24,
        is_active INTEGER DEFAULT 1,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    # ── Contracts (MVP-4 persistence) ──
    """CREATE TABLE IF NOT EXISTS contracts (
        id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL,
        supplier_name TEXT NOT NULL,
        category TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        committed_volume_pln REAL DEFAULT 0,
        price_lock INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        notes TEXT,
        tenant_id TEXT NOT NULL DEFAULT 'demo',
        created_at TEXT,
        updated_at TEXT
    )""",
    # ── Contract audit log (who changed what, when) ──
    """CREATE TABLE IF NOT EXISTS contract_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor TEXT,
        diff TEXT,
        occurred_at TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'demo'
    )""",
    """CREATE INDEX IF NOT EXISTS idx_contract_audit_contract_id
        ON contract_audit(contract_id)""",
]


def _migrate_tenant_id(client):
    """Add tenant_id column to existing tables (idempotent migration)."""
    tables_needing_tenant = [
        "users", "orders", "order_events", "suppliers", "demand",
        "optimization_results", "p2p_events", "catalog_items",
        "business_rules", "workflow_steps", "supplier_profiles",
    ]
    for table in tables_needing_tenant:
        try:
            # Check if column exists
            rs = client.execute(f"PRAGMA table_info({table})")
            columns = [r[1] for r in rs.rows]
            if "tenant_id" not in columns:
                client.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'demo'")
                logger.info("Added tenant_id column to %s", table)
        except Exception as e:
            logger.warning("Migration tenant_id on %s skipped: %s", table, e)

    # Create indexes for tenant_id
    idx_stmts = [
        f"CREATE INDEX IF NOT EXISTS idx_{t}_tenant ON {t}(tenant_id)"
        for t in tables_needing_tenant
    ]
    try:
        client.batch(idx_stmts)
    except Exception as e:
        logger.warning("tenant_id indexes: %s", e)


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    client = _get_client()
    try:
        client.batch(_SCHEMA_STATEMENTS)
        mode = "Turso" if _USE_TURSO else "SQLite"
        logger.info("Database schema initialised (%s)", mode)
        # Run tenant_id migration on existing tables
        _migrate_tenant_id(client)
    except Exception as e:
        logger.error("Database init failed: %s", e)


# ---------------------------------------------------------------------------
# CRUD — Suppliers
# ---------------------------------------------------------------------------

def db_insert_suppliers(client: TursoClient, domain: str, suppliers: list[dict]) -> int:
    """Insert supplier rows via batch. Returns count inserted."""
    now = datetime.now(timezone.utc).isoformat()
    stmts = []
    for s in suppliers:
        regions = json.dumps(s["served_regions"]) if isinstance(s["served_regions"], list) else s["served_regions"]
        stmts.append((
            """INSERT INTO suppliers
               (domain, supplier_id, name, unit_cost, logistics_cost,
                lead_time_days, compliance_score, esg_score,
                min_order_qty, max_capacity, served_regions, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [domain, s["supplier_id"], s["name"], s["unit_cost"],
             s.get("logistics_cost", 0), s["lead_time_days"],
             s["compliance_score"], s["esg_score"],
             s.get("min_order_qty", 0), s["max_capacity"], regions, now],
        ))
    if stmts:
        client.batch(stmts)
    return len(stmts)


def db_get_suppliers(client: TursoClient, domain: str) -> list[dict]:
    """Fetch suppliers for a domain."""
    rs = client.execute(
        "SELECT supplier_id, name, unit_cost, logistics_cost, lead_time_days, "
        "compliance_score, esg_score, min_order_qty, max_capacity, served_regions "
        "FROM suppliers WHERE domain = ? ORDER BY supplier_id",
        [domain],
    )
    result = []
    for r in rs.rows:
        regions = json.loads(r[9]) if isinstance(r[9], str) else r[9]
        result.append({
            "supplier_id": r[0], "name": r[1], "unit_cost": r[2],
            "logistics_cost": r[3], "lead_time_days": r[4],
            "compliance_score": r[5], "esg_score": r[6],
            "min_order_qty": r[7], "max_capacity": r[8],
            "served_regions": regions,
        })
    return result


def db_delete_suppliers(client: TursoClient, domain: str) -> int:
    """Delete all suppliers for a domain. Returns count deleted."""
    rs = client.execute("DELETE FROM suppliers WHERE domain = ?", [domain])
    return rs.rows_affected


# ---------------------------------------------------------------------------
# CRUD — Demand
# ---------------------------------------------------------------------------

def db_insert_demand(client: TursoClient, domain: str, items: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    stmts = []
    for d in items:
        stmts.append((
            """INSERT INTO demand (domain, product_id, demand_qty, destination_region, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [domain, d["product_id"], d["demand_qty"], d["destination_region"], now],
        ))
    if stmts:
        client.batch(stmts)
    return len(stmts)


def db_get_demand(client: TursoClient, domain: str) -> list[dict]:
    rs = client.execute(
        "SELECT product_id, demand_qty, destination_region FROM demand WHERE domain = ? ORDER BY product_id",
        [domain],
    )
    return [{"product_id": r[0], "demand_qty": r[1], "destination_region": r[2]} for r in rs.rows]


def db_delete_demand(client: TursoClient, domain: str) -> int:
    rs = client.execute("DELETE FROM demand WHERE domain = ?", [domain])
    return rs.rows_affected


# ---------------------------------------------------------------------------
# CRUD — Optimization Results
# ---------------------------------------------------------------------------

def db_save_result(client: TursoClient, domain: str, mode: str, lambda_param: float,
                   weights: dict, objective_total: float,
                   allocations: list[dict], solver_stats: dict) -> int:
    """Save optimization result. Returns row ID."""
    now = datetime.now(timezone.utc).isoformat()
    rs = client.execute(
        """INSERT INTO optimization_results
           (domain, mode, lambda_param, weights, objective_total, allocations, solver_stats, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [domain, mode, lambda_param, json.dumps(weights),
         objective_total, json.dumps(allocations),
         json.dumps(solver_stats), now],
    )
    return rs.last_insert_rowid


def db_get_results(client: TursoClient, domain: Optional[str] = None, limit: int = 50) -> list[dict]:
    if domain:
        rs = client.execute(
            "SELECT id, domain, mode, lambda_param, objective_total, created_at "
            "FROM optimization_results WHERE domain = ? ORDER BY id DESC LIMIT ?",
            [domain, limit],
        )
    else:
        rs = client.execute(
            "SELECT id, domain, mode, lambda_param, objective_total, created_at "
            "FROM optimization_results ORDER BY id DESC LIMIT ?",
            [limit],
        )
    return [{"id": r[0], "domain": r[1], "mode": r[2], "lambda_param": r[3],
             "objective_total": r[4], "created_at": r[5]} for r in rs.rows]


def db_get_result_detail(client: TursoClient, result_id: int) -> Optional[dict]:
    rs = client.execute(
        "SELECT id, domain, mode, lambda_param, weights, objective_total, "
        "allocations, solver_stats, created_at "
        "FROM optimization_results WHERE id = ?",
        [result_id],
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {
        "id": row[0], "domain": row[1], "mode": row[2], "lambda_param": row[3],
        "weights": json.loads(row[4]), "objective_total": row[5],
        "allocations": json.loads(row[6]), "solver_stats": json.loads(row[7]),
        "created_at": row[8],
    }


# ---------------------------------------------------------------------------
# CRUD — P2P Events
# ---------------------------------------------------------------------------

def db_insert_p2p_events(client: TursoClient, dataset_name: str, events: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    stmts = []
    for e in events:
        stmts.append((
            """INSERT INTO p2p_events (dataset_name, case_id, activity, timestamp, resource, cost, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [dataset_name, e["case_id"], e["activity"], e["timestamp"],
             e.get("resource"), e.get("cost", 0), now],
        ))
    if stmts:
        client.batch(stmts)
    return len(stmts)


def db_get_p2p_events(client: TursoClient, dataset_name: str = "default") -> list[dict]:
    rs = client.execute(
        "SELECT case_id, activity, timestamp, resource, cost "
        "FROM p2p_events WHERE dataset_name = ? ORDER BY timestamp",
        [dataset_name],
    )
    return [{"case_id": r[0], "activity": r[1], "timestamp": r[2],
             "resource": r[3], "cost": r[4]} for r in rs.rows]


def db_get_p2p_datasets(client: TursoClient) -> list[dict]:
    rs = client.execute(
        "SELECT dataset_name, COUNT(*) as cnt, MIN(timestamp) as first_ts, MAX(timestamp) as last_ts "
        "FROM p2p_events GROUP BY dataset_name ORDER BY dataset_name"
    )
    return [{"dataset_name": r[0], "event_count": r[1],
             "first_event": r[2], "last_event": r[3]} for r in rs.rows]


def db_delete_p2p_events(client: TursoClient, dataset_name: str) -> int:
    rs = client.execute("DELETE FROM p2p_events WHERE dataset_name = ?", [dataset_name])
    return rs.rows_affected


# ---------------------------------------------------------------------------
# Seed demo data into DB
# ---------------------------------------------------------------------------

def seed_domain_data(client: TursoClient, domain: str):
    """Copy hardcoded demo data for a domain into the DB."""
    from app.data_layer import get_domain_data
    data = get_domain_data(domain)

    # Clear existing
    db_delete_suppliers(client, domain)
    db_delete_demand(client, domain)

    # Insert
    suppliers = [s.model_dump() if hasattr(s, "model_dump") else s for s in data["suppliers"]]
    demand = [d.model_dump() if hasattr(d, "model_dump") else d for d in data["demand"]]

    s_count = db_insert_suppliers(client, domain, suppliers)
    d_count = db_insert_demand(client, domain, demand)

    return {"domain": domain, "suppliers_inserted": s_count, "demand_inserted": d_count}


# ---------------------------------------------------------------------------
# CRUD — Orders (buying module)
# ---------------------------------------------------------------------------

def db_save_order(client: TursoClient, order: dict) -> str:
    """Upsert an order (INSERT or UPDATE by order_id). Returns order_id."""
    now = datetime.now(timezone.utc).isoformat()
    oid = order["order_id"]
    items_json = json.dumps(order.get("items", []))
    dr_json = json.dumps(order.get("domain_results", []))
    po_json = json.dumps(order.get("purchase_orders", []))

    # Try update first
    rs = client.execute(
        """UPDATE orders SET status=?, requester=?, mpk=?, gl_account=?,
           items=?, subtotal=?, discount=?, shipping_fee=?, total=?,
           total_items=?, delivery_days=?, requires_manager_approval=?,
           optimized_cost=?, savings_pln=?, domain_results=?,
           purchase_orders=?, updated_at=?
           WHERE order_id=?""",
        [order.get("status", "draft"), order.get("requester"),
         order.get("mpk"), order.get("gl_account"),
         items_json, order.get("subtotal", 0), order.get("discount", 0),
         order.get("shipping_fee", 0), order.get("total", 0),
         order.get("total_items", 0), order.get("delivery_days"),
         int(order.get("requires_manager_approval", False)),
         order.get("optimized_cost"), order.get("savings_pln"),
         dr_json, po_json, now, oid],
    )
    if rs.rows_affected == 0:
        # Insert new
        client.execute(
            """INSERT INTO orders (order_id, status, requester, mpk, gl_account,
               items, subtotal, discount, shipping_fee, total,
               total_items, delivery_days, requires_manager_approval,
               optimized_cost, savings_pln, domain_results,
               purchase_orders, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [oid, order.get("status", "draft"), order.get("requester"),
             order.get("mpk"), order.get("gl_account"),
             items_json, order.get("subtotal", 0), order.get("discount", 0),
             order.get("shipping_fee", 0), order.get("total", 0),
             order.get("total_items", 0), order.get("delivery_days"),
             int(order.get("requires_manager_approval", False)),
             order.get("optimized_cost"), order.get("savings_pln"),
             dr_json, po_json,
             order.get("created_at", now), now],
        )
    return oid


def _row_to_order(columns: list[str], row: tuple) -> dict:
    """Convert a DB row to order dict with JSON fields decoded."""
    d = dict(zip(columns, row))
    for key in ("items", "domain_results", "purchase_orders"):
        if d.get(key) and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    d["requires_manager_approval"] = bool(d.get("requires_manager_approval"))
    return d


def db_get_order(client: TursoClient, order_id: str) -> Optional[dict]:
    rs = client.execute(
        "SELECT order_id, status, requester, mpk, gl_account, items, "
        "subtotal, discount, shipping_fee, total, total_items, delivery_days, "
        "requires_manager_approval, optimized_cost, savings_pln, "
        "domain_results, purchase_orders, created_at, updated_at "
        "FROM orders WHERE order_id = ?",
        [order_id],
    )
    if not rs.rows:
        return None
    return _row_to_order(rs.columns, rs.rows[0])


def db_list_orders(client: TursoClient, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    if status:
        rs = client.execute(
            "SELECT order_id, status, requester, mpk, gl_account, items, "
            "subtotal, discount, shipping_fee, total, total_items, delivery_days, "
            "requires_manager_approval, optimized_cost, savings_pln, "
            "domain_results, purchase_orders, created_at, updated_at "
            "FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            [status, limit],
        )
    else:
        rs = client.execute(
            "SELECT order_id, status, requester, mpk, gl_account, items, "
            "subtotal, discount, shipping_fee, total, total_items, delivery_days, "
            "requires_manager_approval, optimized_cost, savings_pln, "
            "domain_results, purchase_orders, created_at, updated_at "
            "FROM orders ORDER BY created_at DESC LIMIT ?",
            [limit],
        )
    return [_row_to_order(rs.columns, row) for row in rs.rows]


def db_add_order_event(client: TursoClient, order_id: str,
                       action: str, status: str,
                       actor: str = "system", note: str = "") -> int:
    now = datetime.now(timezone.utc).isoformat()
    rs = client.execute(
        """INSERT INTO order_events (order_id, action, status, actor, note, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [order_id, action, status, actor, note, now],
    )
    return rs.last_insert_rowid


def db_get_order_events(client: TursoClient, order_id: str) -> list[dict]:
    rs = client.execute(
        "SELECT action, status, actor, note, timestamp "
        "FROM order_events WHERE order_id = ? ORDER BY timestamp",
        [order_id],
    )
    return [{"action": r[0], "status": r[1], "actor": r[2],
             "note": r[3], "timestamp": r[4]} for r in rs.rows]


def db_get_order_kpi(client: TursoClient) -> dict:
    """Aggregate order statistics for KPI dashboard."""
    rs_counts = client.execute(
        "SELECT status, COUNT(*) as cnt, COALESCE(SUM(total),0) as spend, "
        "COALESCE(SUM(savings_pln),0) as saved "
        "FROM orders GROUP BY status"
    )
    by_status = {}
    total_orders = 0
    total_spend = 0.0
    total_savings = 0.0
    for r in rs_counts.rows:
        by_status[r[0]] = {"count": r[1], "spend": r[2], "savings": r[3]}
        total_orders += r[1]
        total_spend += r[2]
        total_savings += r[3]

    return {
        "total_orders": total_orders,
        "orders_by_status": by_status,
        "total_spend_pln": round(total_spend, 2),
        "total_savings_pln": round(total_savings, 2),
        "avg_order_value": round(total_spend / total_orders, 2) if total_orders else 0,
        "avg_savings_pct": round((total_savings / total_spend * 100), 1) if total_spend else 0,
    }


# ---------------------------------------------------------------------------
# CRUD — Supplier Profiles (supplier management module)
# ---------------------------------------------------------------------------

def db_save_supplier_profile(client: TursoClient, profile: dict) -> str:
    """Upsert a supplier profile. Returns supplier_id."""
    now = datetime.now(timezone.utc).isoformat()
    sid = profile["supplier_id"]
    data_json = json.dumps({
        k: v for k, v in profile.items()
        if k not in ("supplier_id", "name", "nip", "country_code")
    })

    rs = client.execute(
        """UPDATE supplier_profiles SET name=?, nip=?, country_code=?,
           data=?, updated_at=? WHERE supplier_id=?""",
        [profile.get("name", ""), profile.get("nip", ""),
         profile.get("country_code", "PL"), data_json, now, sid],
    )
    if rs.rows_affected == 0:
        client.execute(
            """INSERT INTO supplier_profiles
               (supplier_id, name, nip, country_code, data, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [sid, profile.get("name", ""), profile.get("nip", ""),
             profile.get("country_code", "PL"), data_json,
             profile.get("created_at", now), now],
        )
    return sid


# ---------------------------------------------------------------------------
# CRUD — Catalog Items (backoffice)
# ---------------------------------------------------------------------------

def db_list_catalog(client: TursoClient, category: str | None = None,
                    search: str | None = None, active_only: bool = True) -> list[dict]:
    sql = "SELECT item_id, name, description, price, category, delivery_days, weight_kg, unit, requires_approval, is_active, unspsc_code, unspsc_name, manufacturer, ean, created_at, updated_at FROM catalog_items"
    conditions, params = [], []
    if active_only:
        conditions.append("is_active = 1")
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(name LIKE ? OR item_id LIKE ? OR unspsc_code LIKE ? OR ean LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s, s])
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY category, name"
    rs = client.execute(sql, params)
    cols = ["item_id", "name", "description", "price", "category", "delivery_days",
            "weight_kg", "unit", "requires_approval", "is_active", "unspsc_code",
            "unspsc_name", "manufacturer", "ean", "created_at", "updated_at"]
    return [dict(zip(cols, row)) for row in rs.rows]


def db_save_catalog_item(client: TursoClient, item: dict) -> str:
    now = datetime.now(timezone.utc).isoformat()
    iid = item["item_id"]
    rs = client.execute(
        """UPDATE catalog_items SET name=?, description=?, price=?, category=?,
           delivery_days=?, weight_kg=?, unit=?, requires_approval=?, is_active=?,
           unspsc_code=?, unspsc_name=?, manufacturer=?, ean=?, updated_at=?
           WHERE item_id=?""",
        [item.get("name", ""), item.get("description", ""), item.get("price", 0),
         item.get("category", "parts"), item.get("delivery_days", 3),
         item.get("weight_kg"), item.get("unit", "szt"),
         int(item.get("requires_approval", False)),
         int(item.get("is_active", True)),
         item.get("unspsc_code"), item.get("unspsc_name"),
         item.get("manufacturer"), item.get("ean"), now, iid],
    )
    if rs.rows_affected == 0:
        client.execute(
            """INSERT INTO catalog_items
               (item_id, name, description, price, category, delivery_days,
                weight_kg, unit, requires_approval, is_active,
                unspsc_code, unspsc_name, manufacturer, ean, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [iid, item.get("name", ""), item.get("description", ""),
             item.get("price", 0), item.get("category", "parts"),
             item.get("delivery_days", 3), item.get("weight_kg"),
             item.get("unit", "szt"), int(item.get("requires_approval", False)),
             int(item.get("is_active", True)),
             item.get("unspsc_code"), item.get("unspsc_name"),
             item.get("manufacturer"), item.get("ean"), now, now],
        )
    return iid


def db_delete_catalog_item(client: TursoClient, item_id: str) -> int:
    """Soft-delete: set is_active=0."""
    rs = client.execute("UPDATE catalog_items SET is_active = 0, updated_at = ? WHERE item_id = ?",
                        [datetime.now(timezone.utc).isoformat(), item_id])
    return rs.rows_affected


# ---------------------------------------------------------------------------
# CRUD — Business Rules (backoffice)
# ---------------------------------------------------------------------------

def db_list_rules(client: TursoClient, rule_type: str | None = None,
                  active_only: bool = True) -> list[dict]:
    sql = "SELECT id, rule_type, rule_key, config, is_active, description, created_at, updated_at FROM business_rules"
    conditions, params = [], []
    if active_only:
        conditions.append("is_active = 1")
    if rule_type:
        conditions.append("rule_type = ?")
        params.append(rule_type)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY rule_type, rule_key"
    rs = client.execute(sql, params)
    cols = ["id", "rule_type", "rule_key", "config", "is_active", "description", "created_at", "updated_at"]
    result = []
    for row in rs.rows:
        d = dict(zip(cols, row))
        if d.get("config") and isinstance(d["config"], str):
            d["config"] = json.loads(d["config"])
        result.append(d)
    return result


def db_save_rule(client: TursoClient, rule: dict) -> int:
    now = datetime.now(timezone.utc).isoformat()
    config_json = json.dumps(rule["config"]) if isinstance(rule.get("config"), dict) else rule.get("config", "{}")
    if rule.get("id"):
        client.execute(
            "UPDATE business_rules SET config=?, is_active=?, description=?, updated_at=? WHERE id=?",
            [config_json, int(rule.get("is_active", True)), rule.get("description", ""), now, rule["id"]],
        )
        return rule["id"]
    else:
        client.execute(
            """INSERT INTO business_rules (rule_type, rule_key, config, is_active, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [rule["rule_type"], rule["rule_key"], config_json,
             int(rule.get("is_active", True)), rule.get("description", ""), now, now],
        )
        rs = client.execute("SELECT last_insert_rowid()")
        return rs.rows[0][0] if rs.rows else 0


def db_delete_rule(client: TursoClient, rule_id: int) -> int:
    rs = client.execute("UPDATE business_rules SET is_active = 0, updated_at = ? WHERE id = ?",
                        [datetime.now(timezone.utc).isoformat(), rule_id])
    return rs.rows_affected


# ---------------------------------------------------------------------------
# CRUD — Workflow Steps (backoffice)
# ---------------------------------------------------------------------------

def db_list_workflow_steps(client: TursoClient, workflow_name: str = "order_approval") -> list[dict]:
    rs = client.execute(
        "SELECT id, workflow_name, step_order, condition_type, condition_value, approver_role, sla_hours, is_active "
        "FROM workflow_steps WHERE workflow_name = ? AND is_active = 1 ORDER BY step_order",
        [workflow_name],
    )
    cols = ["id", "workflow_name", "step_order", "condition_type", "condition_value", "approver_role", "sla_hours", "is_active"]
    result = []
    for row in rs.rows:
        d = dict(zip(cols, row))
        if d.get("condition_value") and isinstance(d["condition_value"], str):
            try:
                d["condition_value"] = json.loads(d["condition_value"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(d)
    return result


def db_save_workflow_step(client: TursoClient, step: dict) -> int:
    cond_json = json.dumps(step.get("condition_value")) if isinstance(step.get("condition_value"), (dict, list)) else step.get("condition_value", "")
    if step.get("id"):
        client.execute(
            "UPDATE workflow_steps SET step_order=?, condition_type=?, condition_value=?, approver_role=?, sla_hours=? WHERE id=?",
            [step["step_order"], step["condition_type"], cond_json, step["approver_role"], step.get("sla_hours", 24), step["id"]],
        )
        return step["id"]
    else:
        client.execute(
            """INSERT INTO workflow_steps (workflow_name, step_order, condition_type, condition_value, approver_role, sla_hours, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            [step.get("workflow_name", "order_approval"), step["step_order"],
             step["condition_type"], cond_json, step["approver_role"], step.get("sla_hours", 24)],
        )
        rs = client.execute("SELECT last_insert_rowid()")
        return rs.rows[0][0] if rs.rows else 0


def db_delete_workflow_step(client: TursoClient, step_id: int) -> int:
    rs = client.execute("UPDATE workflow_steps SET is_active = 0 WHERE id = ?", [step_id])
    return rs.rows_affected


def db_get_supplier_profile(client: TursoClient, supplier_id: str) -> Optional[dict]:
    rs = client.execute(
        "SELECT supplier_id, name, nip, country_code, data, created_at, updated_at "
        "FROM supplier_profiles WHERE supplier_id = ?",
        [supplier_id],
    )
    if not rs.rows:
        return None
    r = rs.rows[0]
    profile = json.loads(r[4]) if r[4] else {}
    profile.update({"supplier_id": r[0], "name": r[1], "nip": r[2],
                     "country_code": r[3], "created_at": r[5], "updated_at": r[6]})
    return profile


def db_list_supplier_profiles(client: TursoClient, limit: int = 200) -> list[dict]:
    rs = client.execute(
        "SELECT supplier_id, name, nip, country_code, data, created_at, updated_at "
        "FROM supplier_profiles ORDER BY name LIMIT ?",
        [limit],
    )
    results = []
    for r in rs.rows:
        profile = json.loads(r[4]) if r[4] else {}
        profile.update({"supplier_id": r[0], "name": r[1], "nip": r[2],
                         "country_code": r[3], "created_at": r[5], "updated_at": r[6]})
        results.append(profile)
    return results


def db_delete_supplier_profile(client: TursoClient, supplier_id: str) -> int:
    rs = client.execute("DELETE FROM supplier_profiles WHERE supplier_id = ?", [supplier_id])
    return rs.rows_affected


def seed_p2p_demo(client: TursoClient, dataset_name: str = "demo"):
    """Copy hardcoded P2P event log into DB."""
    from app.data_layer import get_p2p_demo_events

    db_delete_p2p_events(client, dataset_name)
    count = db_insert_p2p_events(client, dataset_name, get_p2p_demo_events())
    return {"dataset_name": dataset_name, "events_inserted": count}


# ---------------------------------------------------------------------------
# CRUD — Contracts (MVP-4 persistence)
# ---------------------------------------------------------------------------

def _row_to_contract(row) -> dict:
    """Map a raw Turso row back to a dict with the same shape as
    contract_engine.contract_to_dict (minus days_to_expiry which is a
    view concern and gets calculated at read time by the caller)."""
    return {
        "id": row[0],
        "supplier_id": row[1],
        "supplier_name": row[2],
        "category": row[3],
        "start_date": row[4],
        "end_date": row[5],
        "committed_volume_pln": float(row[6] or 0),
        "price_lock": bool(row[7]),
        "status": row[8] or "active",
        "notes": row[9] or "",
    }


_CONTRACT_COLS = (
    "id, supplier_id, supplier_name, category, start_date, end_date, "
    "committed_volume_pln, price_lock, status, notes"
)


def db_list_contracts(client: TursoClient, tenant_id: str = "demo") -> list[dict]:
    rs = client.execute(
        f"SELECT {_CONTRACT_COLS} FROM contracts WHERE tenant_id = ? "
        f"ORDER BY end_date ASC",
        [tenant_id],
    )
    return [_row_to_contract(r) for r in rs.rows]


def db_get_contract(client: TursoClient, contract_id: str,
                    tenant_id: str = "demo") -> Optional[dict]:
    rs = client.execute(
        f"SELECT {_CONTRACT_COLS} FROM contracts WHERE id = ? AND tenant_id = ?",
        [contract_id, tenant_id],
    )
    if not rs.rows:
        return None
    return _row_to_contract(rs.rows[0])


def db_upsert_contract(client: TursoClient, contract: dict,
                       tenant_id: str = "demo") -> str:
    """Insert or replace a single contract. `contract` dict must carry the
    fields used by _row_to_contract. `tenant_id` defaults to the demo tenant
    to stay aligned with the rest of the single-tenant deployment."""
    now = datetime.now(timezone.utc).isoformat()
    client.execute(
        "INSERT OR REPLACE INTO contracts "
        "(id, supplier_id, supplier_name, category, start_date, end_date, "
        " committed_volume_pln, price_lock, status, notes, "
        " tenant_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "        COALESCE((SELECT created_at FROM contracts WHERE id = ?), ?), ?)",
        [
            contract["id"],
            contract["supplier_id"],
            contract["supplier_name"],
            contract["category"],
            contract["start_date"],
            contract["end_date"],
            float(contract.get("committed_volume_pln") or 0),
            1 if contract.get("price_lock") else 0,
            contract.get("status") or "active",
            contract.get("notes") or "",
            tenant_id,
            contract["id"],
            now,
            now,
        ],
    )
    return contract["id"]


def db_delete_contract(client: TursoClient, contract_id: str,
                       tenant_id: str = "demo") -> int:
    rs = client.execute(
        "DELETE FROM contracts WHERE id = ? AND tenant_id = ?",
        [contract_id, tenant_id],
    )
    return rs.rows_affected


def db_count_contracts(client: TursoClient, tenant_id: str = "demo") -> int:
    rs = client.execute(
        "SELECT COUNT(*) FROM contracts WHERE tenant_id = ?",
        [tenant_id],
    )
    return int(rs.rows[0][0]) if rs.rows else 0


# ---------------------------------------------------------------------------
# Contract audit log
# ---------------------------------------------------------------------------

def db_append_contract_audit(
    client: TursoClient,
    contract_id: str,
    action: str,
    actor: str = "system",
    diff: str = "",
    tenant_id: str = "demo",
) -> None:
    """Append a single audit entry. `diff` is free-form JSON string from the
    caller — cheap, avoids schema churn if we later track extra keys."""
    client.execute(
        "INSERT INTO contract_audit (contract_id, action, actor, diff, occurred_at, tenant_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            contract_id,
            action,
            actor or "system",
            diff or "",
            datetime.now(timezone.utc).isoformat(),
            tenant_id,
        ],
    )


def db_get_contract_audit(
    client: TursoClient,
    contract_id: str,
    tenant_id: str = "demo",
    limit: int = 50,
) -> list[dict]:
    rs = client.execute(
        "SELECT id, contract_id, action, actor, diff, occurred_at "
        "FROM contract_audit WHERE contract_id = ? AND tenant_id = ? "
        "ORDER BY occurred_at DESC LIMIT ?",
        [contract_id, tenant_id, limit],
    )
    return [
        {
            "id": r[0],
            "contract_id": r[1],
            "action": r[2],
            "actor": r[3],
            "diff": r[4],
            "occurred_at": r[5],
        }
        for r in rs.rows
    ]
