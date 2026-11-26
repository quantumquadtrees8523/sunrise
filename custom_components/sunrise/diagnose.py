"""Why a device dropped, and the fixes the house can make in software, reading Home Assistant's
records in-process.

General first: every device, whatever its integration, gets Home Assistant's record (state, since
when, its integration and config entry, maker, model, how it connects), and, when Home Assistant
knows its address, a check of whether anything answers there. Then, for the kinds Sunrise has a
helper for (helpers.py, WiZ today), that kind's own checks and fixes. A device without a helper
carries `tailor`: what to look up so the person gets its maker's own steps.

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

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import net as N
from .const import RELOAD_WAIT_S
from .helpers import HELPERS, label
from .house import router_facts, system_log_counts
from .store import Store

# The port each integration's devices listen on; any other device with an address: 80 and 443.
# A refused connection counts too: the device itself answered.
TCP_PORTS = {"esphome": (6053,), "shelly": (80,), "hue": (443, 80), "sonos": (1400,), "cast": (8009,), "tplink": (9999, 80),
             "wled": (80,), "elgato": (9123,), "nanoleaf": (16021,), "yeelight": (55443,)}
DEFAULT_PORTS = (80, 443)
HOST_KEYS = ("host", "ip_address", "ip")
# How a device reaches Home Assistant, when its device record doesn't say.
RADIO_INTEGRATIONS = {"zha": "zigbee", "deconz": "zigbee", "hue": "zigbee", "zwave_js": "z-wave", "zwave_me": "z-wave",
                      "thread": "thread", "bthome": "bluetooth", "ibeacon": "bluetooth"}
RADIO = ("zigbee", "z-wave", "bluetooth", "thread")
STILL_GONE = ("forgot_wifi", "off_network", "still_unreachable")  # a remembered power cycle still counts
NEEDS_MAKER = {"unreachable": "getting it back on the network", "still_unreachable": "reconnecting it to the Wi-Fi",
               "radio_silent": "bringing it back onto its radio network (battery, range, re-pairing)",
               "forgot_wifi": "re-pairing it with the Wi-Fi", "weak_signal": "improving its connection",
               "unknown_address": "getting it back online"}


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
    manufacturer: str | None = None
    model: str | None = None
    connection: str | None = None  # network, zigbee, z-wave, bluetooth, thread, or None (Home Assistant doesn't say)
    via: str | None = None  # the hub or bridge it reaches Home Assistant through


def _connection(d: dr.DeviceEntry, domain: str | None, host: str | None, mac: str | None) -> str | None:
    kinds = {k for k, _v in d.connections}
    if dr.CONNECTION_ZIGBEE in kinds:
        return "zigbee"
    if dr.CONNECTION_BLUETOOTH in kinds:
        return "bluetooth"
    if domain in RADIO_INTEGRATIONS:
        return RADIO_INTEGRATIONS[domain]
    return "network" if host or mac or dr.CONNECTION_UPNP in kinds else None


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
        if not mac and entry and (helper := HELPERS.get(entry.domain)):
            mac = helper.mac(d, entry)
        host = next((str(entry.data[k]) for k in HOST_KEYS if entry and isinstance(entry.data.get(k), str)), None)
        area = areas.async_get_area(d.area_id) if d.area_id else None
        hub = devs.async_get(d.via_device_id) if d.via_device_id else None
        out.append(Dev(id=d.id, name=d.name_by_user or d.name or d.id, room=area.name if area else None,
                       integration=entry.domain if entry else None, entry_id=entry.entry_id if entry else None,
                       entry_state=entry.state.value if entry else None, host=host, mac=mac,
                       entities=by_dev.get(d.id, []), down=down,
                       since=min((s.last_changed.timestamp() for s in states if s.state == "unavailable"), default=None) if down else None,
                       manufacturer=d.manufacturer, model=d.model, connection=_connection(d, entry.domain if entry else None, host, mac),
                       via=(hub.name_by_user or hub.name) if hub else None))
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


async def _reach(hass: HomeAssistant, d: Dev) -> str:
    """open / refused (the device is there) / silent, over the ports its integration uses."""
    got = await asyncio.gather(*(hass.async_add_executor_job(N.tcp_reach, d.host, p, 1.0)
                                 for p in TCP_PORTS.get(d.integration or "", DEFAULT_PORTS)))
    return "open" if "open" in got else "refused" if "refused" in got else "silent"


def general_cause(d: Dev, reach: str | None, loaded: bool, cycled: bool) -> dict[str, Any]:
    """The cause for any device, from Home Assistant's record and whether its address answers."""
    out: dict[str, Any] = {}
    if reach in ("open", "refused"):
        out["answers"] = True
        cause = "not_loaded" if not loaded else "answering" if d.down else "ok"
    elif reach == "silent":
        out["answers"] = False
        cause = ("still_unreachable" if cycled and d.down else "unreachable") if d.down or not loaded else "ok"
    elif not loaded:
        cause = "not_loaded"
    elif d.down:
        cause = "radio_silent" if d.connection in RADIO else "unknown_address"
    else:
        cause = "ok"
    return {**out, "cause": cause, "why": N.CAUSES[cause]}


