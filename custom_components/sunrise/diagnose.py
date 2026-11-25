"""Why a device dropped, and the fixes the house can make in software, reading Home Assistant's
records in-process.

Never the router, the Wi-Fi or a password: those come back as steps for a person.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from dataclasses import dataclass
from functools import partial
from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import net as N
from .const import RELOAD_WAIT_S
from .house import system_log_counts
from .store import Store

TCP_PORTS = {"esphome": 6053}
HOST_KEYS = ("host", "ip_address", "ip")


@dataclass
class Dev:
    id: str
    name: str
    room: str | None
    integration: str | None
    entry_id: str | None
    entry_state: str | None
    host: str | None
    mac: str | None
    entities: list[str]
    down: bool
    since: float | None


def devices(hass: HomeAssistant) -> list[Dev]:
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    by_dev: dict[str, list[str]] = {}
    for e in ents.entities.values():
        if e.device_id and not e.disabled_by:
            by_dev.setdefault(e.device_id, []).append(e.entity_id)
    out = []
    for d in devs.devices:
        if d.disabled_by or d.entry_type is not None:
            continue
        entry = next((x for x in (hass.config_entries.async_get_entry(i) for i in d.config_entries) if x), None)
        states = [s for s in (hass.states.get(e) for e in by_dev.get(d.id, [])) if s]
        down = bool(states) and all(s.state == "unavailable" for s in states)
        mac = next((N.norm_mac(v) for k, v in d.connections if k == dr.CONNECTION_NETWORK_MAC), None)
        if not mac and entry and entry.domain == "wiz":
            mac = next((N.norm_mac(v) for _k, v in d.identifiers if len(N.norm_mac(v)) == 12), None) or N.norm_mac(entry.unique_id)
        host = next((str(entry.data[k]) for k in HOST_KEYS if entry and isinstance(entry.data.get(k), str)), None)
        area = areas.async_get_area(d.area_id) if d.area_id else None
        out.append(Dev(id=d.id, name=d.name_by_user or d.name or d.id, room=area.name if area else None,
                       integration=entry.domain if entry else None, entry_id=entry.entry_id if entry else None,
                       entry_state=entry.state.value if entry else None, host=host, mac=mac,
                       entities=by_dev.get(d.id, []), down=down,
                       since=min((s.last_changed.timestamp() for s in states if s.state == "unavailable"), default=None) if down else None))
    return out


def find(devs: list[Dev], target: str) -> list[Dev]:
    """What a person means: a device id, entity id, name, room ('kitchen lights') or address."""
    t = " ".join((target or "").lower().split())
    if not t:
        return [d for d in devs if d.down]
    for d in devs:
        if t == d.id.lower() or t in (e.lower() for e in d.entities) or (d.mac and N.norm_mac(t) == d.mac) or t == (d.host or ""):
            return [d]
    named = [d for d in devs if t == d.name.lower()]
    if named:
        return named
    rooms = [d for d in devs if d.room and d.room.lower() in t]
    if rooms:
        if re.search(r"\b(light|lights|lamp|lamps|bulb|bulbs)\b", t):
            lit = [d for d in rooms if any(e.startswith("light.") for e in d.entities)]
            rooms = lit or rooms
        return rooms
    if re.search(r"\b(light|lights|lamp|lamps|bulb|bulbs)\b", t) and re.search(r"\b(all|my|the)\b", t):
        return [d for d in devs if any(e.startswith("light.") for e in d.entities)]
    scored = sorted(((max(difflib.SequenceMatcher(None, t, n).ratio() for n in [d.name.lower()] + d.entities), d) for d in devs),
                    key=lambda x: -x[0])
    return [d for s, d in scored[:12] if s >= 0.6]


async def subnets(hass: HomeAssistant, devs: list[Dev]) -> list[str]:
    """The LAN /24s to search: Home Assistant's own adapters, then where its devices are."""
    out: list[str] = []
    try:
        from homeassistant.components import network  # noqa: PLC0415

        for a in await network.async_get_adapters(hass):
            for ip in a.get("ipv4") or []:
                if a.get("enabled") and (s := N.subnet_of(ip.get("address", ""))):
                    out.append(s)
    except Exception:  # noqa: BLE001  (no network integration)
        pass
    out += [s for d in devs if d.host and (s := N.subnet_of(d.host))]
    return list(dict.fromkeys(out))


def _when(ts: float | None) -> str | None:
    return time.strftime("%b %d %H:%M", time.localtime(ts)) if ts else None


