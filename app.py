"""
app.py
------
Network Monitoring & Troubleshooting Dashboard
===============================================

A self-contained IT Support Engineer tool built with Flask + SQLite:

    * Device management (add / edit / delete / view) with IP and hostname
      validation and duplicate-IP protection.
    * Real connectivity monitoring using the operating system `ping`
      command - results are stored in SQLite, never fabricated.
    * A professional dashboard of real statistics (online / offline /
      errors / average response time / recent failures).
    * Hand-written troubleshooting guides with practical Windows commands
      (ping, ipconfig, tracert, nslookup, ...).
    * CSRF protection, parameterized SQL, friendly 404/500 pages.

Run locally:
    python app.py
    then open http://127.0.0.1:5000
"""

import secrets
import socket
from datetime import datetime

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from config import DevelopmentConfig
from database import (DEVICE_TYPES, count_devices, count_devices_by_status,
                      create_device, dashboard_stats, delete_device,
                      fetch_all_devices, fetch_device, init_db, ip_is_taken,
                      update_device, update_device_status, validate_device)
from monitor import ping_host
from troubleshooting import GUIDES, get_guide, guide_for_status

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)
init_db()


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    """Expose common values to every template."""
    return {
        "app_name": app.config.get("APP_NAME", "Network Monitor"),
        "refresh_interval": app.config.get("REFRESH_INTERVAL", 30),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": socket.gethostname(),
    }


def _nice_uptime(epoch_seconds: float) -> str:
    """Convert an epoch timestamp into a short 'up since' string."""
    dt = datetime.fromtimestamp(epoch_seconds)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


app.jinja_env.filters["dt"] = _nice_uptime


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------
def _get_csrf_token() -> str:
    """Create (and remember on first use) a per-session CSRF token."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = _get_csrf_token
app.jinja_env.globals["guide_for_status"] = guide_for_status


@app.before_request
def csrf_protect():
    """Reject POST requests that do not carry a valid CSRF token."""
    if request.method == "POST":
        token = session.get("_csrf_token")
        incoming = request.form.get("csrf_token")
        if not token or not incoming or not secrets.compare_digest(token, incoming):
            abort(400, description="Invalid or missing CSRF token.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Landing / dashboard page with real monitoring statistics."""
    stats = dashboard_stats()

    # Online vs Offline chart: proportional segments from real stored counts.
    checked = stats["checked"]
    if checked:
        chart = {
            "checked": checked,
            "segments": [
                {
                    "klass": "seg-online", "label": "Online",
                    "count": stats["online"],
                    "width": round(stats["online"] / checked * 100, 1),
                },
                {
                    "klass": "seg-offline", "label": "Offline",
                    "count": stats["offline"],
                    "width": round(stats["offline"] / checked * 100, 1),
                },
                {
                    "klass": "seg-error", "label": "Check errors",
                    "count": stats["errors"],
                    "width": round(stats["errors"] / checked * 100, 1),
                },
            ],
        }
    else:
        chart = {"checked": 0, "segments": []}

    # Response-time bars: width proportional to the slowest online device.
    max_ms = stats["max_response_ms"] or 1
    latencies = [
        {
            "name": device["name"],
            "ip_address": device["ip_address"],
            "response_ms": device["last_response_ms"],
            "width": round(device["last_response_ms"] / max_ms * 100, 1),
        }
        for device in stats["latencies"]
    ]

    return render_template(
        "index.html",
        stats=stats,
        chart=chart,
        latencies=latencies,
    )


@app.route("/devices")
def list_devices():
    """Show every saved device."""
    devices = fetch_all_devices()
    for device in devices:
        device["guide_slug"] = guide_for_status(device["last_status"])
    return render_template(
        "devices.html",
        devices=devices,
        device_types=DEVICE_TYPES,
    )


