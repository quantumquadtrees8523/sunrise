"""The home network, as Home Assistant's host sees it. Plain blocking Python (Home Assistant code
runs it in the executor).

WiZ bulbs speak JSON over UDP port 38899: `getPilot` gives the MAC, state and Wi-Fi signal (RSSI),
`getSystemConfig` the MAC and firmware, and a `registration` broadcast plus a sweep of the subnet
finds every bulb that answers. A bulb is matched to Home Assistant by MAC, which tells a bulb that
moved to a new address apart from one that is off the network.

Local only: every packet this module sends goes to a LAN address (`is_lan`), checked in code.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any

WIZ_PORT = 38899
FAIR_RSSI, WEAK_RSSI, VERY_WEAK_RSSI = -67, -75, -82
IP_RX = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


class NotLocal(ValueError):
    """Refused: the address isn't on the home network."""


LAN_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
                                              "255.255.255.255/32", "fc00::/7", "fe80::/10", "::1/128")]


def is_lan(host: str) -> bool:
    """A home-network address (RFC 1918, loopback, link-local, broadcast): the only places this
    integration sends anything. Python's is_private is wider (it includes documentation ranges)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in n for n in LAN_NETS if n.version == ip.version)


def _lan(host: str) -> str:
    if not is_lan(host):
        raise NotLocal(f"{host} isn't on the home network")
    return host


@dataclass
class Net:
    """Knobs: tests point the port at fake bulbs on 127.0.0.x and shorten the timeouts."""

    wiz_port: int = WIZ_PORT
    probe_timeout: float = 1.5
    discover_timeout: float = 2.5
    broadcast: bool = True
    sweep: list[str] | None = None  # addresses to ask one by one (None: the /24s given to discover)
    extra: dict[str, Any] = field(default_factory=dict)


def norm_mac(value: Any) -> str:
    return re.sub(r"[^0-9a-f]", "", str(value or "").lower())


def signal_words(rssi: Any) -> str | None:
    if not isinstance(rssi, int | float):
        return None
    if rssi >= FAIR_RSSI:
        return "good"
    if rssi >= WEAK_RSSI:
        return "fair"
    return "weak" if rssi >= VERY_WEAK_RSSI else "very weak"


def wiz_ask(ip: str, method: str, net: Net, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """One WiZ request; its `result`, or None. Asked three times: a bulb on weak Wi-Fi drops packets."""
    _lan(ip)
    msg = json.dumps({"method": method, "params": params or {}}).encode()
    tries = 3
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(net.probe_timeout / tries)
        for _ in range(tries):
            try:
                s.sendto(msg, (_lan(ip), net.wiz_port))
                while True:
                    data, addr = s.recvfrom(4096)
                    if addr[0] != ip:
                        continue
                    with contextlib.suppress(ValueError):
                        res = json.loads(data.decode("utf-8", "replace")).get("result")
                        if isinstance(res, dict):
                            return res
            except TimeoutError:
                continue
            except OSError:
                return None
    return None


def wiz_probe(ip: str, net: Net) -> dict[str, Any]:
    """What a WiZ bulb at `ip` says about itself: MAC, signal (RSSI, dBm), firmware."""
    pilot = wiz_ask(ip, "getPilot", net)
    if pilot is None:
        return {"answers": False}
    out: dict[str, Any] = {"answers": True, "mac": norm_mac(pilot.get("mac")), "rssi": pilot.get("rssi"), "on": pilot.get("state")}
    cfg = wiz_ask(ip, "getSystemConfig", net) or {}
    out["mac"] = out["mac"] or norm_mac(cfg.get("mac"))
    if cfg.get("fwVersion"):
        out["firmware"] = cfg["fwVersion"]
    return out


def sweep_targets(subnets: list[str], net: Net, limit: int = 4) -> list[str]:
    """Every host address of up to `limit` private /24s."""
    if net.sweep is not None:
        return [h for h in net.sweep if is_lan(h)]
    out: list[str] = []
    for sub in list(dict.fromkeys(subnets))[:limit]:
        with contextlib.suppress(ValueError):
            n = ipaddress.ip_network(sub, strict=False)
            if is_lan(str(n.network_address)) and n.prefixlen >= 24:
                out.extend(str(h) for h in n.hosts())
    return out


def subnet_of(ip: str) -> str | None:
    return str(ipaddress.ip_network(f"{ip}/24", strict=False)) if IP_RX.match(ip or "") and is_lan(ip) else None


def wiz_discover(net: Net, subnets: list[str]) -> dict[str, str]:
    """Every WiZ device that answers on the LAN: mac -> ip. A broadcast (what the WiZ app and HA send)
    plus the same packet to each address of the subnets, because some routers don't pass broadcasts
    between wired and Wi-Fi clients."""
    msg = json.dumps({"method": "registration",
                      "params": {"phoneMac": "AAAAAAAAAAAA", "register": False, "phoneIp": "1.2.3.4", "id": "1"}}).encode()
    targets = (["255.255.255.255"] if net.broadcast else []) + sweep_targets(subnets, net)
    found: dict[str, str] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.2)
        start = time.monotonic()
        end = start + net.discover_timeout
        sent = 0
        while time.monotonic() < end:
            if sent < 2 and time.monotonic() >= start + sent * net.discover_timeout / 2:  # now, and halfway
                sent += 1
                for t in targets:
                    with contextlib.suppress(OSError):
                        s.sendto(msg, (_lan(t), net.wiz_port))
            try:
                data, addr = s.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            with contextlib.suppress(ValueError, AttributeError):
                mac = norm_mac((json.loads(data.decode("utf-8", "replace")).get("result") or {}).get("mac"))
                if len(mac) == 12:
                    found[mac] = addr[0]
    return found


def tcp_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """A LAN device's port answers (ESPHome 6053, a router's web page 80)."""
    try:
        with socket.create_connection((_lan(ip), port), timeout=timeout):
            return True
    except OSError:
        return False


# --- classification -----------------------------------------------------------------------------

CAUSES = {
    "ok": "It's working.",
    "moved": "It's on the Wi-Fi at a new address and Home Assistant is still looking at the old one.",
    "answering": "It answers right now; Home Assistant just hasn't caught up.",
    "not_loaded": "Home Assistant's connection to it isn't running, but the device answers.",
    "other_device_at_host": "A different device now answers at its old address: it moved, and something else took the address.",
    "weak_signal": "It's connected, but its Wi-Fi signal is weak, so it drops off now and then.",
    "off_network": ("It doesn't answer anywhere on the network. It most likely has no power (a wall switch or lamp switch "
                    "is off) or is stuck; it still knows the Wi-Fi, so turning its power off for 10 seconds and on once "
                    "usually brings it back."),
    "forgot_wifi": ("It still doesn't answer after its power was turned off and on, so it has most likely forgotten the "
                    "Wi-Fi. Only this kind needs re-pairing, in the WiZ phone app over Bluetooth."),
    "unreachable": "It doesn't answer on the network: no power, or not connected.",
    "unknown_address": "Home Assistant doesn't say what address it uses, so I couldn't check it on the network.",
    "derived": "It's built inside Home Assistant from other things, and one of those is missing.",
}


def classify_wiz(*, down: bool, ha_mac: str | None, host: str | None, probe: dict[str, Any] | None,
                 found: dict[str, str], power_cycled: bool, entry_loaded: bool = True) -> dict[str, Any]:
    """Sort one WiZ bulb into a cause: (a) moved = on the Wi-Fi at a new address, fix in software;
    (b) off_network = power-cycle at the switch; (c) forgot_wifi = still gone after a power cycle,
    re-pair in the WiZ app. Plus the in-between cases a reload fixes."""
    probe = probe or {"answers": False}
    new_ip = found.get(ha_mac or "")
    out: dict[str, Any] = {"answers": bool(probe.get("answers"))}
    if probe.get("answers") and probe.get("rssi") is not None:
        out["rssi"] = probe["rssi"]
        out["signal"] = signal_words(probe["rssi"])
    if new_ip and new_ip != host:
        cause = "moved"
        out["found_at"] = new_ip
    elif probe.get("answers") and ha_mac and probe.get("mac") and probe["mac"] != ha_mac:
        cause = "other_device_at_host"
    elif probe.get("answers") or new_ip:
        if not entry_loaded:
            cause = "not_loaded"
        elif down:
            cause = "answering"
        elif isinstance(probe.get("rssi"), int | float) and probe["rssi"] < WEAK_RSSI:
            cause = "weak_signal"
        else:
            cause = "ok"
    elif not down and entry_loaded:
        cause = "ok"  # HA reached it lately; the probe just missed
    else:
        cause = "forgot_wifi" if power_cycled else "off_network"
    out["cause"] = cause
    out["why"] = CAUSES[cause]
    return out


def fix_for(cause: str) -> dict[str, str] | None:
    """What fixes a cause: a tool the agent calls, or one thing a person does."""
    return {
        "moved": {"tool": "fix_device", "op": "update_host", "what": "point Home Assistant at its new address (undoable)"},
        "answering": {"tool": "fix_device", "op": "reload_entry", "what": "reconnect Home Assistant to it"},
        "not_loaded": {"tool": "fix_device", "op": "reload_entry", "what": "restart Home Assistant's connection to it"},
        "other_device_at_host": {"tool": "diagnose_device", "what": "search again; the bulb itself may have moved"},
        "off_network": {"person": "turn its switch off, wait 10 seconds, turn it on once; then check again with power_cycled=true"},
        "forgot_wifi": {"person": "re-pair it in the WiZ phone app (add a light, follow the app; it uses Bluetooth)"},
        "unreachable": {"person": "check it has power; turn it off for 10 seconds and on again"},
        "weak_signal": {"person": "its Wi-Fi signal is weak: move it, or the router, closer, or add a 2.4 GHz access point near it"},
    }.get(cause)