async def diagnose(hass: HomeAssistant, store: Store, net: N.Net, target: str | None, power_cycled: bool = False) -> dict[str, Any]:
    all_devs = devices(hass)
    picked = find(all_devs, target or "")[:20]
    if not picked:
        down = sorted(d.name for d in all_devs if d.down)[:12]
        return {"devices": [], "note": f"Nothing matches {target!r}." if target else "Nothing in the house is unreachable right now.",
                **({"unreachable_now": down} if down else {})}
    wiz = [d for d in picked if d.integration == "wiz"]
    found: dict[str, str] = {}
    probes: dict[str, dict[str, Any]] = {}
    if wiz:
        all_wiz = [d for d in all_devs if d.integration == "wiz"]
        subs = await subnets(hass, all_wiz)
        tasks = {d.id: hass.async_add_executor_job(N.wiz_probe, d.host, net) for d in wiz if d.host and N.is_lan(d.host)}
        disc = hass.async_add_executor_job(N.wiz_discover, net, subs) if any(d.down for d in wiz) or power_cycled else None
        results = await asyncio.gather(*tasks.values())
        probes = dict(zip(tasks, results, strict=True))
        found = await disc if disc else {}
    remembered = await hass.async_add_executor_job(store.get, "power_cycles", {})
    rows = []
    for d in picked:
        row: dict[str, Any] = {"device": d.name, "room": d.room, "integration": d.integration,
                               "state": "unreachable" if d.down else "working", "since": _when(d.since), "device_id": d.id}
        loaded = d.entry_state in (None, ConfigEntryState.LOADED.value)
        if d.integration == "wiz":
            cycled = power_cycled or bool(remembered.get(d.id))
            row.update(N.classify_wiz(down=d.down, ha_mac=d.mac, host=d.host, probe=probes.get(d.id), found=found,
                                      power_cycled=cycled, entry_loaded=loaded))
        elif d.host and N.is_lan(d.host) and (port := TCP_PORTS.get(d.integration or "")):
            ok = await hass.async_add_executor_job(N.tcp_open, d.host, port, 1.0)
            cause = ("not_loaded" if not loaded else "answering" if d.down else "ok") if ok else ("unreachable" if d.down or not loaded else "ok")
            row.update(cause=cause, why=N.CAUSES[cause], answers=ok)
        elif d.down or not loaded:
            cause = "not_loaded" if not loaded else "unknown_address"
            row.update(cause=cause, why=N.CAUSES[cause])
        else:
            row.update(cause="ok", why=N.CAUSES["ok"])
        if power_cycled and d.integration == "wiz" and row["cause"] == "forgot_wifi":
            remembered[d.id] = time.time()
        if row["cause"] not in ("forgot_wifi", "off_network"):
            remembered.pop(d.id, None)  # it answers again: forget the power cycle
        row["fix"] = N.fix_for(row["cause"])
        rows.append(row)
    await hass.async_add_executor_job(store.put, "power_cycles", remembered)
    by = {}
    for r in rows:
        by.setdefault(r["cause"], []).append(f"{r['device']}" + (f" ({r['room']})" if r.get("room") else ""))
    people = []
    if by.get("off_network"):
        people.append("Turn the switch off, wait 10 seconds, turn it on once, for: " + ", ".join(by["off_network"]))
    if by.get("forgot_wifi"):
        people.append("Re-pair in the WiZ phone app (add a light; it uses Bluetooth): " + ", ".join(by["forgot_wifi"]))
    out: dict[str, Any] = {"devices": rows, "by_cause": by, "for_the_person": people,
                           "software_fixes": [r["device_id"] for r in rows if (r.get("fix") or {}).get("tool") == "fix_device"]}
    if wiz:
        out["wiz_answered_search"] = len(found)
        errors = system_log_counts(hass).get("wiz")
        if errors:
            out["wiz_errors_since_start"] = errors["count"]
    return out


async def fix(hass: HomeAssistant, store: Store, net: N.Net, op: str, target: str, host: str | None = None,
              reload_wait: float = RELOAD_WAIT_S) -> dict[str, Any]:
    if re.search(r"router|wi-?fi|password|ssid|dhcp", f"{op} {target}", re.I):
        return {"refused": "I never change the router, the Wi-Fi or a password. Give the person the steps instead."}
    all_devs = devices(hass)
    picked = find(all_devs, target)
    if len(picked) != 1:
        raise HomeAssistantError(f"{target!r} matches {len(picked)} devices; name exactly one (device_id from diagnose_device)")
    d = picked[0]
    entry = hass.config_entries.async_get_entry(d.entry_id) if d.entry_id else None
    if not entry:
        raise HomeAssistantError(f"{d.name} has no integration entry to fix")
    if op == "reload_entry":
        before = entry.state.value
        await hass.config_entries.async_reload(entry.entry_id)
        await asyncio.sleep(reload_wait)
        after_dev = next((x for x in devices(hass) if x.id == d.id), d)
        return {"ok": entry.state is ConfigEntryState.LOADED and not after_dev.down,
                "read_back": {"connection": entry.state.value, "was": before, "device": "unreachable" if after_dev.down else "working"},
                "undo": "nothing to undo: a reload only reconnects Home Assistant"}
    if op == "update_host":
        return await update_host(hass, store, net, d, entry, host)
    raise HomeAssistantError("op is reload_entry or update_host")


