"""
test_app.py - automated tests for the Network Monitoring Dashboard.

Coverage:
    * Device CRUD, validation and duplicate-IP protection
    * Ping result handling (mocked subprocess) + status persistence
    * Dashboard statistics and route rendering (empty + populated states)
    * Troubleshooting pages and guide mapping
    * Error cases (CSRF rejection, 404 pages)
    * Schema migration + test-database isolation guards

The suite always runs against a separate temporary SQLite file (set in
tests/conftest.py via DATABASE_PATH before the app is imported).

Run with:  python -m pytest tests -v
"""

import os
import sqlite3
from unittest import mock

import monitor
from database import (dashboard_stats, fetch_all_devices, fetch_device,
                      init_db, update_device_status)
from troubleshooting import GUIDES, guide_for_status


def _post(client, url, csrf, **data):
    data["csrf_token"] = csrf()
    return client.post(url, data=data)


# ---------------------------------------------------------------------------
# Connectivity result parsing (mock the subprocess, never touch the network)
# ---------------------------------------------------------------------------
def _mock_ping(returncode, output):
    proc = mock.Mock()
    proc.returncode = returncode
    proc.stdout = output
    proc.stderr = b""
    return mock.patch("monitor.subprocess.run", return_value=proc)


def test_ping_online_parses_latency():
    with _mock_ping(0, b"Reply from 127.0.0.1: bytes=32 time=2ms TTL=64"):
        result = monitor.ping_host("127.0.0.1")
    assert result["status"] == "online"
    assert result["response_ms"] == 2


def test_ping_online_submillisecond():
    with _mock_ping(0, b"Reply from 127.0.0.1: bytes=32 time<1ms TTL=128"):
        result = monitor.ping_host("127.0.0.1")
    assert result["status"] == "online"


def test_ping_timeout_is_offline():
    with _mock_ping(1, b"Request timed out."):
        result = monitor.ping_host("192.0.2.10")
    assert result["status"] == "offline"
    assert result["response_ms"] is None


def test_ping_unreachable_is_offline():
    with _mock_ping(1, b"Reply from 10.0.0.1: Destination host unreachable."):
        result = monitor.ping_host("10.0.0.99")
    assert result["status"] == "offline"
    assert result["response_ms"] is None


def test_ping_missing_binary_is_error():
    with mock.patch("monitor.subprocess.run", side_effect=FileNotFoundError):
        result = monitor.ping_host("127.0.0.1")
    assert result["status"] == "error"
    assert result["response_ms"] is None


def test_ping_invalid_ip_never_runs_command():
    with mock.patch("monitor.subprocess.run",
                    side_effect=AssertionError("must not run")):
        result = monitor.ping_host("999.1.1.1")
    assert result["status"] == "error"
    assert "not a valid IP" in result["detail"]


# ---------------------------------------------------------------------------
# Check Now route (mock ping) persists real results to SQLite
# ---------------------------------------------------------------------------
def test_check_now_online_persists_status(client, csrf, add_device):
    device_id = add_device("Loopback", "127.0.0.1", "Server", "localhost")
    with mock.patch("app.ping_host", return_value={
            "status": "online", "response_ms": 12, "detail": "Device responded."}):
        resp = _post(client, f"/devices/{device_id}/check", csrf)
    assert resp.status_code == 302
    device = fetch_device(device_id)
    assert device["last_status"] == "online"
    assert device["last_response_ms"] == 12
    assert device["last_checked_at"] is not None


def test_check_now_offline_persists_status(client, csrf, add_device):
    device_id = add_device("Dark router", "192.0.2.7", "Router", "edge-7")
    with mock.patch("app.ping_host", return_value={
            "status": "offline", "response_ms": None, "detail": "No reply."}):
        resp = _post(client, f"/devices/{device_id}/check", csrf)
    assert resp.status_code == 302
    device = fetch_device(device_id)
    assert device["last_status"] == "offline"
    assert device["last_response_ms"] is None


def test_check_now_error_persists_status(client, csrf, add_device):
    device_id = add_device("Odd device", "999.1.1.1", "Other", "odd-1")
    with mock.patch("app.ping_host", return_value={
            "status": "error", "response_ms": None, "detail": "invalid IP"}):
        resp = _post(client, f"/devices/{device_id}/check", csrf)
    assert resp.status_code == 302
    assert fetch_device(device_id)["last_status"] == "error"


