"""Routines: Home Assistant automations made, changed, tried and removed by asking. Uses Home Assistant's
own pieces only: its validator, its automations.yaml (the file its editor writes), automation.reload and
automation.trigger. Every save and delete is in the change log, so `undo` puts the old one back."""

from __future__ import annotations

import re
import uuid
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .house import _record, guarded, nearest
from .store import Store

DOMAIN = "automation"
FILE = "automations.yaml"
ENTITY_ID = re.compile(r"\b([a-z_]+\.[a-z0-9_]+)\b")
SOUND = ("media_player.", "tts.", "notify.")


def _read(path: str) -> list[dict[str, Any]]:
    from homeassistant.util.yaml import load_yaml  # noqa: PLC0415

    try:
        data = load_yaml(path)
    except FileNotFoundError:
        return []
    return list(data) if isinstance(data, list) else []


def _write(path: str, rows: list[dict[str, Any]]) -> None:
    from homeassistant.util.file import write_utf8_file_atomic  # noqa: PLC0415
    from homeassistant.util.yaml import dump  # noqa: PLC0415

    write_utf8_file_atomic(path, dump(rows))


def _entity(hass: HomeAssistant, rid: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(DOMAIN, DOMAIN, rid)


def _things(config: Any) -> list[str]:
    """Every entity id a routine's config names under an entity_id key, wherever it sits."""
    found: list[str] = []

    def walk(v: Any, named: bool = False) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k == "entity_id")
        elif isinstance(v, list):
            for x in v:
                walk(x, named)
        elif isinstance(v, str) and named:
            found.extend(ENTITY_ID.fullmatch(p.strip()).group(1) for p in v.split(",") if ENTITY_ID.fullmatch(p.strip()))

    walk(config)
    return list(dict.fromkeys(found))


def check(hass: HomeAssistant, config: dict[str, Any]) -> dict[str, Any]:
    """What a routine touches: things Home Assistant doesn't have, and things that need the person's yes."""
    actions = config.get("actions") or config.get("action") or []
    missing = [{"id": e, "nearest": nearest(hass, e)} for e in _things(config) if hass.states.get(e) is None]
    acted = _things(actions)
    return {"missing": missing,
            "guarded": [e for e in acted if hass.states.get(e) is not None and (guarded(hass, e) or e.startswith("climate."))],
            "makes_sound": any(e.startswith(SOUND) for e in acted)}


async def _reload(hass: HomeAssistant, rid: str) -> None:
    if not hass.services.has_service(DOMAIN, "reload"):
        raise HomeAssistantError("Home Assistant's automations aren't loaded, so the routine was saved but can't run.")
    await hass.services.async_call(DOMAIN, "reload", {"id": rid}, blocking=True)
    await hass.async_block_till_done()


