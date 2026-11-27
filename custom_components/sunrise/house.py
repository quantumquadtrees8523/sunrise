"""The house as the tools see it: plain async functions over `hass`, each returning a JSON-able dict.

Everything here runs inside Home Assistant, reads its own registries and states directly (no
token, no network), and writes only through Home Assistant's own APIs.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import dt as dt_util

from .access import device_seen, seen
from .const import ACT_CUTOFF_S, GUARDED_DEVICE_CLASSES, GUARDED_DOMAINS, LLM_API_ID
from .store import Store

DOWN = ("unavailable",)
# Ways to name targets inside an action's data; `act` takes its things only in entity_ids, where each is checked.
TARGET_KEYS = frozenset({"entity_id", "device_id", "area_id", "floor_id", "label_id"})
NO_READING = ("unknown",)
SKIP_DOMAINS = ("update", "event", "persistent_notification", "conversation", "tts", "stt", "wake_word", "assist_satellite_hidden")
NOT_DEVICES = ("automation", "script", "scene", "zone", "person", "sun", "update", "event", "input_boolean", "input_number",
               "input_select", "input_text", "input_datetime", "input_button", "timer", "counter", "schedule", "todo",
               "conversation", "tts", "stt", "wake_word", "ai_task")
# A name that reads like an id: hex runs, MAC-ish, underscores, model codes, "_2" copies.
BAD_NAME_RX = re.compile(r"[0-9a-f]{6,}|([0-9a-f]{2}[:-]){2,}|_|\b\d{1,3}(\.\d{1,3}){3}\b|\b[A-Z]{2,}\d{2,}\w*\b", re.IGNORECASE)


# --- reading the house --------------------------------------------------------------------------

def _name(hass: HomeAssistant, entity_id: str, ent: er.RegistryEntry | None = None) -> str:
    st = hass.states.get(entity_id)
    if st and st.attributes.get("friendly_name"):
        return str(st.attributes["friendly_name"])
    if ent and (ent.name or ent.original_name):
        return str(ent.name or ent.original_name)
    return entity_id


def _area_of(ent: er.RegistryEntry | None, dev: dr.DeviceEntry | None) -> str | None:
    if ent and ent.area_id:
        return ent.area_id
    return dev.area_id if dev else None


def _shown(ent: er.RegistryEntry | None, entity_id: str) -> bool:
    if entity_id.split(".", 1)[0] in SKIP_DOMAINS:
        return False
    return not (ent and (ent.entity_category or ent.hidden_by or ent.disabled_by))


def counts(hass: HomeAssistant) -> dict[str, Any]:
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    states = [s for s in hass.states.async_all() if seen(s.entity_id)]
    no_area = 0
    for st in states:
        ent = ents.async_get(st.entity_id)
        dev = devs.async_get(ent.device_id) if ent and ent.device_id else None
        if not _area_of(ent, dev):
            no_area += 1
    return {"entities": len(states), "unavailable": sum(1 for s in states if s.state in DOWN),
            "unknown": sum(1 for s in states if s.state in NO_READING), "no_area": no_area,
            "devices": sum(1 for d in devs.devices if d.entry_type is None and not d.disabled_by),
            "areas": len(areas.areas), "floors": len(fr.async_get(hass).floors),
            "integrations": len({e.domain for e in hass.config_entries.async_entries()})}


async def house_map(hass: HomeAssistant, room: str | None = None, everything: bool = False) -> dict[str, Any]:
    """Rooms -> devices -> things with their state, compact. Things with no room are listed last."""
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    floors = fr.async_get(hass)
    rooms: dict[str | None, dict[str, Any]] = {}
    for st in sorted(hass.states.async_all(), key=lambda s: s.entity_id):
        if not seen(st.entity_id):
            continue
        ent = ents.async_get(st.entity_id)
        if not everything and not _shown(ent, st.entity_id):
            continue
        dev = devs.async_get(ent.device_id) if ent and ent.device_id else None
        area_id = _area_of(ent, dev)
        area = areas.async_get_area(area_id) if area_id else None
        if room and not (area and room.lower() in (area.name.lower(), area.id.lower())):
            continue
        r = rooms.setdefault(area_id, {"room": area.name if area else None, "devices": {}, "other": []})
        if area and area.floor_id and (floor := floors.async_get_floor(area.floor_id)):
            r["floor"] = floor.name
        thing = {"id": st.entity_id, "name": _name(hass, st.entity_id, ent), "state": st.state}
        if dev:
            r["devices"].setdefault(dev.id, {"device": dev.name_by_user or dev.name or dev.id, "things": []})["things"].append(thing)
        else:
            r["other"].append(thing)
    out = []
    for area_id, r in sorted(rooms.items(), key=lambda kv: (kv[0] is None, kv[1]["room"] or "")):
        out.append({**{k: v for k, v in r.items() if k != "devices"}, "devices": list(r["devices"].values()),
                    **({"note": "these have no room"} if area_id is None else {})})
    return {"rooms": out, "counts": counts(hass), **({} if room else {"setup": await setup_facts(hass)})}


def nearest(hass: HomeAssistant, entity_id: str, n: int = 3, only: Callable[[str], bool] | None = None) -> list[str]:
    ids = [s.entity_id for s in hass.states.async_all() if (only is None or only(s.entity_id))]
    return difflib.get_close_matches(entity_id, ids, n=n, cutoff=0.5)


# --- act, then read back ------------------------------------------------------------------------

def _expect(domain: str, service: str, data: dict[str, Any], before: State):
    """What the state should look like after the call, as a check on a State (None: any change)."""
    def attr_close(key: str, want: float, tol: float):
        return lambda s: isinstance(s.attributes.get(key), int | float) and abs(s.attributes[key] - want) <= tol

    if service == "turn_on":
        if domain == "light" and isinstance(data.get("brightness_pct"), int | float):
            want = max(1.0, float(data["brightness_pct"])) * 255 / 100
            close = attr_close("brightness", want, 8)
            return lambda s: s.state == "on" and (close(s) or data["brightness_pct"] < 12)  # bulbs floor near 10%
        if domain in ("scene", "script"):
            return None
        return lambda s: s.state == "on" if domain != "media_player" else s.state not in ("off", "standby")
    if service == "turn_off":
        return lambda s: s.state == "off" if domain != "media_player" else s.state in ("off", "standby", "idle")
    if service == "toggle":
        return lambda s: s.state != before.state
    simple = {"lock": "locked", "unlock": "unlocked", "open_cover": ("open", "opening"), "close_cover": ("closed", "closing"),
              "media_pause": ("paused", "idle"), "media_play": ("playing",)}
    if service in simple:
        want = simple[service]
        return lambda s: s.state in (want if isinstance(want, tuple) else (want,))
    if service == "set_temperature" and isinstance(data.get("temperature"), int | float):
        return attr_close("temperature", float(data["temperature"]), 0.6)
    if service == "volume_set" and isinstance(data.get("volume_level"), int | float):
        return attr_close("volume_level", float(data["volume_level"]), 0.03)
    return None


def guarded(hass: HomeAssistant, entity_id: str) -> bool:
    domain = entity_id.split(".", 1)[0]
    if domain in GUARDED_DOMAINS:
        return True
    st = hass.states.get(entity_id)
    return domain == "cover" and bool(st and st.attributes.get("device_class") in GUARDED_DEVICE_CLASSES)


async def act(hass: HomeAssistant, action: str, entity_ids: list[str], data: dict[str, Any] | None, *,
              context: Context | None, confirmed: bool = False, cutoff: float = ACT_CUTOFF_S,
              allowed: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Perform one action on some things, then read each back: CHECKED, NOT CONFIRMED or UNREACHABLE.
    `allowed` is the exposure check (access.py): a thing it says no to is NOT EXPOSED and isn't tried."""
    data = dict(data or {})
    domain, _, service = (action or "").partition(".")
    if not domain or not service or not hass.services.has_service(domain, service):
        raise HomeAssistantError(f"{action!r} isn't an action this Home Assistant has")
    if not entity_ids:
        raise HomeAssistantError("name the things to act on in entity_ids (from house_map); nothing was done")
    if smuggled := sorted(TARGET_KEYS & set(data)):
        raise HomeAssistantError(f"name the things in entity_ids, not in data ({', '.join(smuggled)}); nothing was done")
    rows: list[dict[str, Any]] = []
    todo: list[str] = []
    for eid in dict.fromkeys(entity_ids):
        st = hass.states.get(eid)
        if st is None:
            rows.append({"id": eid, "result": "NOT FOUND", "nearest": nearest(hass, eid, only=allowed)})
        elif allowed is not None and not allowed(eid):
            rows.append({"id": eid, "name": _name(hass, eid), "result": "NOT EXPOSED",
                         "why": "the owner hasn't exposed it to voice assistants, so Sunrise can't switch it either. "
                                "Only the owner changes that: Settings > Voice assistants > Expose"})
        elif guarded(hass, eid) and not confirmed:
            rows.append({"id": eid, "name": _name(hass, eid), "result": "REFUSED",
                         "why": "locks, alarms and garage doors move only after the person says yes in this conversation (confirmed=true)"})
        elif st.state in DOWN:
            rows.append({"id": eid, "name": _name(hass, eid), "result": "UNREACHABLE",
                         "why": "it reads unavailable, so it wasn't tried; diagnose it instead of retrying"})
        else:
            todo.append(eid)
    if todo:
        before = {eid: hass.states.get(eid) for eid in todo}
        start = time.monotonic()
        error = None
        try:
            async with asyncio.timeout(cutoff):
                await hass.services.async_call(domain, service, data, blocking=True, context=context,
                                               target={"entity_id": todo})
        except TimeoutError:
            error = "the call didn't finish in time"
        except (HomeAssistantError, ValueError) as exc:
            error = str(exc)[:200]
        checks = {eid: _expect(eid.split(".", 1)[0], service, data, before[eid]) for eid in todo}
        pending = set(todo) if error is None or error == "the call didn't finish in time" else set()

        def landed(eid: str) -> bool:
            now, was = hass.states.get(eid), before[eid]
            if now is None:
                return False
            check = checks[eid]
            if check is None:
                return now.last_updated > was.last_updated
            return check(now)

        while pending and time.monotonic() - start < cutoff:
            pending = {eid for eid in pending if not landed(eid)}
            if pending:
                await asyncio.sleep(0.2)
        for eid in todo:
            now = hass.states.get(eid)
            ok = landed(eid)
            row = {"id": eid, "name": _name(hass, eid), "result": "CHECKED" if ok else "NOT CONFIRMED",
                   "now": now.state if now else None}
            if now and eid.startswith("light.") and now.attributes.get("brightness") is not None:
                row["brightness_pct"] = round(now.attributes["brightness"] * 100 / 255)
            if now and now.state in DOWN:
                row["result"] = "UNREACHABLE"
            if not ok and error:
                row["error"] = error
            rows.append(row)
    words = Counter(r["result"] for r in rows)
    return {"results": rows, "summary": ", ".join(f"{n} {k}" for k, n in words.items()),
            "say": "Report each result exactly: CHECKED may be called done; anything else may not."}