def test_check_now_missing_device_404(client, csrf):
    assert _post(client, "/devices/999/check", csrf).status_code == 404


# ---------------------------------------------------------------------------
# Schema migration + database isolation
# ---------------------------------------------------------------------------
def test_migration_adds_monitor_columns():
    db_path = os.environ["DATABASE_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS devices")
    conn.execute(
        "CREATE TABLE devices ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL, ip_address TEXT NOT NULL UNIQUE,"
        "device_type TEXT NOT NULL, hostname TEXT NOT NULL,"
        "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO devices (name, ip_address, device_type, hostname) "
                 "VALUES ('Old Device', '10.1.1.1', 'PC', 'old-pc')")
    conn.commit()
    conn.close()

    init_db()  # must add columns and keep the row

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devices)")}
    row = conn.execute("SELECT name, last_status FROM devices WHERE id = 1").fetchone()
    assert row[0] == "Old Device", "migration lost existing data"
    assert row[1] is None, "migrated device should have no status yet"
    # No app fixture here: remove the leftover row so other tests stay isolated.
    conn.execute("DELETE FROM devices")
    conn.commit()
    conn.close()

    for column in ("last_status", "last_response_ms", "last_checked_at"):
        assert column in cols, f"column {column} missing after migration"


def test_database_is_isolated_from_production():
    from config import BASE_DIR, Config
    production = os.path.join(BASE_DIR, "instance", "network_monitor.db")
    assert Config.SQLITE_DB_PATH != production
    assert os.environ["DATABASE_PATH"] != production


# ---------------------------------------------------------------------------
# Dashboard statistics (real stored data only)
# ---------------------------------------------------------------------------
def _seed_mixed_devices(add_device):
    online = add_device("Loopback", "127.0.0.1", "Server", "localhost")
    offline = add_device("Dark router", "192.0.2.7", "Router", "edge-7")
    broken = add_device("Odd PC", "999.1.1.1", "PC", "odd-pc")
    add_device("New printer", "10.0.0.50", "Printer", "hr-printer")  # not checked
    update_device_status(online, "online", 12)
    update_device_status(offline, "offline")
    update_device_status(broken, "error")
    return online, offline, broken


def test_dashboard_stats_aggregates_real_data(client, add_device):
    _seed_mixed_devices(add_device)
    stats = dashboard_stats()
    assert stats["total"] == 4
    assert stats["online"] == 1
    assert stats["offline"] == 1
    assert stats["errors"] == 1
    assert stats["not_checked"] == 1
    assert stats["checked"] == 3
    assert stats["avg_response_ms"] == 12.0
    assert stats["max_response_ms"] == 12
    assert stats["last_checked_at"] is not None
    assert {f["name"] for f in stats["failures"]} == {"Dark router", "Odd PC"}
    assert [f["last_status"] for f in stats["failures"]] in (
        ["offline", "error"], ["error", "offline"],
    ) or stats["failures"]  # order depends on same-second timestamps


def test_dashboard_stats_empty_database(client):
    stats = dashboard_stats()
    assert stats["total"] == 0
    assert stats["online"] == stats["offline"] == 0
    assert stats["errors"] == stats["not_checked"] == 0
    assert stats["avg_response_ms"] is None
    assert stats["failures"] == []
    assert stats["latencies"] == []


def test_dashboard_route_shows_real_statistics(client, add_device):
    _seed_mixed_devices(add_device)
    resp = client.get("/")
    data = resp.data.decode()
    assert resp.status_code == 200
    assert "Total devices" in data
    assert "Avg response" in data
    assert "Online vs Offline" in data
    assert "Recent connectivity failures" in data
    assert "Dark router" in data          # a real offline failure is listed
    assert "Odd PC" in data               # a real check error is listed
    assert "Troubleshoot" in data         # failures link to a guide


def test_dashboard_route_empty_state(client):
    resp = client.get("/")
    data = resp.data.decode()
    assert resp.status_code == 200
    assert "Nothing to report yet" in data
    assert "No connectivity checks" in data or "Add device" in data


# ---------------------------------------------------------------------------
# Troubleshooting pages and guide data
# ---------------------------------------------------------------------------
def test_troubleshooting_index_lists_guides(client):
    resp = client.get("/troubleshooting")
    data = resp.data.decode()
    assert resp.status_code == 200
    for guide in GUIDES:
        assert guide["title"] in data


