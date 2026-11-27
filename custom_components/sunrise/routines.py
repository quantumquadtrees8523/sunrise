"""Routines: Home Assistant automations made, changed, tried and removed by asking. Uses Home Assistant's
own pieces only: its validator, its automations.yaml (the file its editor writes), automation.reload and
automation.trigger. Every save and delete is in the change log, so `undo` puts the old one back.

Suggestions (short term, routines only): op=suggest saves a routine switched off (initial_state false),
labelled "Suggested", with an id that starts `suggestion_`, without anyone's yes. It's inert: it never
fires on its own, so an agent running unattended (Console's nightly run) may make one. It may never touch
a lock, alarm, garage door, heating or anything that makes sound, nor anything not exposed to the
assistant. op=keep turns a suggestion into an ordinary routine (on, unlabelled); op=dismiss removes a
suggestion that's still off. Each is one change in the log, so `undo` works on all of them."""

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
SUGGESTION = "suggestion_"
SUGGESTED_LABEL = "Suggested"


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


def _label_id(hass: HomeAssistant, create: bool) -> str | None:
    from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

    labels = lr.async_get(hass)
    found = labels.async_get_label_by_name(SUGGESTED_LABEL)
    if found is None and create:
        found = labels.async_create(SUGGESTED_LABEL, icon="mdi:lightbulb-auto-outline",
                                    description="A routine Sunrise suggested. It stays off until it's kept.")
    return found.label_id if found else None


def _label(hass: HomeAssistant, eid: str | None, on: bool) -> None:
    if not eid or not (entry := er.async_get(hass).async_get(eid)) or (label := _label_id(hass, on)) is None:
        return
    labels = set(entry.labels) | {label} if on else set(entry.labels) - {label}
    er.async_get(hass).async_update_entity(eid, labels=labels)


def _state_of(hass: HomeAssistant, eids: list[str]) -> list[dict[str, Any]]:
    out = []
    for e in eids:
        st = hass.states.get(e)
        out.append({"id": e, "name": st.name if st else e, "now": st.state if st else "missing"})
    return out


async def _suggest(hass: HomeAssistant, store: Store, config: Any, allowed) -> dict[str, Any]:
    """Save a routine switched off and labelled Suggested. Inert, so no yes is needed; never anything guarded."""
    if not isinstance(config, dict) or not (config.get("alias") or "").strip():
        raise HomeAssistantError("config must be an automation (alias, triggers, conditions, actions) with a name in alias")
    from homeassistant.components.automation.config import async_validate_config_item  # noqa: PLC0415

    config = {k: v for k, v in config.items() if k not in ("id", "initial_state")}
    rid = SUGGESTION + uuid.uuid4().hex[:16]
    try:
        await async_validate_config_item(hass, rid, dict(config))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "valid": False, "why": str(exc)[:400], "saved": False}
    found = check(hass, config)
    acted = _things(config.get("actions") or config.get("action") or [])
    hidden = [e for e in acted if allowed is not None and hass.states.get(e) is not None and not allowed(e)]
    why = None
    if found["missing"]:
        why = "it names things Home Assistant doesn't have"
    elif found["guarded"] or found["makes_sound"]:
        why = "a suggestion may never move a lock, alarm, garage door or heating, or make sound"
    elif hidden:
        why = "it switches things the owner hasn't exposed to voice assistants"
    elif not acted:
        why = "it doesn't switch anything"
    if why:
        return {"ok": False, "valid": True, "saved": False, **found, "not_exposed": hidden, "why": why + "; nothing was saved"}
    config = {**config, "initial_state": False}
    await _put(hass, rid, config)
    await _reload(hass, rid)
    eid = _entity(hass, rid)
    _label(hass, eid, True)
    change = await _record(hass, store, op="routine_suggest", target=rid, before=None, after=config)
    st = hass.states.get(eid) if eid else None
    return {"ok": st is not None, "saved": True, "suggestion": True, "id": rid, "entity_id": eid,
            "on": bool(st and st.state == "on"), "things": acted, "change_id": change["id"], **found}