async def update_host(hass: HomeAssistant, store: Store, net: N.Net, d: Dev, entry, new: str | None) -> dict[str, Any]:
    """Point Home Assistant at a WiZ bulb's new address through WiZ's own config flow: the flow
    reads the bulb's MAC, finds the entry with that MAC, updates its host and reloads it."""
    if d.integration != "wiz":
        raise HomeAssistantError(f"changing the address is built for WiZ bulbs; {d.name} is {d.integration}")
    if not new:
        subs = await subnets(hass, [x for x in devices(hass) if x.integration == "wiz"])
        new = (await hass.async_add_executor_job(N.wiz_discover, net, subs)).get(d.mac or "")
        if not new:
            return {"ok": False, "error": f"{d.name} didn't answer a search of the network, so there's no new address. Nothing changed."}
    if not N.IP_RX.match(new) or not N.is_lan(new):
        raise HomeAssistantError(f"{new!r} isn't an address on the home network; nothing changed")
    old = d.host
    if old == new:
        return {"ok": True, "changed": False, "note": "Home Assistant already uses that address"}
    probe = await hass.async_add_executor_job(N.wiz_probe, new, net)
    if not probe.get("answers"):
        return {"ok": False, "error": f"Nothing answers like a WiZ bulb at {new}; nothing changed."}
    if d.mac and probe.get("mac") and probe["mac"] != d.mac:
        return {"ok": False, "error": f"The bulb at {new} is a different one; nothing changed."}
    flow = await hass.config_entries.flow.async_init("wiz", context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(flow["flow_id"], {"host": new})
    if res.get("type") == "create_entry":
        return {"ok": False, "error": "Home Assistant added it as a new bulb instead of moving the old one; remove the duplicate in Devices."}
    if res.get("type") != "abort" or res.get("reason") != "already_configured":
        if res.get("type") == "form":
            hass.config_entries.flow.async_abort(res["flow_id"])
        return {"ok": False, "error": f"WiZ didn't take the new address ({res.get('reason') or res.get('errors') or res.get('type')}); nothing changed."}
    await hass.async_block_till_done()
    got = entry.data.get("host")
    change = await hass.async_add_executor_job(partial(store.append, "changes", {"op": "update_host", "target": d.id,
                                               "entry_id": entry.entry_id, "before": old, "after": new}))
    return {"ok": got == new, "read_back": {"host_now": got}, "change_id": change["id"],
            "undo": "undo with this change_id puts the old address back", "next": "diagnose_device again to confirm it works"}


async def network_check(hass: HomeAssistant, store: Store, net: N.Net) -> dict[str, Any]:
    """The network from the house's side: the router, the internet as HA sees it, Wi-Fi devices."""
    router: dict[str, Any] = {}
    for st in hass.states.async_all():
        if re.search(r"router|wan_status|gateway|modem", st.entity_id) and "external_ip" not in st.entity_id:
            router[st.attributes.get("friendly_name") or st.entity_id] = {"state": st.state, **({"unit": u} if (u := st.attributes.get("unit_of_measurement")) else {})}
    wan = next((v["state"] for k, v in router.items() if "wan" in k.lower()), None)
    all_devs = devices(hass)
    subs = await subnets(hass, all_devs)
    gateway = None
    if subs:
        gw = subs[0].rsplit(".", 1)[0] + ".1"
        answers = any(await asyncio.gather(*(hass.async_add_executor_job(N.tcp_open, gw, p, 1.0) for p in (80, 443))))
        gateway = {"answers": answers, "address": gw}
    wifi_like = [d for d in all_devs if d.integration in ("wiz", "esphome", "shelly", "tplink", "tuya", "tasmota", "govee_light_local", "lifx")]
    wiz = [d for d in all_devs if d.integration == "wiz" and not d.down and d.host and N.is_lan(d.host)]
    probes = await asyncio.gather(*(hass.async_add_executor_job(N.wiz_probe, d.host, net) for d in wiz))
    signal = sorted(({"device": d.name, "room": d.room, "rssi": p["rssi"], "signal": N.signal_words(p["rssi"])}
                     for d, p in zip(wiz, probes, strict=True) if p.get("answers") and p.get("rssi") is not None), key=lambda x: x["rssi"])
    prof = await hass.async_add_executor_job(store.get, "profile", {}) or {}
    findings = []
    if wan is not None:
        findings.append("The internet connection is up." if str(wan).lower() in ("on", "connected", "up", "true") else
                        "The router says the internet connection is down; local devices still work.")
    down = [d for d in wifi_like if d.down]
    if down:
        findings.append(f"{len(down)} of {len(wifi_like)} Wi-Fi devices can't be reached.")
    weak = [s for s in signal if s["rssi"] < N.WEAK_RSSI]
    if weak:
        findings.append(f"{len(weak)} of the bulbs that answer have a weak signal.")
    errors = {k: v["count"] for k, v in system_log_counts(hass).items() if k in {d.integration for d in wifi_like}}
    return {"isp": prof.get("isp", "unknown"), "router": router, "internet": wan, "gateway": gateway,
            "wifi_devices": {"total": len(wifi_like), "unreachable": len(down)}, "wiz_signal": signal, "errors_since_start": errors,
            "findings": findings, "rule": "These tools never change router settings or passwords. Give the person steps, or follow a skill that covers the router with their yes."}
