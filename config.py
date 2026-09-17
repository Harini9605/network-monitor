"""
config.py
---------
Application configuration for the Network Monitoring & Troubleshooting
Dashboard.

Kept separate so settings are easy to find and change. Environment
variables can override values, which is useful when deploying.
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared by all environments."""

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # In production this MUST be replaced with a long random value,
    # e.g.  python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get("SECRET_KEY", "network-monitor-dev-key-change-me")

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME = "Network Monitor"
    # Interval (seconds) the browser will refresh dashboards with.
    REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "30"))

    # ------------------------------------------------------------------
    # Flask
    # ------------------------------------------------------------------
    JSON_SORT_KEYS = False  # keep API payloads in a predictable order

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # SQLite stores device records and, later, historical monitoring data.
    # The database file lives in instance/ (git-ignored). Access is handled
    # by database.py using Python's built-in sqlite3 module and fully
    # parameterized queries — no ORM, no extra dependencies.
    INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    SQLITE_DB_PATH = os.environ.get(
        "DATABASE_PATH",
        os.path.join(INSTANCE_DIR, "network_monitor.db"),
    )


class DevelopmentConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"