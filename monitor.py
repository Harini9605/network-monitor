"""
monitor.py
----------
Real network connectivity checks using the operating system's `ping`
command. No external libraries, works on Windows (and Unix-like hosts).

Windows command used:
    ping -n 1 -w <timeout_ms> <ip>
    -n 1   : send a single echo request
    -w ms  : wait at most ms milliseconds for a reply (Windows)

Statuses returned:
    online  - a reply was received (response_ms contains the RTT)
    offline - no reply / timeout / destination unreachable
    error   - the check itself could not run (invalid address, missing ping)

Everything is defensive: any platform difference, timeout or missing
binary is turned into a structured result instead of an exception, so
the web application can never crash because one device is unreachable.
"""

import ipaddress
import platform
import re
import subprocess

# Milliseconds to wait per ping attempt.
PING_TIMEOUT_MS = 1000

# Matches the response time shown by `ping`, e.g. "time=1ms", "time<1ms".
_TIME_RE = re.compile(rb"time[=<]\s*(\d+)\s*ms", re.IGNORECASE)


def ping_host(ip_address: str, timeout_ms: int = PING_TIMEOUT_MS) -> dict:
    """Ping one IP address and return a structured result dict.

    Returns:
        {"status": "online"|"offline"|"error",
         "response_ms": int|None,
         "detail": human-readable explanation}
    """

    # Safety: only attempt real checks on a syntactically valid address.
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return {
            "status": "error",
            "response_ms": None,
            "detail": f"'{ip_address}' is not a valid IP address.",
        }

    timeout_ms = max(1, int(timeout_ms))
    windows = platform.system().lower() == "windows"

    if windows:
        command = ["ping", "-n", "1", "-w", str(timeout_ms), ip_address]
        # Avoid popping up a console window for the subprocess on Windows.
        flags = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    else:
        # Unix-like systems use -c (count) and -W (timeout in seconds).
        command = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip_address]
        flags = {}

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            timeout=max(2 * timeout_ms, 3000),
            **flags,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "offline",
            "response_ms": None,
            "detail": "No reply (ping timed out).",
        }
    except (OSError, ValueError):
        # e.g. the ping binary does not exist on this machine.
        return {
            "status": "error",
            "response_ms": None,
            "detail": "Could not run a connectivity check on this host.",
        }

    return _parse_ping_result(proc.returncode, proc.stdout + proc.stderr)


def _parse_ping_result(returncode: int, output: bytes) -> dict:
    """Turn a raw ping exit code + output into a structured result.

    Separated from ping_host() so it can be unit-tested directly.
    The exit code is authoritative for reachability (locale-independent);
    the RTT is parsed from the output when present.
    """

    text = (output or b"").decode("utf-8", errors="ignore").lower()
    match = _TIME_RE.search(output or b"")
    response_ms = int(match.group(1)) if match else None

    if returncode == 0:
        # Reply received. Windows prints the RTT as part of the reply line.
        return {
            "status": "online",
            "response_ms": response_ms if response_ms is not None else 0,
            "detail": "Device responded to the ping request.",
        }

    # Non-zero exit: figure out a friendly reason from the output.
    if "destination host unreachable" in text or "unreachable" in text:
        detail = "Destination host unreachable."
    elif "request timed out" in text or "timed out" in text:
        detail = "No reply (request timed out)."
    elif "could not find host" in text:
        detail = "Host could not be resolved."
    else:
        detail = "No reply from the device."

    return {"status": "offline", "response_ms": None, "detail": detail}