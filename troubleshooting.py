"""
troubleshooting.py
------------------
Hand-written guidance library for common network problems an IT Support
Engineer runs into while using this dashboard.

Every guide contains:
    slug     - unique id used in URLs (e.g. /troubleshooting/device-offline)
    title    - short human-readable title
    summary  - when this guide applies
    severity - low / medium / high (shown as a badge)
    causes   - possible root causes to check
    steps    - recommended troubleshooting steps, in order
    commands - real commands to try (ping, ipconfig, tracert, nslookup, ...)

No AI APIs, no network calls: the content is static and the application
simply renders the right guide for the current stored status.
"""


def get_guide(slug: str) -> dict | None:
    """Return the guide dict for a slug, or None when it does not exist."""
    for guide in GUIDES:
        if guide["slug"] == slug:
            return guide
    return None


def guide_for_status(status: str | None) -> str | None:
    """Map a stored device status to the most relevant guide slug.

    Returns None for healthy / un-checked devices (nothing to troubleshoot).
    """
    return {
        "offline": "device-offline",
        "error": "invalid-ip",
    }.get(status)


GUIDES = [
    {
        "slug": "device-offline",
        "title": "Device appears offline",
        "summary": (
            "A saved device did not answer the latest ping (last status: OFFLINE). "
            "The machine may be off, disconnected, sleeping, or configured to ignore "
            "ping (ICMP echo) requests."
        ),
        "severity": "high",
        "causes": [
            "The device is powered off or in sleep/hibernate mode.",
            "The network cable or Wi-Fi connection is down.",
            "The device's IP address changed (DHCP lease renewed with a new address).",
            "A firewall on the device blocks ICMP echo requests (ping).",
            "The device is on a different VLAN/subnet and routing is broken.",
        ],
        "steps": [
            "Confirm the device is powered on and the OS is fully loaded.",
            "On the device, open a command prompt and run `ipconfig` to confirm it has "
            "a valid IP address and the default gateway is set.",
            "From the monitoring PC, ping the device again; if it still fails, ping "
            "the device's IP from a second computer to rule out this PC's network.",
            "Verify DNS/external connectivity of the monitoring host first - if the "
            "whole network is down, every device will look offline.",
            "Check whether other devices on the same switch/VLAN respond. This "
            "isolates the fault to this device vs. the network path.",
            "If the device only ignores ping (other services work), ping is blocked "
            "by its firewall - use the tracked service/port instead.",
        ],
        "commands": [
            {"cmd": "ping <device-ip>", "what": "Basic reachability test from this PC."},
            {"cmd": "ipconfig", "what": "Show local IP, subnet mask and default gateway on the affected machine."},
            {"cmd": "tracert <device-ip>", "what": "Trace the path to the device and find where packets stop."},
            {"cmd": "arp -a", "what": "Check the ARP table - an entry means the device is on the L2 network."},
            {"cmd": "ping <default-gateway-ip>", "what": "Confirm the local network and gateway are up."},
        ],
    },
    {
        "slug": "high-response-time",
        "title": "High response time (slow device)",
        "summary": (
            "The device replies, but slower than expected. High latency usually points "
            "to an overloaded endpoint or a sluggish network segment rather than a "
            "dead device."
        ),
        "severity": "medium",
        "causes": [
            "The device CPU/network interface is saturated (busy application, backup job).",
            "Wi-Fi interference or a weak wireless signal.",
            "A congested uplink, switch port or firewall path.",
            "Wrong duplex/speed settings between the device and the switch.",
            "Network delay from distance/routing (normal for remote sites).",
        ],
        "steps": [
            "Run several pings in a row and look for a pattern: always slow, "
            "sometimes slow, or normal but with occasional spikes.",
            "Identify whether latency is only on this device (compare against a "
            "neighbour on the same switch).",
            "On the switch, check the port for errors, CRC failures and duplex mismatch.",
            "During a slow period, run tracert to see whether the delay is at the "
            "device or somewhere along the path.",
            "Check resource usage (CPU/memory/disk) on the device if you have access.",
        ],
        "commands": [
            {"cmd": "ping -n 20 <device-ip>", "what": "20 quick pings - shows min/max/average and packet loss."},
            {"cmd": "tracert <device-ip>", "what": "Find which hop adds most of the delay."},
            {"cmd": "netstat -e", "what": "Shows interface error statistics on a Windows host."},
            {"cmd": "taskmgr / performance tab", "what": "Check live CPU, memory and network usage on the device."},
        ],
    },
    {
        "slug": "invalid-ip",
        "title": "Invalid IP address on record",
        "summary": (
            "The saved IP address is not a syntactically valid IPv4/IPv6 address, so a "
            "ping can never run. This is usually a data-entry problem."
        ),
        "severity": "low",
        "causes": [
            "Typo when the device was registered (e.g. 192.168.1 instead of 192.168.1.10).",
            "A hostname was entered into the IP field by mistake.",
            "Extra spaces or characters slipped into the address.",
        ],
        "steps": [
            "Confirm the correct address on the device with `ipconfig` (or its OS equivalent).",
            "Edit the device in the Devices page and fix the IP address.",
            "After saving, run 'Check now' to obtain the real status.",
        ],
        "commands": [
            {"cmd": "ipconfig", "what": "Show the real IPv4/IPv6 addresses of a Windows device."},
            {"cmd": "nslookup <hostname>", "what": "Resolve a hostname in DNS to check you have the right address."},
        ],
    },
    {
        "slug": "network-unreachable",
        "title": "Destination network unreachable",
        "summary": (
            "Ping reports 'Destination host unreachable' - the device cannot be reached "
            "because there is no valid route at some hop, commonly the local gateway."
        ),
        "severity": "high",
        "causes": [
            "Device is powered off so its gateway has no route to it.",
            "The device is on a different subnet without a proper route.",
            "The router/switch interface is administratively down.",
            "A firewall is silently dropping the traffic (perceived as unreachable).",
            "Wrong subnet mask / default gateway configured on the device.",
        ],
        "steps": [
            "Check the device's config: subnet mask and default gateway (`ipconfig`).",
            "Ping the local default gateway to confirm the LAN is up.",
            "If the device is on another subnet, ping the remote router/gateway to "
            "verify the inter-VLAN route exists.",
            "Check the switchport: powered on, correct VLAN, no ACL blocking the traffic.",
        ],
        "commands": [
            {"cmd": "ipconfig", "what": "Verify IP, subnet mask and default gateway on the device."},
            {"cmd": "ping <gateway-ip>", "what": "Tests the first hop out of the device's subnet."},
            {"cmd": "route print", "what": "Show the local routing table and see whether a route exists."},
            {"cmd": "tracert <device-ip>", "what": "See exactly where routing fails along the path."},
        ],
    },
    {
        "slug": "ping-timeout",
        "title": "Ping timeout (host not responding)",
        "summary": (
            "Ping says 'Request timed out' - packets were sent but no reply arrived "
            "within the timeout. This typically means the device or a hop is not "
            "answering ICMP."
        ),
        "severity": "medium",
        "causes": [
            "Device is behind a firewall that drops (not rejects) ICMP traffic.",
            "Device is too busy to answer ping in time (high load).",
            "Network congestion or packet loss drops the echo replies.",
            "The device only replies, not the host itself, but a middle hop stops ICMP.",
            "Power management / sleep state on the device.",
        ],
        "steps": [
            "Run several pings (e.g. `ping -n 10 <ip>`) and check the loss percentage.",
            "Compare with another device in the same area to separate device vs path.",
            "Ping the device's default gateway: if it also times out, the fault is "
            "upstream of the device.",
            "Check whether the tracked service (e.g. the port the app listens on) is "
            "actually up - ICMP may be blocked while services run normally.",
            "Increase the per-ping timeout in this tool if the device is known to be "
            "slow but reachable.",
        ],
        "commands": [
            {"cmd": "ping -n 10 <device-ip>", "what": "10 pings to measure packet loss and consistency."},
            {"cmd": "ping <gateway-ip>", "what": "Separate local-network problems from remote ones."},
            {"cmd": "tracert <device-ip>", "what": "Identify the hop where replies stop coming."},
            {"cmd": "nslookup <hostname>", "what": "Confirm DNS resolves correctly for the device."},
            {"cmd": "netstat -an", "what": "On the device, confirm the service port is listening."},
        ],
    },
]