@app.route("/devices/new", methods=["GET", "POST"])
def new_device():
    """Add a new device."""
    if request.method == "POST":
        form = {
            "name": request.form.get("name", ""),
            "ip_address": request.form.get("ip_address", ""),
            "device_type": request.form.get("device_type", ""),
            "hostname": request.form.get("hostname", ""),
        }
        errors = validate_device(**form)
        if ip_is_taken(form["ip_address"]) and not errors:
            errors.append("A device with this IP address already exists.")
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "device_form.html", device=None, form=form,
                device_types=DEVICE_TYPES,
            )

        create_device(**form)
        flash(f"Device '{form['name'].strip()}' added successfully.", "success")
        return redirect(url_for("list_devices"))

    return render_template(
        "device_form.html", device=None, form={},
        device_types=DEVICE_TYPES,
    )


@app.route("/devices/<int:device_id>/edit", methods=["GET", "POST"])
def edit_device(device_id):
    """Edit an existing device."""
    device = fetch_device(device_id)
    if device is None:
        abort(404)

    if request.method == "POST":
        form = {
            "name": request.form.get("name", ""),
            "ip_address": request.form.get("ip_address", ""),
            "device_type": request.form.get("device_type", ""),
            "hostname": request.form.get("hostname", ""),
        }
        errors = validate_device(**form)
        if ip_is_taken(form["ip_address"], exclude_id=device_id) and not errors:
            errors.append("A device with this IP address already exists.")
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "device_form.html", device=device, form=form,
                device_types=DEVICE_TYPES,
            )

        update_device(device_id, **form)
        flash(f"Device '{form['name'].strip()}' updated successfully.", "success")
        return redirect(url_for("list_devices"))

    return render_template(
        "device_form.html", device=device, form=dict(device),
        device_types=DEVICE_TYPES,
    )


@app.route("/devices/<int:device_id>/delete", methods=["POST"])
def delete_device_route(device_id):
    """Delete a device."""
    device = fetch_device(device_id)
    if device is None:
        abort(404)

    delete_device(device_id)
    flash(f"Device '{device['name']}' deleted.", "info")
    return redirect(url_for("list_devices"))


@app.route("/devices/<int:device_id>/check", methods=["POST"])
def check_device_route(device_id):
    """Run a real connectivity check on one device and store the result."""
    device = fetch_device(device_id)
    if device is None:
        abort(404)

    result = ping_host(device["ip_address"])
    update_device_status(device_id, result["status"], result["response_ms"])

    label = {"online": "ONLINE", "offline": "OFFLINE", "error": "CHECK ERROR"}.get(
        result["status"], result["status"].upper()
    )
    detail = result["detail"]
    if result["response_ms"] is not None:
        detail = f"{detail} Response time: {result['response_ms']} ms."

    flash(
        f"{device['name']} ({device['ip_address']}) is {label}. {detail}",
        "success" if result["status"] == "online" else "warning",
    )
    return redirect(url_for("list_devices"))


@app.route("/troubleshooting")
def troubleshooting():
    """Index of troubleshooting guides for common network problems."""
    return render_template("troubleshooting.html", guides=GUIDES)


@app.route("/troubleshooting/<slug>")
def troubleshooting_detail(slug):
    """Full troubleshooting guide for one specific problem."""
    guide = get_guide(slug)
    if guide is None:
        abort(404)
    return render_template("troubleshooting_detail.html", guide=guide)


@app.route("/health")
def health():
    """Lightweight health check used by load balancers or scripts."""
    return jsonify(
        {
            "status": "ok",
            "app": app.config.get("APP_NAME"),
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@app.errorhandler(400)
def bad_request(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Bad request"}), 400
    return render_template("error.html", code=400,
                           title="Bad request",
                           message="The request was invalid (e.g. a missing security token)."), 400


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", code=404,
                           title="Page not found",
                           message="The page you are looking for does not exist."), 404


@app.errorhandler(500)
def server_error(_e):
    return render_template("error.html", code=500, title="Server error",
                           message="Something went wrong on our side. Please try again later."), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)