async def _suggestion_row(hass: HomeAssistant, rid: str) -> dict[str, Any]:
    if not rid.startswith(SUGGESTION):
        raise HomeAssistantError(f"{rid!r} isn't a suggestion; only routines made with op=suggest can be kept or dismissed")
    rows = await hass.async_add_executor_job(_read, hass.config.path(FILE))
    row = next((r for r in rows if r.get("id") == rid), None)
    if not row:
        raise HomeAssistantError(f"no suggestion {rid!r}; use op=list")
    return row


async def routine(hass: HomeAssistant, store: Store, a: dict[str, Any], allowed=None) -> dict[str, Any]:
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
                        "last_ran": str(st.attributes.get("last_triggered") or "never"), "editable": i in by_id,
                        **({"suggestion": True} if i in by_id and by_id[i].get("initial_state") is False and str(i).startswith(SUGGESTION) else {})})
        return {"routines": out, "count": len(out)}
    if op == "get":
        rows = await hass.async_add_executor_job(_read, path)
        row = next((r for r in rows if r.get("id") == rid), None)
        if not row:
            raise HomeAssistantError(f"no editable routine {rid!r}; use op=list")
        return {"id": rid, "config": row, "entity_id": _entity(hass, rid)}
    if op == "suggest":
        return await _suggest(hass, store, a.get("config"), allowed)
    if op == "keep":
        before = await _suggestion_row(hass, rid)
        after = {k: v for k, v in before.items() if k not in ("id", "initial_state")}
        await _put(hass, rid, after)
        await _reload(hass, rid)
        eid = _entity(hass, rid)
        if eid:
            await hass.services.async_call(DOMAIN, "turn_on", {"entity_id": eid}, blocking=True)
            _label(hass, eid, False)
        change = await _record(hass, store, op="routine_keep", target=rid, before=before, after=after)
        st = hass.states.get(eid) if eid else None
        return {"ok": bool(st and st.state == "on"), "kept": rid, "entity_id": eid, "on": bool(st and st.state == "on"),
                "change_id": change["id"]}
    if op == "dismiss":
        before = await _suggestion_row(hass, rid)
        if before.get("initial_state") is not False:
            raise HomeAssistantError(f"{rid!r} was kept, so it's an ordinary routine now: remove it with op=delete")
        await _put(hass, rid, None)
        if eid := _entity(hass, rid):
            er.async_get(hass).async_remove(eid)
        await _reload(hass, rid)
        change = await _record(hass, store, op="routine_dismiss", target=rid, before=before, after=None)
        return {"ok": _entity(hass, rid) is None, "dismissed": rid, "change_id": change["id"]}
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
        acted = _things(next((r for r in rows if r.get("id") == rid), {}).get("actions") or [])
        return {"ok": True, "ran": True, "entity_id": eid, "last_ran": str(st.attributes.get("last_triggered") if st else None),
                "things": _state_of(hass, acted),
                "next": "things is each thing it changes, read back after the run; put them back if this was a test"}
    raise HomeAssistantError("op is list, get, check, save, delete, try, suggest, keep or dismiss")


async def undo_routine(hass: HomeAssistant, row: dict[str, Any]) -> None:
    rid, before = row["target"], row.get("before")
    await _put(hass, rid, before)
    if before is None and (eid := _entity(hass, rid)):
        er.async_get(hass).async_remove(eid)
    await _reload(hass, rid)
    if before is not None and before.get("initial_state") is False and rid.startswith(SUGGESTION):
        # a kept suggestion put back, or a dismissed one brought back: off again, and labelled again
        if eid := _entity(hass, rid):
            await hass.services.async_call(DOMAIN, "turn_off", {"entity_id": eid}, blocking=True)
            _label(hass, eid, True)