def test_troubleshooting_detail_pages_render(client):
    for guide in GUIDES:
        resp = client.get(f"/troubleshooting/{guide['slug']}")
        data = resp.data.decode()
        assert resp.status_code == 200, f"{guide['slug']} should exist"
        assert guide["title"] in data
        assert "Recommended troubleshooting steps" in data
        assert "Commands an IT Support Engineer can try" in data


def test_troubleshooting_unknown_slug_404(client):
    assert client.get("/troubleshooting/bogus-slug").status_code == 404


def test_guides_are_well_formed():
    from troubleshooting import get_guide
    slugs = [g["slug"] for g in GUIDES]
    assert len(GUIDES) == 5
    assert len(set(slugs)) == len(slugs), "guide slugs must be unique"
    for guide in GUIDES:
        assert get_guide(guide["slug"]) is guide
        for key in ("title", "summary", "severity", "causes", "steps", "commands"):
            assert key in guide
        assert guide["causes"] and guide["steps"] and guide["commands"]


def test_guide_status_mapping():
    assert guide_for_status("offline") == "device-offline"
    assert guide_for_status("error") == "invalid-ip"
    assert guide_for_status("online") is None
    assert guide_for_status(None) is None


def test_device_row_links_to_guide(client, csrf, add_device):
    device_id = add_device("Dark router", "192.0.2.7", "Router", "edge-7")
    with mock.patch("app.ping_host", return_value={
            "status": "offline", "response_ms": None, "detail": "No reply."}):
        _post(client, f"/devices/{device_id}/check", csrf)
    data = client.get("/devices").data.decode()
    assert "/troubleshooting/device-offline" in data


# ---------------------------------------------------------------------------
# CRUD + validation + error cases
# ---------------------------------------------------------------------------
def test_crud_flow_still_works(client, csrf):
    # Add
    resp = _post(client, "/devices/new", csrf,
                 name="Core Switch", ip_address="10.0.0.1",
                 device_type="Switch", hostname="core-sw")
    assert resp.status_code == 302
    devices = fetch_all_devices()
    assert len(devices) == 1
    device_id = devices[0]["id"]

    # Duplicate IP rejected (new device with the same IP)
    resp = _post(client, "/devices/new", csrf,
                 name="Copy", ip_address="10.0.0.1",
                 device_type="Other", hostname="copy-1")
    assert b"already exists" in resp.data

    # Validation: missing name + bad hostname rejected
    resp = _post(client, "/devices/new", csrf,
                 name="", ip_address="not-an-ip",
                 device_type="Other", hostname="bad_hostname")
    body = resp.data.decode().lower()
    assert "device name is required" in body
    assert "not a valid ip" in body
    assert "invalid" in body or "hostname is invalid" in body

    # View / edit
    resp = client.get(f"/devices/{device_id}/edit")
    assert b'value="Core Switch"' in resp.data
    resp = _post(client, f"/devices/{device_id}/edit", csrf,
                 name="Core Switch v2", ip_address="10.0.0.2",
                 device_type="Switch", hostname="core-sw2")
    assert resp.status_code == 302
    assert fetch_device(device_id)["name"] == "Core Switch v2"

    # Duplicate IP rejected on edit (excluding self is allowed)
    resp = _post(client, f"/devices/{device_id}/edit", csrf,
                 name="Core Switch v2", ip_address="10.0.0.2",
                 device_type="Switch", hostname="core-sw2")
    assert resp.status_code == 302  # same IP, same device -> allowed

    # Delete
    resp = _post(client, f"/devices/{device_id}/delete", csrf)
    assert resp.status_code == 302
    assert fetch_device(device_id) is None
    assert fetch_all_devices() == []


def test_missing_devices_return_404(client, csrf):
    assert client.get("/devices/999/edit").status_code == 404
    assert _post(client, "/devices/999/edit", csrf,
                 name="X", ip_address="1.1.1.1",
                 device_type="Other", hostname="x-1").status_code == 404
    assert _post(client, "/devices/999/delete", csrf).status_code == 404


def test_post_without_csrf_token_is_rejected(client):
    resp = client.post("/devices/new", data={
        "name": "No token",
        "ip_address": "10.0.0.9",
        "device_type": "Other",
        "hostname": "no-token",
    })
    assert resp.status_code == 400


def test_unknown_page_renders_friendly_404(client):
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"