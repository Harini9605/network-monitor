"""
Pytest fixtures for the Network Monitor test suite.

The test database is chosen through the DATABASE_PATH environment
variable BEFORE the app module is imported (config.py reads it at
import time), so the suite always runs against an isolated SQLite file
and can never touch instance/network_monitor.db.
"""

import os
import tempfile

_TEST_DB = os.path.join(tempfile.gettempdir(), "network_monitor_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_PATH"] = _TEST_DB

import pytest

from config import BASE_DIR, Config
from app import app as flask_app

# Hard safety check: the suite must NEVER run against the real database.
_PRODUCTION_DB = os.path.join(BASE_DIR, "instance", "network_monitor.db")
assert Config.SQLITE_DB_PATH == _TEST_DB and _TEST_DB != _PRODUCTION_DB, (
    f"Test isolation broken: DATABASE_PATH points at {Config.SQLITE_DB_PATH}"
)


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret-key")
    yield flask_app
    # Reset device table so tests cannot leak into each other.
    from database import get_connection
    conn = get_connection()
    try:
        conn.execute("DELETE FROM devices")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    """Return (and create if needed) the session CSRF token."""

    def _get():
        with client.session_transaction() as sess:
            if not sess.get("_csrf_token"):
                sess["_csrf_token"] = "test-csrf-token"
            return sess["_csrf_token"]

    return _get


@pytest.fixture
def add_device():
    """Create a device through the real database layer; returns its id."""

    def _add(name, ip_address, device_type, hostname):
        from database import create_device
        return create_device(name=name, ip_address=ip_address,
                             device_type=device_type, hostname=hostname)

    return _add