def tailor(d: Dev, cause: str) -> str | None:
    """For a device Sunrise has no helper for: what to look up so the person's steps are its maker's own."""
    if cause not in NEEDS_MAKER:
        return None
    what = " ".join(x for x in (d.manufacturer, d.model) if x) or "this device"
    via = f" (it reaches Home Assistant through {d.via})" if d.via else ""
    return (f"Sunrise has no helper for {d.integration or 'this kind of device'}. It is a {what}, connected by "
            f"{d.connection or 'a way Home Assistant does not record'}{via}. Read memory playbooks/ for it first; else look up "
            f"its maker's own steps for {NEEDS_MAKER[cause]} (the maker's support pages or app), give those, and save what works.")


async def diagnose(hass: HomeAssistant, store: Store, net: N.Net, target: str | None, power_cycled: bool = False) -> dict[str, Any]:
    all_devs = devices(hass)
    picked = find(all_devs, target or "")[:20]
    if not picked:
        down = sorted(d.name for d in all_devs if d.down)[:12]
        return {"devices": [], "note": f"Nothing matches {target!r}." if target else "Nothing in the house is unreachable right now.",
                **({"unreachable_now": down} if down else {})}
    helped: dict[str, list[Dev]] = {}
    for d in picked:
        if d.integration in HELPERS:
            helped.setdefault(d.integration, []).append(d)

    async def look(dom: str) -> Any:
        subs = await subnets(hass, [d for d in all_devs if d.integration == dom])
        return await HELPERS[dom].look(hass, net, helped[dom], subs, power_cycled)

    general = [d for d in picked if d.integration not in helped and d.host and N.is_lan(d.host)]
    looked = await asyncio.gather(*(look(dom) for dom in helped), *(_reach(hass, d) for d in general))
    seen = dict(zip(helped, looked[:len(helped)], strict=True))
    reach = dict(zip((d.id for d in general), looked[len(helped):], strict=True))
    remembered = await hass.async_add_executor_job(store.get, "power_cycles", {})
    rows = []
    for d in picked:
        row: dict[str, Any] = {"device": d.name, "room": d.room, "integration": d.integration, "manufacturer": d.manufacturer,
                               "model": d.model, "connection": d.connection, **({"via": d.via} if d.via else {}),
                               "state": "unreachable" if d.down else "working", "since": _when(d.since), "device_id": d.id}
        loaded = d.entry_state in (None, ConfigEntryState.LOADED.value)
        cycled = power_cycled or bool(remembered.get(d.id))
        helper = HELPERS[d.integration] if d.integration in helped else None
        row.update(helper.classify(d, seen[d.integration], cycled, loaded) if helper else general_cause(d, reach.get(d.id), loaded, cycled))
        if power_cycled and row["cause"] in ("forgot_wifi", "still_unreachable"):
            remembered[d.id] = time.time()
        if row["cause"] not in STILL_GONE:
            remembered.pop(d.id, None)  # it answers again: forget the power cycle
        row["fix"] = (helper.fix(row["cause"]) if helper else None) or N.fix_for(row["cause"])
        if not helper and (hint := tailor(d, row["cause"])):
            row["tailor"] = hint
        rows.append(row)
    await hass.async_add_executor_job(store.put, "power_cycles", remembered)
    by: dict[str, list[str]] = {}
    for r in rows:
        by.setdefault(r["cause"], []).append(label(r))
    people = []
    if by.get("off_network"):
        people.append("Turn the switch off, wait 10 seconds, turn it on once, for: " + ", ".join(by["off_network"]))
    if by.get("unreachable"):
        people.append("Check these have power; turn each off for 10 seconds and on once: " + ", ".join(by["unreachable"]))
    for dom, h in ((dom, HELPERS[dom]) for dom in helped):
        people += h.person([r for r in rows if r["integration"] == dom])
    if by.get("still_unreachable"):
        people.append("These still don't answer after a power cycle; reconnect each to the Wi-Fi with its maker's own steps: "
                      + ", ".join(by["still_unreachable"]))
    if by.get("radio_silent"):
        people.append("Check the battery, and that it's near a powered device on the same network, for: " + ", ".join(by["radio_silent"]))
    out: dict[str, Any] = {"devices": rows, "by_cause": by, "for_the_person": people,
                           "software_fixes": [r["device_id"] for r in rows if (r.get("fix") or {}).get("tool") == "fix_device"]}
    logged = system_log_counts(hass)
    errors = {k: logged[k]["count"] for k in sorted({d.integration for d in picked if d.integration in logged})}
    if errors:
        out["errors_since_start"] = errors
    if helped:
        out["helpers"] = {dom: HELPERS[dom].summary(seen[dom]) for dom in helped}
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
    """Point Home Assistant at a device's new address, through its helper (which uses the
    integration's own setup), and keep the old address for undo."""
    helper = HELPERS.get(d.integration or "")
    if not helper or not helper.can_move:
        kinds = ", ".join(sorted(k for k, h in HELPERS.items() if h.can_move))
        raise HomeAssistantError(f"Sunrise changes a device's address only for the kinds it has a helper for ({kinds} today); "
                                 f"{d.name} is {d.integration}. Its integration may offer Reconfigure in Settings > Devices & services.")
    if not new:
        subs = await subnets(hass, [x for x in devices(hass) if x.integration == d.integration])
        new = await helper.find(hass, net, d, subs)
        if not new:
            return {"ok": False, "error": f"{d.name} didn't answer a search of the network, so there's no new address. Nothing changed."}
    if not N.IP_RX.match(new) or not N.is_lan(new):
        raise HomeAssistantError(f"{new!r} isn't an address on the home network; nothing changed")
    old = d.host
    if old == new:
        return {"ok": True, "changed": False, "note": "Home Assistant already uses that address"}
    error = await helper.move(hass, net, d, entry, new)
    if error:
        return {"ok": False, "error": error}
    got = entry.data.get("host")
    change = await hass.async_add_executor_job(partial(store.append, "changes", {"op": "update_host", "target": d.id,
                                               "entry_id": entry.entry_id, "before": old, "after": new}))
    return {"ok": got == new, "read_back": {"host_now": got}, "change_id": change["id"],
            "undo": "undo with this change_id puts the old address back", "next": "diagnose_device again to confirm it works"}