async def _put(hass: HomeAssistant, rid: str, config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Write (or with None, remove) one routine in automations.yaml; returns what was there before."""
    path = hass.config.path(FILE)
    rows = await hass.async_add_executor_job(_read, path)
    before = next((r for r in rows if r.get("id") == rid), None)
    rows = [r for r in rows if r.get("id") != rid]
    if config is not None:
        rows.append({"id": rid, **{k: v for k, v in config.items() if k != "id"}})
    await hass.async_add_executor_job(_write, path, rows)
    return before


async def routine(hass: HomeAssistant, store: Store, a: dict[str, Any]) -> dict[str, Any]:
    op = a.get("op", "list")
    rid = (a.get("id") or "").strip()
    path = hass.config.path(FILE)
    if op == "list":
        rows = await hass.async_add_executor_job(_read, path)
        by_id = {r.get("id"): r for r in rows}
        out = []
        for st in hass.states.async_all(DOMAIN):
            i = st.attributes.get("id")
            out.append({"id": i, "entity_id": st.entity_id, "name": st.name, "on": st.state == "on",
                        "last_ran": str(st.attributes.get("last_triggered") or "never"), "editable": i in by_id})
        return {"routines": out, "count": len(out)}
    if op == "get":
        rows = await hass.async_add_executor_job(_read, path)
        row = next((r for r in rows if r.get("id") == rid), None)
        if not row:
            raise HomeAssistantError(f"no editable routine {rid!r}; use op=list")
        return {"id": rid, "config": row, "entity_id": _entity(hass, rid)}
    if op in ("check", "save"):
        config = a.get("config")
        if not isinstance(config, dict) or not (config.get("alias") or "").strip():
            raise HomeAssistantError("config must be an automation (alias, triggers, conditions, actions) with a name in alias")
        from homeassistant.components.automation.config import async_validate_config_item  # noqa: PLC0415

        rid = rid or uuid.uuid4().hex
        try:
            await async_validate_config_item(hass, rid, dict(config))
        except Exception as exc:  # noqa: BLE001  (vol.Invalid, HomeAssistantError: all mean "not valid")
            return {"ok": False, "valid": False, "why": str(exc)[:400], "saved": False}
        found = check(hass, config)
        if op == "check" or found["missing"]:
            return {"ok": not found["missing"], "valid": True, "saved": False, **found,
                    **({"why": "it names things Home Assistant doesn't have; nothing was saved"} if found["missing"] else {})}
        if (found["guarded"] or found["makes_sound"]) and not a.get("confirmed"):
            return {"ok": False, "valid": True, "saved": False, **found,
                    "why": "it moves a lock, alarm, garage door or heating, or makes sound; save it only after the person "
                           "says yes to exactly this (confirmed=true)"}
        before = await _put(hass, rid, config)
        await _reload(hass, rid)
        change = await _record(hass, store, op="routine_save", target=rid, before=before, after=config)
        eid = _entity(hass, rid)
        st = hass.states.get(eid) if eid else None
        return {"ok": st is not None, "saved": True, "id": rid, "entity_id": eid, "on": bool(st and st.state == "on"),
                "change_id": change["id"], **found,
                **({} if st else {"why": "saved to automations.yaml, but Home Assistant didn't load it: its configuration may not include that file"})}
    if op == "delete":
        before = await _put(hass, rid, None)
        if before is None:
            raise HomeAssistantError(f"no editable routine {rid!r}; use op=list")
        eid = _entity(hass, rid)
        if eid:
            er.async_get(hass).async_remove(eid)
        await _reload(hass, rid)
        change = await _record(hass, store, op="routine_delete", target=rid, before=before, after=None)
        return {"ok": _entity(hass, rid) is None, "deleted": rid, "change_id": change["id"]}
    if op == "try":
        eid = _entity(hass, rid)
        if not eid or hass.states.get(eid) is None:
            raise HomeAssistantError(f"no loaded routine {rid!r}; use op=list")
        rows = await hass.async_add_executor_job(_read, path)
        found = check(hass, next((r for r in rows if r.get("id") == rid), {}))
        if (found["guarded"] or found["makes_sound"]) and not a.get("confirmed"):
            return {"ok": False, "ran": False, **found, "why": "running it needs the person's yes (confirmed=true)"}
        await hass.services.async_call(DOMAIN, "trigger", {"entity_id": eid, "skip_condition": True}, blocking=True)
        await hass.async_block_till_done()
        st = hass.states.get(eid)
        return {"ok": True, "ran": True, "entity_id": eid, "last_ran": str(st.attributes.get("last_triggered") if st else None),
                "next": "read back the things it changes (house_map), then put them back"}
    raise HomeAssistantError("op is list, get, check, save, delete or try")


async def undo_routine(hass: HomeAssistant, row: dict[str, Any]) -> None:
    rid, before = row["target"], row.get("before")
    await _put(hass, rid, before)
    if before is None and (eid := _entity(hass, rid)):
        er.async_get(hass).async_remove(eid)
    await _reload(hass, rid)
