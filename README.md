# Network Monitoring & Troubleshooting Dashboard

A self-contained **IT Support Engineer** tool written in Python + Flask + SQLite.
It tracks network devices, runs **real** `ping` checks against them, stores the
results in a local database, and shows them on a professional dashboard — with
hand-written troubleshooting guides for the most common network problems.

Everything runs locally with zero external services. No AI APIs, no fake
monitoring data, no cloud accounts required.

---

## Features

- **Device management** — add, edit, delete and view network devices (PC, server,
  router, switch, printer, other) with IP and hostname validation and
  duplicate-IP protection.
- **Real connectivity monitoring** — each device is checked with the operating
  system's own `ping` command. Results are real: Online, Offline, or Check error,
  including response time in milliseconds and the last-checked timestamp.
- **One-click "Check now"** — run a live ping against any device and store the result.
- **Professional dashboard** — total / online / offline / check errors / not-checked
  counts, average response time, an Online-vs-Offline chart, response-time bars and
  a list of recent connectivity failures — all computed only from stored results.
- **Troubleshooting assistant** — 5 practical guides (device offline, high response
  time, invalid IP, network unreachable, ping timeout) with possible causes,
  recommended steps and real commands an IT Support Engineer can try
  (`ping`, `ipconfig`, `tracert`, `nslookup`, `arp`, `netstat`, ...).
- **Reliable by design** — CSRF protection on every POST, fully parameterized SQL
  queries (no SQL injection), defensive ping handling (timeout, invalid IP,
  missing executable) that never crashes the app, and friendly 404/500 pages.

## Technology stack

| Piece | Choice |
| --- | --- |
| Language | Python 3.9+ |
| Web framework | Flask |
| Database | SQLite (Python's built-in `sqlite3` module — no ORM) |
| Frontend | Bootstrap 5 (CDN) + a small custom CSS file |
| Tests | pytest (test database is fully isolated from the real one) |
| OS | Windows first (the ping logic also works on Linux/macOS) |

## Project structure

```
network-monitor/
├── app.py                # Flask application, routes, error handlers, CSRF
├── config.py             # Configuration (paths, secret key, refresh interval)
├── database.py           # SQLite schema, validation, CRUD, dashboard stats
├── monitor.py            # Real ping implementation (subprocess, defensive)
├── troubleshooting.py    # Hand-written troubleshooting guides (static data)
├── requirements.txt      # Runtime dependencies (Flask)
├── requirements-dev.txt  # Development dependencies (pytest)
├── pytest.ini            # Pytest configuration
├── .gitignore
├── instance/
│   └── network_monitor.db  # The real database (created automatically, git-ignored)
├── static/
│   ├── css/style.css     # Custom styles (badges, charts, guides)
│   └── js/main.js        # Small behaviour file
├── templates/
│   ├── base.html         # Layout + navigation + flash messages
│   ├── index.html        # Dashboard with real statistics
│   ├── devices.html      # Device list with status + Check now
│   ├── device_form.html  # Add / edit device form
│   ├── troubleshooting.html        # Guide index
│   ├── troubleshooting_detail.html # Full guide for one problem
│   └── error.html        # 400 / 404 / 500 pages
├── tests/
│   ├── conftest.py       # Test fixtures + DB-isolation guard
│   └── test_app.py       # 27 automated tests
└── README.md
```

## Installation

1. Install Python 3.9 or newer from [python.org](https://www.python.org/).
2. Open a terminal (PowerShell on Windows) in the project folder.
3. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   .\venv\Scripts\activate        # Windows
   source venv/bin/activate       # Linux / macOS
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## How to run

```bash
python app.py
```

Then open <http://127.0.0.1:5000> in your browser.

- The SQLite database is created automatically at `instance/network_monitor.db`
  on first launch.
- Stop the server with `Ctrl+C`.

## How to use

1. Open the **Devices** page and click **+ Add device**.
2. Enter a device name, a valid IPv4/IPv6 address, a type and a hostname.
   Duplicate IP addresses are rejected.
3. Click **Check now** on any row to run a **real** ping and store the result.
   The Status badge changes to Online (green), Offline (red) or Check error (amber).
4. Open the **Dashboard** to see the real statistics: how many devices are online,
   average response time, the Online-vs-Offline chart and recent failures.
5. On any failing device, click **Troubleshoot** (or open the **Troubleshooting**
   link in the navigation) to read practical steps and commands to try.

### Example monitoring workflow

```
1. Add the HR printer        -> 192.168.1.50 / hr-printer-01
2. "Check now"               -> online, 8 ms
3. Next week printer silent  -> "Check now" again -> offline
4. Dashboard > Recent connectivity failures shows the printer
5. Click "Troubleshoot"      -> "Device appears offline" guide
6. Run "ping 192.168.1.50", "arp -a", "ping <gateway>"
7. Fix the issue (cable / power / firewall), press "Check now" -> online again
```

## Testing instructions

The test suite runs against a **separate temporary database** and will never
delete or modify the real `instance/network_monitor.db` (a guard in
`tests/conftest.py` enforces this).

```bash
pip install -r requirements-dev.txt
python -m pytest tests -v
```

Run from the `network-monitor` folder. Expected result: **27 passed**.

## IT Support use cases

- **Quick triage** — a user says "the printer doesn't work". Open this tool,
  find the printer, press **Check now**, and immediately know whether the device
  is reachable and how fast it responds.
- **Fault isolation** — check several devices around a problem area; online
  neighbours with an offline target identify the broken device or cable instead
  of guessing.
- **Documenting incidents** — the dashboard records the last result and timestamp
  for every device, so support tickets can reference observed offline/error states.
- **Preparing for the network guy** — the troubleshooting guides turn a status into
  a plan of action (`ping`, `ipconfig`, `tracert`, `nslookup`) you already tried.

## GitHub preparation

1. Create a new repository on GitHub (do **not** tick "Add a README").
2. In the project folder run the commands below (see the exact list in the
   handoff notes): `git init`, `git add .`, `git commit`, set the `main` branch
   and paste your repository URL as the `origin` remote, then push.

---

Built with Flask + SQLite for an IT Support Engineer portfolio.