# --- audit --------------------------------------------------------------------------------------

def _norm(name: str) -> str:
    return re.sub(r"[\s_]*(\(\d+\)|\d+|copy)$", "", name.strip().lower())


def system_log_counts(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Errors Home Assistant logged since it started, by integration (needs system_log)."""
    handler = hass.data.get("system_log")
    out: dict[str, dict[str, Any]] = {}
    try:
        records = handler.records.to_list() if handler else []
    except Exception:  # noqa: BLE001  (an older or newer system_log shape)
        records = []
    for r in records:
        m = re.search(r"components\.([a-z0-9_]+)", str(r.get("name") or ""))
        if not m:
            continue
        d = out.setdefault(m.group(1), {"count": 0, "top": ""})
        d["count"] += int(r.get("count") or 1)
        msg = (r.get("message") or [""])[0]
        if len(d["top"]) == 0:
            d["top"] = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<address>", str(msg))[:160]
    return out


def _orphaned(hass: HomeAssistant, ent: er.RegistryEntry) -> bool:
    """A registry entry whose setup is gone: no live entity behind it."""
    st = hass.states.get(ent.entity_id)
    if ent.config_entry_id and hass.config_entries.async_get_entry(ent.config_entry_id) is None:
        return True
    if st is None:
        return not ent.disabled_by
    return st.state in DOWN and bool(st.attributes.get("restored"))


async def audit(hass: HomeAssistant, store: Store) -> dict[str, Any]:
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    entry_domain = {e.entry_id: e.domain for e in hass.config_entries.async_entries()}
    dead: dict[str, dict[str, Any]] = {}
    leftovers, unroomed_devices, unroomed_things, bad_names = [], [], [], []
    orphan_ids = {e.entity_id for e in ents.entities.values() if seen(e.entity_id) and _orphaned(hass, e)}
    for e in ents.entities.values():
        if e.entity_id in orphan_ids:
            leftovers.append({"id": e.entity_id, "name": _name(hass, e.entity_id, e), "kind": e.domain})
    by_device: dict[str, list[State]] = defaultdict(list)
    for st in hass.states.async_all():
        if not seen(st.entity_id):
            continue
        ent = ents.async_get(st.entity_id)
        if ent and ent.device_id:
            by_device[ent.device_id].append(st)
        elif st.state in DOWN and st.entity_id not in orphan_ids and st.domain not in NOT_DEVICES:
            g = dead.setdefault(ent.platform if ent else st.domain, {"integration": ent.platform if ent else st.domain, "things": []})
            g["things"].append({"name": _name(hass, st.entity_id, ent), "room": None})
        dev = devs.async_get(ent.device_id) if ent and ent.device_id else None
        if not _area_of(ent, dev) and _shown(ent, st.entity_id) and st.domain not in NOT_DEVICES and not dev:
            unroomed_things.append(_name(hass, st.entity_id, ent))
        name = _name(hass, st.entity_id, ent)
        if _shown(ent, st.entity_id) and BAD_NAME_RX.search(name) and st.entity_id not in orphan_ids:
            bad_names.append({"id": st.entity_id, "name": name})
    for did, states in by_device.items():
        dev = devs.async_get(did)
        if not dev or dev.disabled_by or dev.entry_type is not None:
            continue
        domain = next((entry_domain[x] for x in dev.config_entries if x in entry_domain), "unknown")
        room = areas.async_get_area(dev.area_id).name if dev.area_id and areas.async_get_area(dev.area_id) else None
        if states and all(s.state in DOWN for s in states):
            g = dead.setdefault(domain, {"integration": domain, "things": []})
            g["things"].append({"name": dev.name_by_user or dev.name, "room": room, "device_id": did})
        if not dev.area_id:
            unroomed_devices.append(dev.name_by_user or dev.name)
        if BAD_NAME_RX.search(dev.name_by_user or dev.name or ""):
            bad_names.append({"device_id": did, "name": dev.name_by_user or dev.name})
    duplicates = []
    autos = [s for s in hass.states.async_all("automation") if s.entity_id not in orphan_ids and seen(s.entity_id)]
    by_name: dict[str, list[State]] = defaultdict(list)
    for s in autos:
        by_name[_norm(str(s.attributes.get("friendly_name") or s.entity_id))].append(s)
    for group in by_name.values():
        if len(group) > 1:
            duplicates.append({"kind": "automation", "what": f"{len(group)} automations named like "
                               f"{group[0].attributes.get('friendly_name')!r}",
                               "ids": [s.entity_id for s in group], "on": [s.entity_id for s in group if s.state == "on"]})
    weather = [s for s in hass.states.async_all("weather") if seen(s.entity_id)]
    if len(weather) > 1:
        duplicates.append({"kind": "weather", "what": f"{len(weather)} weather services", "ids": [s.entity_id for s in weather]})
    noisy = {d: v for d, v in system_log_counts(hass).items() if v["count"] >= 20}
    groups = sorted(dead.values(), key=lambda g: -len(g["things"]))
    for g in groups:
        g["count"] = len(g["things"])
        g["rooms"] = sorted({t["room"] for t in g["things"] if t["room"]})
        g["things"] = g["things"][:15]
    now = {"ts": time.time(), "dead": sorted(t["name"] for g in dead.values() for t in g["things"]),
           "leftovers": len(leftovers), "unroomed": len(unroomed_devices) + len(unroomed_things),
           "duplicates": len(duplicates), "version": HA_VERSION}
    last = await hass.async_add_executor_job(store.get, "audit", None)
    changed = None
    if last:
        gone, new = set(last.get("dead", [])) - set(now["dead"]), set(now["dead"]) - set(last.get("dead", []))
        changed = {"since": dt_util.utc_from_timestamp(last["ts"]).isoformat(timespec="minutes"),
                   "back_now": sorted(gone)[:15], "newly_unreachable": sorted(new)[:15],
                   "leftovers": now["leftovers"] - last.get("leftovers", 0),
                   "unroomed": now["unroomed"] - last.get("unroomed", 0),
                   **({"ha_updated": f"{last.get('version')} -> {HA_VERSION}"} if last.get("version") != HA_VERSION else {})}
    await hass.async_add_executor_job(store.put, "audit", now)
    c = counts(hass)
    return {"counts": c, "dead": groups, "leftovers": leftovers, "unroomed": {"devices": unroomed_devices, "things": unroomed_things[:30],
            "count": len(unroomed_devices) + len(unroomed_things)}, "duplicates": duplicates, "bad_names": bad_names[:20],
            "noisy": noisy, "changed_since_last": changed,
            "note": "The audit changed nothing. Leftovers are entries whose setup was deleted; registry_edit removes them one at a time."}


# --- registry edits, each undoable --------------------------------------------------------------

def _find_area(hass: HomeAssistant, room: str) -> ar.AreaEntry | None:
    areas = ar.async_get(hass)
    return areas.async_get_area(room) or areas.async_get_area_by_name(room)


async def registry_edit(hass: HomeAssistant, store: Store, op: str, target: str, value: str | None) -> dict[str, Any]:
    """rename / set_area / create_area / remove_entity, with the old value kept for `undo`."""
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    ent = ents.async_get(target)
    dev = devs.async_get(target) if not ent else None
    if op == "create_area":
        if not value:
            raise HomeAssistantError("give the room's name in value")
        if _find_area(hass, value):
            return {"ok": True, "changed": False, "room": value, "note": "that room already exists"}
        area = areas.async_create(value)
        change = await _record(hass, store, op="create_area", target=area.id, before=None, after=value)
        return {"ok": True, "changed": True, "room": area.name, "read_back": bool(areas.async_get_area(area.id)), "change_id": change["id"]}
    if not ent and not dev:
        raise HomeAssistantError(f"{target!r} isn't an entity id or device id this house has; nearest: {nearest(hass, target)}")
    if op == "rename":
        if not value:
            raise HomeAssistantError("give the new name in value")
        if ent:
            before = ent.name
            ents.async_update_entity(ent.entity_id, name=value)
            got = ents.async_get(ent.entity_id).name
        else:
            before = dev.name_by_user
            devs.async_update_device(dev.id, name_by_user=value)
            got = devs.async_get(dev.id).name_by_user
        change = await _record(hass, store, op="rename", target=target, before=before, after=value)
        return {"ok": got == value, "read_back": got, "change_id": change["id"], "undo": "undo with this change_id"}
    if op == "set_area":
        area = _find_area(hass, value or "")
        if not area:
            raise HomeAssistantError(f"there's no room called {value!r}; create_area first (with the person's OK)")
        if ent:
            before = ent.area_id
            ents.async_update_entity(ent.entity_id, area_id=area.id)
            got = ents.async_get(ent.entity_id).area_id
        else:
            before = dev.area_id
            devs.async_update_device(dev.id, area_id=area.id)
            got = devs.async_get(dev.id).area_id
        change = await _record(hass, store, op="set_area", target=target, before=before, after=area.id)
        return {"ok": got == area.id, "read_back": area.name if got == area.id else got, "change_id": change["id"]}
    if op == "remove_entity":
        if not ent:
            raise HomeAssistantError("remove_entity takes an entity id")
        if not _orphaned(hass, ent):
            raise HomeAssistantError("refused: it isn't a leftover (something still provides it); turn it off or leave it")
        saved = {"entity_id": ent.entity_id, "domain": ent.domain, "platform": ent.platform, "unique_id": ent.unique_id,
                 "name": ent.name, "area_id": ent.area_id, "original_name": ent.original_name}
        ents.async_remove(ent.entity_id)
        if hass.states.get(ent.entity_id) is not None:
            hass.states.async_remove(ent.entity_id)
        change = await _record(hass, store, op="remove_entity", target=ent.entity_id, before=saved, after=None)
        return {"ok": ents.async_get(ent.entity_id) is None, "read_back": "gone from Home Assistant's list", "change_id": change["id"]}
    raise HomeAssistantError("op is rename, set_area, create_area or remove_entity")


async def _record(hass: HomeAssistant, store: Store, **row: Any) -> dict[str, Any]:
    return await hass.async_add_executor_job(store.append, "changes", row)


async def changes(hass: HomeAssistant, store: Store, limit: int = 20) -> dict[str, Any]:
    """The latest changes Sunrise made to the house, newest first, each with whether it's been undone."""
    rows = await hass.async_add_executor_job(store.rows, "changes")
    out = [{"change_id": r.get("id"), "when": r.get("ts"), "what": r.get("op"), "target": r.get("target"),
            "before": r.get("before") if not isinstance(r.get("before"), dict) else r["before"].get("alias") or r["before"].get("entity_id"),
            "undone": bool(r.get("undone"))} for r in rows[-max(1, min(limit, 100)):]]
    return {"changes": out[::-1], "count": len(rows), "note": "undo takes a change_id; skills and memory have their own history tools"}


async def undo(hass: HomeAssistant, store: Store, change_id: str) -> dict[str, Any]:
    rows = await hass.async_add_executor_job(store.rows, "changes")
    row = next((r for r in rows if r.get("id") == change_id), None)
    if not row:
        raise HomeAssistantError(f"no change {change_id!r}; recent ones: {[r['id'] for r in rows[-5:]]}")
    if row.get("undone"):
        return {"ok": True, "changed": False, "note": "already undone"}
    ents, devs, areas = er.async_get(hass), dr.async_get(hass), ar.async_get(hass)
    op, target, before = row["op"], row["target"], row.get("before")
    if op == "rename":
        if ents.async_get(target):
            ents.async_update_entity(target, name=before)
        else:
            devs.async_update_device(target, name_by_user=before)
    elif op == "set_area":
        if ents.async_get(target):
            ents.async_update_entity(target, area_id=before)
        else:
            devs.async_update_device(target, area_id=before)
    elif op == "create_area":
        if areas.async_get_area(target):
            areas.async_delete(target)
    elif op == "remove_entity":
        e = ents.async_get_or_create(before["domain"], before["platform"], before["unique_id"],
                                     suggested_object_id=before["entity_id"].split(".", 1)[1], original_name=before.get("original_name"))
        if before.get("name") or before.get("area_id"):
            ents.async_update_entity(e.entity_id, name=before.get("name"), area_id=before.get("area_id"))
    elif op == "update_host":
        entry = hass.config_entries.async_get_entry(row["entry_id"])
        if not entry:
            raise HomeAssistantError("that device's integration entry is gone; nothing to undo")
        hass.config_entries.async_update_entry(entry, data={**entry.data, "host": before})
        await hass.config_entries.async_reload(entry.entry_id)
    elif op == "add_integration":
        if hass.config_entries.async_get_entry(target):
            await hass.config_entries.async_remove(target)
    elif op in ("routine_save", "routine_delete", "routine_suggest", "routine_keep", "routine_dismiss"):
        from .routines import undo_routine  # noqa: PLC0415

        await undo_routine(hass, row)
    else:
        raise HomeAssistantError(f"can't undo {op}")
    row["undone"] = time.time()
    await hass.async_add_executor_job(store.rewrite, "changes", rows)
    return {"ok": True, "undone": op, "target": target}


# --- the setup: what Home Assistant itself can tell ----------------------------------------------

# The router as Home Assistant knows it: devices of an integration that talks to a router, or that
# call themselves one; sensors on those devices, or that read like the internet link. Hints, not a
# list of brands: whatever is found is reported by its own maker and model.
ROUTER_INTEGRATIONS = {"upnp", "fritz", "netgear", "asuswrt", "unifi", "tplink_omada", "mikrotik", "keenetic_ndms2", "huawei_lte",
                       "luci", "ubus", "ruckus_unleashed", "vodafone_station", "sfr_box", "freebox", "synology_srm", "netgear_lte"}
SPEED_INTEGRATIONS = {"speedtestdotnet", "fastdotcom"}
ROUTER_WORDS = re.compile(r"router|gateway|modem", re.I)
WAN_RX = re.compile(r"(^|[._])wan([._]|$)|wan_status|internet", re.I)


def router_facts(hass: HomeAssistant) -> dict[str, Any]:
    """{devices: [{name, manufacturer, model, integration, found_by}], sensors: [entity ids], wan: [entity ids]}.
    Never the house's public address."""
    devs, ents = dr.async_get(hass), er.async_get(hass)
    found: dict[str, dict[str, Any]] = {}
    for d in devs.devices:
        if not device_seen(hass, d.id):
            continue
        entry = hass.config_entries.async_get_entry(d.config_entry_id) if d.config_entry_id else None
        by = entry.domain if entry and entry.domain in ROUTER_INTEGRATIONS else None
        if by or ROUTER_WORDS.search(f"{d.model or ''} {d.name or ''} {d.name_by_user or ''}"):
            found[d.id] = {"name": d.name_by_user or d.name, "manufacturer": d.manufacturer, "model": d.model,
                           "integration": entry.domain if entry else None, "found_by": "integration" if by else "name"}
    sensors, wan = [], []
    for st in hass.states.async_all(("sensor", "binary_sensor")):
        if "external_ip" in st.entity_id or not seen(st.entity_id):
            continue
        reg = ents.async_get(st.entity_id)
        if (reg and (reg.device_id in found or reg.platform in SPEED_INTEGRATIONS)) or ROUTER_WORDS.search(st.entity_id) or WAN_RX.search(st.entity_id):
            sensors.append(st.entity_id)
            if WAN_RX.search(st.entity_id) and st.domain == "binary_sensor":
                wan.append(st.entity_id)
    return {"devices": list(found.values())[:5], "sensors": sensors[:10], "wan": wan}


async def setup_facts(hass: HomeAssistant) -> dict[str, Any]:
    """How this Home Assistant is installed and reached, detected fresh each time. What only people
    know (the provider, the router, quirks) lives in the memory file house.md."""
    from homeassistant.helpers.system_info import async_get_system_info  # noqa: PLC0415

    try:
        info = await async_get_system_info(hass)
    except Exception:  # noqa: BLE001
        info = {}
    install = str(info.get("installation_type") or "Unknown")
    kind = {"Home Assistant OS": "haos", "Home Assistant Container": "container", "Home Assistant Supervised": "supervised", "Unsupported Third Party Container": "container",
            "Home Assistant Core": "core"}.get(install, "unknown")
    found = router_facts(hass)
    router: dict[str, Any] = {"devices": found["devices"], "sensors": found["sensors"]}
    if not found["devices"]:
        router["note"] = "Home Assistant doesn't know the router; ask the person, and keep its make, model and provider in house.md."
    mcp = [e for e in hass.config_entries.async_entries("mcp_server")]
    served = []
    for e in mcp:
        if e.data.get("all_llm_apis"):
            served.append("all")
        served.extend(e.data.get("llm_hass_api") or [])
    remote = []
    if "cloud" in hass.config.components:
        remote.append("nabu_casa_possible")
    if hass.config.external_url:
        remote.append("external_url_set")
    return {"install_type": kind, "install_type_words": install, "ha_version": HA_VERSION,
            "access": {"sunrise_tools": True, "mcp_server": bool(mcp),
                       "mcp_serves_this_api": LLM_API_ID in served or "all" in served},
            "router": router, "remote_access": remote or ["none_detected"]}


# --- usage -----------------------------------------------------------------------------------------

USAGE_DOMAINS = ("light", "switch", "fan", "media_player", "climate", "cover")


class UsageTally:
    """Who changes what, live: Home Assistant's history keeps states but not who made each change,
    so the integration counts each change's actor (a person, an automation, the device) as it
    happens, by entity and hour. Saved to usage.json every 10 minutes and on unload."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.data: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        self.data = self.store.get("usage", {}) or {}

    def save(self) -> None:
        self.store.put("usage", self.data)

    def add(self, entity_id: str, new_state: str, context: Context, when) -> None:
        row = self.data.setdefault(entity_id, {"by": {}, "on_hours": {}, "days": []})
        who = "person" if context.user_id else ("automation" if context.parent_id else "device_or_unknown")
        row["by"][who] = row["by"].get(who, 0) + 1
        if new_state == "on":
            local = dt_util.as_local(when)
            h = str(local.hour)
            row["on_hours"][h] = row["on_hours"].get(h, 0) + 1
            day = local.date().isoformat()
            if day not in row["days"]:
                row["days"] = (row["days"] + [day])[-60:]


async def usage(hass: HomeAssistant, tally: UsageTally | None, days: int = 14) -> dict[str, Any]:
    """How each controllable thing was used: changes and on-hours from the recorder's history,
    plus who made the changes from the live tally."""
    days = max(1, min(int(days), 30))
    ids = [s.entity_id for s in hass.states.async_all() if s.domain in USAGE_DOMAINS and seen(s.entity_id)]
    hist: dict[str, list] = {}
    if "recorder" in hass.config.components and ids:
        from homeassistant.components.recorder import get_instance, history  # noqa: PLC0415

        start = dt_util.utcnow() - timedelta(days=days)
        hist = await get_instance(hass).async_add_executor_job(
            history.get_significant_states, hass, start, None, ids, None, False, False, False, True)
    elif not tally or not tally.data:
        return {"error": "Home Assistant's history (recorder) isn't running and nothing has been counted yet, so there's no usage to learn from."}
    out = []
    for eid in ids:
        states = [s for s in hist.get(eid, []) if isinstance(s, State)]
        live = (tally.data.get(eid) if tally else None) or {}
        ons = [s for s in states if s.state == "on"]
        hours = Counter(dt_util.as_local(s.last_changed).hour for s in ons) or Counter({int(h): n for h, n in live.get("on_hours", {}).items()})
        days_on = len({dt_util.as_local(s.last_changed).date() for s in ons}) or len(live.get("days", []))
        if not states and not live:
            continue
        out.append({"id": eid, "name": _name(hass, eid), "changes": len(states), "turned_on": len(ons), "days_used": days_on,
                    "common_hours": [h for h, _ in hours.most_common(3)], "by": live.get("by", {})})
    out.sort(key=lambda r: -(r["changes"] or sum(r["by"].values())))
    return {"days": days, "things": out[:40],
            "note": "Evidence for suggestions: a habit is the same hour on many of the days, done by a person. "
                    "'by' counts changes since this integration was installed."}


# --- backup -------------------------------------------------------------------------------------

async def backup(hass: HomeAssistant, op: str, wait_s: float = 40.0) -> dict[str, Any]:
    """Home Assistant's own backup to its local storage (never a cloud location), then read back.
    Waits at most 40 s: the MCP Server ends a request at 60 s; a longer backup keeps running and
    op=list confirms it."""
    if "backup" not in hass.config.components:
        return {"error": "Home Assistant's backup feature isn't loaded, so I can't make a backup. Don't make changes yet.",
                "confirmed": False}
    from homeassistant.components.backup.const import DATA_MANAGER  # noqa: PLC0415

    manager = hass.data[DATA_MANAGER]

    async def listed() -> list[dict[str, Any]]:
        backups, _errors = await manager.async_get_backups()
        rows = [{"id": b.backup_id, "name": b.name, "date": b.date, "size_mb": round((b.size or 0) / 1e6, 1)} for b in backups.values()]
        return sorted(rows, key=lambda r: r["date"], reverse=True)

    if op == "list":
        rows = await listed()
        return {"backups": rows[:10], "count": len(rows)}
    if op != "create":
        raise HomeAssistantError("op is create or list")
    local = list(manager.local_backup_agents)
    if not local:
        return {"error": "Home Assistant has no local backup location, so I made no backup.", "confirmed": False}
    started = dt_util.utcnow()
    before = {r["id"] for r in await listed()}
    task = hass.async_create_task(manager.async_create_backup(
        agent_ids=[local[0]], include_addons=None, include_all_addons=False, include_database=True,
        include_folders=None, include_homeassistant=True, name=f"Sunrise {dt_util.now().strftime('%Y-%m-%d %H:%M')}",
        password=None))
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=wait_s)
    except TimeoutError:
        return {"confirmed": False, "running": True,
                "say": "The backup is still being made. Check with op=list in a minute; don't make changes until it's listed."}
    except Exception as exc:  # noqa: BLE001
        return {"confirmed": False, "error": f"The backup failed: {str(exc)[:200]}. Don't make changes."}
    new = [r for r in await listed() if r["id"] not in before]
    if not new:
        return {"confirmed": False, "error": "Home Assistant says it finished, but no new backup is listed. Don't make changes."}
    return {"confirmed": True, "backup": new[0], "started": started.isoformat(timespec="seconds"),
            "restore": "Settings → System → Backups → pick this one → Restore."}
