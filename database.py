"""
database.py
-----------
SQLite data layer for device management.

Design decisions
----------------
* Uses Python's built-in ``sqlite3`` module — no ORM, no extra packages.
* Every query uses ``?`` placeholder parameters (parameterized SQL) to
  prevent SQL injection.
* Validation lives next to the persistence code so business rules are
  easy to find, test and reuse from both the web UI and future APIs.
"""

import ipaddress
import re
import sqlite3

from config import Config

# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------
DEVICE_TYPES = ["PC", "Server", "Router", "Switch", "Printer", "Other"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    ip_address       TEXT NOT NULL UNIQUE,
    device_type      TEXT NOT NULL,
    hostname         TEXT NOT NULL,
    last_status      TEXT,
    last_response_ms INTEGER,
    last_checked_at  TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after the first release. Kept here so init_db() can upgrade
# an existing database file without losing data (simple ALTER TABLE migration).
_LATE_COLUMNS = {
    "last_status": "ALTER TABLE devices ADD COLUMN last_status TEXT",
    "last_response_ms": "ALTER TABLE devices ADD COLUMN last_response_ms INTEGER",
    "last_checked_at": "ALTER TABLE devices ADD COLUMN last_checked_at TEXT",
}

# Valid latest-check statuses produced by monitor.py.
MONITOR_STATUSES = ["online", "offline", "error"]

# RFC 1123 hostname: labels of letters/digits/hyphens, max 253 chars.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*$"
)


def get_connection() -> sqlite3.Connection:
    """Return a connection with row access and foreign keys enabled."""
    conn = sqlite3.connect(Config.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist and apply safe column migrations
    so databases created by earlier stages keep working (idempotent)."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the first release, if missing."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(devices)")}
    for column, ddl in _LATE_COLUMNS.items():
        if column not in existing:
            conn.execute(ddl)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_device(name, ip_address, device_type, hostname) -> list:
    """Validate device fields.

    Returns a list of human-readable error messages. An empty list means
    the data is valid.
    """

    errors = []
    name = (name or "").strip()
    ip_address = (ip_address or "").strip()
    hostname = (hostname or "").strip()

    if not name:
        errors.append("Device name is required.")
    elif len(name) > 50:
        errors.append("Device name must be 50 characters or fewer.")

    if not ip_address:
        errors.append("IP address is required.")
    else:
        try:
            ipaddress.ip_address(ip_address)  # accepts IPv4 and IPv6
        except ValueError:
            errors.append(f"'{ip_address}' is not a valid IP address.")

    if device_type not in DEVICE_TYPES:
        errors.append("Please select a valid device type.")

    if not hostname:
        errors.append("Hostname is required.")
    elif len(hostname) > 253 or not _HOSTNAME_RE.match(hostname):
        errors.append(
            "Hostname is invalid (use letters, digits and hyphens, e.g. hr-printer-01)."
        )

    return errors


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------
_DEVICE_COLUMNS = (
    "id, name, ip_address, device_type, hostname, "
    "last_status, last_response_ms, last_checked_at, created_at, updated_at"
)


def fetch_all_devices() -> list:
    """Return every saved device with its latest monitoring result, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {_DEVICE_COLUMNS} FROM devices ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def fetch_device(device_id: int):
    """Return one device as a dict, or None when it does not exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT {_DEVICE_COLUMNS} FROM devices WHERE id = ?",
            (device_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_devices() -> int:
    """Total number of saved devices (used by the dashboard)."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) FROM devices").fetchone()
        return int(row[0])
    finally:
        conn.close()


def count_devices_by_status(status: str) -> int:
    """Number of devices whose latest check produced the given status."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE last_status = ?", (status,)
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def ip_is_taken(ip_address: str, exclude_id: int | None = None) -> bool:
    """Return True when the IP is already used by another device."""
    conn = get_connection()
    try:
        if exclude_id is None:
            row = conn.execute(
                "SELECT 1 FROM devices WHERE ip_address = ?", (ip_address,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM devices WHERE ip_address = ? AND id != ?",
                (ip_address, exclude_id),
            ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------
def create_device(name, ip_address, device_type, hostname) -> int:
    """Insert a new device and return its id (the caller validates first)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO devices (name, ip_address, device_type, hostname) "
            "VALUES (?, ?, ?, ?)",
            (name.strip(), ip_address.strip(), device_type, hostname.strip()),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def update_device(device_id: int, name, ip_address, device_type, hostname) -> None:
    """Update an existing device by id (idempotent, safe when no rows match)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE devices SET name = ?, ip_address = ?, device_type = ?, "
            "hostname = ?, updated_at = datetime('now') WHERE id = ?",
            (name.strip(), ip_address.strip(), device_type, hostname.strip(), device_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_device(device_id: int) -> None:
    """Remove a device by id (idempotent, safe when no rows match)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
    finally:
        conn.close()


def update_device_status(device_id: int, status: str, response_ms: int | None = None) -> None:
    """Record the latest connectivity-check result on a device."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE devices SET last_status = ?, last_response_ms = ?, "
            "last_checked_at = datetime('now') WHERE id = ?",
            (status, response_ms, device_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dashboard aggregation (all numbers come from real stored results)
# ---------------------------------------------------------------------------
def dashboard_stats() -> dict:
    """Aggregate the monitoring data stored in SQLite for the dashboard.

    Every value is computed from the real `last_status` / `last_response_ms`
    / `last_checked_at` columns - no data is fabricated.

    Returns a flat dict: total, online, offline, errors, not_checked, checked,
    avg_response_ms, max_response_ms, last_checked_at, failures, latencies.
    """
    conn = get_connection()
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0])
        counts = {
            (row["last_status"] or "not_checked"): row["total"]
            for row in conn.execute(
                "SELECT last_status, COUNT(*) AS total FROM devices "
                "GROUP BY last_status"
            )
        }
        online = int(counts.get("online", 0))
        offline = int(counts.get("offline", 0))
        errors = int(counts.get("error", 0))
        not_checked = int(counts.get("not_checked", 0))
        checked = online + offline + errors

        row = conn.execute(
            "SELECT AVG(last_response_ms) AS avg_ms, MAX(last_response_ms) AS max_ms "
            "FROM devices WHERE last_status = 'online' AND last_response_ms IS NOT NULL"
        ).fetchone()
        avg_response_ms = round(row["avg_ms"], 1) if row and row["avg_ms"] is not None else None
        max_response_ms = int(row["max_ms"]) if row and row["max_ms"] is not None else None

        last_checked = conn.execute(
            "SELECT MAX(last_checked_at) FROM devices WHERE last_checked_at IS NOT NULL"
        ).fetchone()[0]

        failures = [
            dict(r)
            for r in conn.execute(
                f"SELECT {_DEVICE_COLUMNS} FROM devices "
                "WHERE last_status IN ('offline', 'error') "
                "ORDER BY last_checked_at DESC, id DESC LIMIT 6"
            )
        ]

        latencies = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, ip_address, last_response_ms FROM devices "
                "WHERE last_status = 'online' AND last_response_ms IS NOT NULL "
                "ORDER BY last_response_ms DESC LIMIT 8"
            )
        ]
        if latencies and max_response_ms is None:
            max_response_ms = max(r["last_response_ms"] for r in latencies)

        return {
            "total": total,
            "online": online,
            "offline": offline,
            "errors": errors,
            "not_checked": not_checked,
            "checked": checked,
            "avg_response_ms": avg_response_ms,
            "max_response_ms": max_response_ms,
            "last_checked_at": last_checked,
            "failures": failures,
            "latencies": latencies,
        }
    finally:
        conn.close()