async def network_check(hass: HomeAssistant, store: Store, net: N.Net) -> dict[str, Any]:
    """The network from the house's side: the router as Home Assistant knows it, the internet,
    devices on the home network, their Wi-Fi signal where it is reported."""
    found = router_facts(hass)
    router: dict[str, Any] = {"devices": found["devices"], "sensors": {}}
    for eid in found["sensors"]:
        if st := hass.states.get(eid):
            router["sensors"][st.attributes.get("friendly_name") or eid] = {
                "state": st.state, **({"unit": u} if (u := st.attributes.get("unit_of_measurement")) else {})}
    wan = next((hass.states.get(e).state for e in found["wan"] if hass.states.get(e)), None)
    all_devs = devices(hass)
    subs = await subnets(hass, all_devs)
    gateway = None
    if subs:
        gw = subs[0].rsplit(".", 1)[0] + ".1"
        answers = any(await asyncio.gather(*(hass.async_add_executor_job(N.tcp_open, gw, p, 1.0) for p in (80, 443))))
        gateway = {"answers": answers, "address": gw}
    on_net = [d for d in all_devs if d.connection == "network"]
    # Signal: Home Assistant's own signal sensors for any device, then live readings from helpers.
    ents = er.async_get(hass)
    reading: dict[str, tuple[float, str]] = {}
    for st in hass.states.async_all("sensor"):
        if st.attributes.get("unit_of_measurement") != "dBm" and st.attributes.get("device_class") != "signal_strength":
            continue
        reg = ents.async_get(st.entity_id)
        try:
            value = float(st.state)
        except ValueError:
            continue
        if reg and reg.device_id:
            reading[reg.device_id] = (value, "home_assistant")
    for dom, h in HELPERS.items():
        live = [d for d in all_devs if d.integration == dom and not d.down and d.host and N.is_lan(d.host)]
        for r in await h.signal(hass, net, live) if live else []:
            reading[r["device_id"]] = (r["rssi"], dom)
    signal = sorted(({"device": d.name, "room": d.room, "rssi": int(v) if float(v).is_integer() else v, "signal": N.signal_words(v), "from": src}
                     for d in all_devs if d.id in reading for v, src in [reading[d.id]]), key=lambda x: x["rssi"])
    findings = []
    if wan is not None:
        findings.append("The internet connection is up." if str(wan).lower() in ("on", "connected", "up", "true") else
                        "The router says the internet connection is down; local devices still work.")
    down = [d for d in on_net if d.down]
    if down:
        findings.append(f"{len(down)} of {len(on_net)} devices on the home network can't be reached.")
    weak = [s for s in signal if s["rssi"] < N.WEAK_RSSI]
    if weak:
        findings.append(f"{len(weak)} of the devices that report a signal have a weak one.")
    if not found["devices"]:
        findings.append("Home Assistant doesn't know the router; its make and model can come from the person or house.md.")
    errors = {k: v["count"] for k, v in system_log_counts(hass).items() if k in {d.integration for d in on_net}}
    return {"router": router, "internet": wan, "gateway": gateway,
            "network_devices": {"total": len(on_net), "unreachable": len(down)}, "signal": signal, "errors_since_start": errors,
            "findings": findings, "rule": "These tools never change router settings or passwords. Give the person steps, or follow a skill that covers the router with their yes."}
