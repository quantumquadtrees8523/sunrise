"""Discovered devices: what Home Assistant found on the network but nobody added yet (its
Settings → Devices & services → Discovered list). Lists them with what each still needs, and accepts
one only when its current step is a plain confirm: never a field, a sign-in, a code or a password.
An accepted device is in the change log, so `undo` removes the entry it made."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, UnknownFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .const import DISCOVERY_SOURCES, GUARDED_PLATFORMS
from .house import _record
from .store import Store

SECRET_RX = re.compile(r"pass|pin|code|token|key|secret|auth", re.IGNORECASE)
WHERE = "Settings → Devices & services → Discovered"


def _flows(hass: HomeAssistant) -> list[dict[str, Any]]:
    return [f for f in hass.config_entries.flow.async_progress() if f.get("context", {}).get("source") in DISCOVERY_SOURCES]


def _step(hass: HomeAssistant, flow_id: str) -> dict[str, Any] | None:
    """The step the flow is showing now (type, schema, placeholders), as Home Assistant's own
    frontend sees it, read without running the step again."""
    flow = getattr(hass.config_entries.flow, "_progress", {}).get(flow_id)
    return getattr(flow, "cur_step", None)


TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _kind(v: Any) -> str:
    if v in TYPES:
        return TYPES[v]
    if sel := getattr(v, "selector_type", None):  # Home Assistant's selectors
        return str(sel)
    if hasattr(v, "container"):  # vol.In
        return "choice"
    return type(v).__name__.lower()


def _fields(schema: Any) -> list[dict[str, Any]]:
    """Each field the form asks for: its name, a plain type, and whether it looks like a secret."""
    out = []
    for key, v in (getattr(schema, "schema", None) or {}).items():
        name = str(getattr(key, "schema", key))
        out.append({"name": name, "type": _kind(v), **({"secret": True} if SECRET_RX.search(name) else {})})
    return out


def needs(step: dict[str, Any] | None) -> dict[str, Any]:
    """What the current step wants: confirm (nothing but a yes), fields, sign_in, choice, waiting or unknown."""
    if not step:
        return {"kind": "unknown"}
    kind = step.get("type")
    if kind is FlowResultType.FORM:
        fields = _fields(step.get("data_schema"))
        if not fields:
            return {"kind": "confirm"}
        return {"kind": "fields", "fields": fields, **({"secret": True} if any(f.get("secret") for f in fields) else {})}
    if kind is FlowResultType.EXTERNAL_STEP:
        return {"kind": "sign_in"}
    if kind is FlowResultType.MENU:
        return {"kind": "choice", "options": list(step.get("menu_options") or [])}
    if kind is FlowResultType.SHOW_PROGRESS:
        return {"kind": "waiting"}
    return {"kind": "unknown"}


async def _integration(hass: HomeAssistant, domain: str) -> tuple[str, list[str]]:
    """The integration's name and which guarded kinds of thing it can make (locks, alarms, doors, heating, valves)."""
    try:
        integ = await async_get_integration(hass, domain)
    except IntegrationNotFound:
        return domain, []
    return integ.name, integ.platforms_exists(GUARDED_PLATFORMS)


async def _row(hass: HomeAssistant, f: dict[str, Any]) -> dict[str, Any]:
    step = _step(hass, f["flow_id"])
    name, guarded = await _integration(hass, f["handler"])
    shown = {**(f.get("context", {}).get("title_placeholders") or {}), **((step or {}).get("description_placeholders") or {})}
    row = {"flow_id": f["flow_id"], "integration": f["handler"], "integration_name": name,
           "device": {k: str(v) for k, v in shown.items() if v is not None}, "source": f["context"]["source"],
           "step": (step or {}).get("step_id"), "needs": needs(step)}
    if guarded:
        row["guarded"] = guarded
    return row


async def discovered(hass: HomeAssistant, store: Store, a: dict[str, Any]) -> dict[str, Any]:
    op = a.get("op") or "list"
    if op == "list":
        rows = [await _row(hass, f) for f in _flows(hass)]
        return {"discovered": rows, "count": len(rows),
                "note": "accept only works where needs.kind is confirm, with confirmed=true after the owner's yes. "
                        f"Everything else the owner finishes in Home Assistant: {WHERE}. Changes nothing."}
    if op != "accept":
        raise HomeAssistantError("op is list or accept")
    flow_id = a.get("flow_id") or ""
    f = next((x for x in _flows(hass) if x["flow_id"] == flow_id), None)
    if f is None:
        raise HomeAssistantError(f"no discovered device with flow_id {flow_id!r}; op=list lists them")
    row = await _row(hass, f)
    who = row["integration_name"]
    if row["needs"]["kind"] != "confirm":
        what = {"fields": "details to fill in", "sign_in": "a sign-in", "choice": "a choice",
                "waiting": "it to finish a step"}.get(row["needs"]["kind"], "a step I can't read")
        return {"ok": False, "accepted": False, "needs": row["needs"], "integration_name": who,
                "error": f"{who} needs {what}, so the owner finishes it in Home Assistant: {WHERE} → {who}. "
                         "I never fill in passwords, codes or sign-ins."}
    if not a.get("confirmed"):
        why = (f"{who} can control {', '.join(row['guarded'])}: say exactly what it is and get the owner's yes for this device"
               if row.get("guarded") else "say which device this is and get the owner's yes")
        return {"ok": False, "accepted": False, "integration_name": who, "error": f"not accepted: {why}, then call again with confirmed=true"}
    try:
        res = await hass.config_entries.flow.async_configure(flow_id, {})
    except UnknownFlow as exc:
        raise HomeAssistantError("that discovery is gone (added or dismissed meanwhile); op=list again") from exc
    kind = res.get("type")
    if kind is FlowResultType.CREATE_ENTRY:
        entry = res.get("result")
        entry_id = getattr(entry, "entry_id", None)
        change = await _record(hass, store, op="add_integration", target=entry_id, before=None,
                               after={"domain": row["integration"], "title": res.get("title"), "device": row["device"]})
        return {"ok": True, "accepted": True, "added": {"title": res.get("title"), "entry_id": entry_id, "integration": who},
                "loaded": bool(entry and hass.config_entries.async_get_entry(entry_id)), "change_id": change["id"],
                "next": "name it, put it in its room and test it (add-a-device)",
                "undo": "undo with this change_id removes it from Home Assistant"}
    if kind is FlowResultType.ABORT:
        return {"ok": False, "accepted": False, "aborted": res.get("reason"), "integration_name": who,
                "error": f"Home Assistant stopped adding {who}: {res.get('reason')}"}
    nxt = needs(_step(hass, flow_id) or res)
    return {"ok": False, "accepted": "partly", "integration_name": who, "next_step": res.get("step_id"), "needs": nxt,
            "say": f"{who} has one more step that needs the owner: {WHERE} → {who}."
            if nxt["kind"] != "confirm" else "it asks for another confirm: op=list shows it; ask the owner again"}
