"""
Database layer — Turso HTTP API with graceful fallback.

Uses ONLY stdlib (urllib.request) — zero external dependencies.
When TURSO_DATABASE_URL is set → calls Turso REST API.
When not set → DB_AVAILABLE=False, app falls back to in-memory demo data.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Turso HTTP client — pure stdlib
# ---------------------------------------------------------------------------

DB_AVAILABLE = bool(settings.turso_database_url) and bool(settings.turso_auth_token)


def _turso_url() -> str:
    """Convert libsql:// → https:// and append /v2/pipeline."""
    url = settings.turso_database_url or ""
    url = url.replace("libsql://", "https://").replace("ws://", "http://")
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/") + "/v2/pipeline"


def _encode_arg(val: Any) -> dict:
    """Encode a Python value to Turso typed arg."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": str(int(val))}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": str(val)}
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
# Singleton client
# ---------------------------------------------------------------------------

_client: Optional[TursoClient] = None


def _get_client() -> TursoClient:
    global _client
    if _client is not None:
        return _client
    if not DB_AVAILABLE:
        raise RuntimeError("Database not configured")
    _client = TursoClient(_turso_url(), settings.turso_auth_token)
    return _client


def get_db():
    """FastAPI Dependency — yields a TursoClient or None."""
    if not DB_AVAILABLE:
        yield None
        return
    yield _get_client()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA_STATEMENTS = [
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
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS demand (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        product_id TEXT NOT NULL,
        demand_qty REAL NOT NULL,
        destination_region TEXT NOT NULL,
        created_at TEXT NOT NULL
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
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS p2p_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_name TEXT NOT NULL DEFAULT 'default',
        case_id TEXT NOT NULL,
        activity TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        resource TEXT,
        cost REAL DEFAULT 0,
        created_at TEXT NOT NULL
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
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
    """CREATE TABLE IF NOT EXISTS order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        actor TEXT,
        note TEXT,
        timestamp TEXT NOT NULL
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
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_nip ON supplier_profiles(nip)",
]


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    if not DB_AVAILABLE:
        logger.info("Database not configured — running in demo-only mode")
        return

    client = _get_client()
    try:
        client.batch(_SCHEMA_STATEMENTS)
        logger.info("Database schema initialised (Turso HTTP API)")
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
