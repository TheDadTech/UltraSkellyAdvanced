"""Read-only network identity shared by the experimental local console."""
import ipaddress
import json
from pathlib import Path


def usable_addresses(interface):
    result = []
    for item in interface.get("addr_info", []):
        try:
            address = ipaddress.ip_address(item.get("local", ""))
        except ValueError:
            continue
        if (item.get("scope") == "global" and not address.is_loopback
                and not address.is_link_local and not address.is_unspecified
                and not address.is_multicast and not item.get("tentative", False)):
            result.append(str(address))
    return sorted(result, key=lambda s: ipaddress.ip_address(s).version)


def address_url(address):
    host = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
    return f"http://{host}"


def summarize(addresses, devices):
    """Never infer network readiness from the host's /etc/hosts entry."""
    interfaces = []
    for interface in addresses:
        name = interface.get("ifname", "")
        device = devices.get(name, {})
        kind = device.get("type")
        if kind not in {"ethernet", "wifi"}:
            continue
        ips = usable_addresses(interface)
        is_ap = kind == "wifi" and device.get("connection") == "USA-Setup"
        up = interface.get("operstate") in {"UP", "UNKNOWN"}
        connected = device.get("state", "").startswith("connected")
        interfaces.append({"name": name, "type": kind, "addresses": ips,
                           "connected": up and connected and bool(ips),
                           "hotspot": is_ap, "state": device.get("state", "unknown")})
    lan = sorted((i for i in interfaces if i["connected"] and not i["hotspot"]),
                 key=lambda i: i["type"] != "ethernet")
    primary = lan[0] if lan else None
    return {"interfaces": interfaces, "connected": bool(primary),
            "transport": primary["type"] if primary else None,
            "address": primary["addresses"][0] if primary else None,
            "dashboard_url": address_url(primary["addresses"][0]) if primary else None,
            "hostname_url": "http://usa-controller.local",
            "hotspot_active": any(i["hotspot"] and i["connected"] for i in interfaces)}


def status(run):
    addresses = json.loads(run("ip", "-j", "address", "show", timeout=5).stdout)
    output = run("nmcli", "-t", "--escape", "no", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                 "device", "status", timeout=5).stdout
    devices = {}
    for line in output.splitlines():
        parts = line.split(":", 3)
        if len(parts) == 4:
            name, kind, state, connection = parts
            devices[name] = {"type": kind, "state": state, "connection": connection}
    result = summarize(addresses, devices)
    try:
        result["hardware"] = Path("/proc/device-tree/model").read_text().rstrip("\x00\n")
    except OSError:
        result["hardware"] = "Raspberry Pi"
    return result
