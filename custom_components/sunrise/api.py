"""The agent-facing interface: one LLM API ("Sunrise") whose tools Home Assistant's MCP
Server serves at /api/mcp/sunrise, and whose prompt (the MCP prompt of the same name) is the
pack's rules plus its skills index.

Each tool is a small spec (name, title, description, parameters, honest annotations, handler).
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import probatio as P

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from . import diagnose as D
from . import house as H
from .const import DOMAIN, LLM_API_ID, LLM_API_NAME
from .net import Net
from .store import CHECKS, MemoryError_, SkillError, Store, sanitize, score


@dataclass
class Runtime:
    store: Store
    net: Net = field(default_factory=Net)
    options: dict[str, Any] = field(default_factory=dict)
    calls: deque = field(default_factory=lambda: deque(maxlen=300))
    act_cutoff: float | None = None
    reload_wait: float | None = None
    tally: Any = None  # house.UsageTally, set up in __init__
    memory_changed: Callable[[], None] | None = None  # tells sensor.sunrise_memory to read the files again


Handler = Callable[[HomeAssistant, Runtime, dict[str, Any], llm.LLMContext], Awaitable[dict[str, Any]]]


@dataclass
class Spec:
    name: str
    title: str
    description: str
    params: dict[Any, Any]
    annotations: llm.ToolAnnotations
    handler: Handler
    writes: bool = False


READ = llm.ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False)
WRITE = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=False, open_world=False)
WRITE_IDEMPOTENT = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False)
CHANGES = llm.ToolAnnotations(read_only=False, destructive=True, idempotent=False, open_world=False)
CHANGES_IDEMPOTENT = llm.ToolAnnotations(read_only=False, destructive=True, idempotent=True, open_world=False)
# `act` can call any action Home Assistant has, including ones that reach outside the house.
ANY_ACTION = llm.ToolAnnotations(read_only=False, destructive=True, idempotent=False, open_world=True)


def _job(hass: HomeAssistant, fn, *args, **kw):
    return hass.async_add_executor_job(partial(fn, *args, **kw))


# --- handlers -----------------------------------------------------------------------------------

async def _house_map(hass, rt, a, ctx):
    return await H.house_map(hass, a.get("room"), bool(a.get("everything")))


async def _act(hass, rt, a, ctx):
    return await H.act(hass, a["action"], list(a.get("entity_ids") or []), a.get("data") or {}, context=ctx.context,
                       confirmed=bool(a.get("confirmed")),
                       **({"cutoff": rt.act_cutoff} if rt.act_cutoff else {}))


async def _audit(hass, rt, a, ctx):
    return await H.audit(hass, rt.store)


async def _profile_get(hass, rt, a, ctx):
    return await H.profile_get(hass, rt.store, bool(a.get("refresh")))


async def _profile_update(hass, rt, a, ctx):
    return await H.profile_update(hass, rt.store, dict(a.get("updates") or {}))


async def _diagnose(hass, rt, a, ctx):
    return await D.diagnose(hass, rt.store, rt.net, a.get("target"), bool(a.get("power_cycled")))


async def _fix(hass, rt, a, ctx):
    kw = {"reload_wait": rt.reload_wait} if rt.reload_wait is not None else {}
    return await D.fix(hass, rt.store, rt.net, a["op"], a["target"], a.get("host"), **kw)


async def _registry_edit(hass, rt, a, ctx):
    return await H.registry_edit(hass, rt.store, a["op"], a.get("target", ""), a.get("value"))


async def _undo(hass, rt, a, ctx):
    return await H.undo(hass, rt.store, a["change_id"])


async def _changes(hass, rt, a, ctx):
    return await H.changes(hass, rt.store, int(a.get("limit") or 20))


async def _routine(hass, rt, a, ctx):
    from . import routines  # noqa: PLC0415

    return await routines.routine(hass, rt.store, a)


async def _backup(hass, rt, a, ctx):
    return await H.backup(hass, a.get("op", "list"))


async def _network(hass, rt, a, ctx):
    return await D.network_check(hass, rt.store, rt.net)


async def _usage(hass, rt, a, ctx):
    return await H.usage(hass, rt.tally, int(a.get("days") or 14))


async def _suggestions(hass, rt, a, ctx):
    rows = await _job(hass, rt.store.get, "suggestions", []) or []
    if a.get("op", "list") == "list":
        return {"suggestions": rows, "rule": "Never pitch an idea that is already here, whatever its status."}
    idea = (a.get("idea") or "").strip()
    status = a.get("status")
    if not idea or status not in ("pitched", "accepted", "declined", "later"):
        raise HomeAssistantError("record needs idea and status (pitched, accepted, declined or later)")
    key = " ".join(idea.lower().split())
    row = next((r for r in rows if r["key"] == key), None)
    if row is None:
        row = {"key": key, "idea": idea, "first": time.time()}
        rows.append(row)
    row.update(status=status, evidence=a.get("evidence") or row.get("evidence"), updated=time.time())
    await _job(hass, rt.store.put, "suggestions", rows)
    return {"ok": True, "recorded": row}


async def _list_skills(hass, rt, a, ctx):
    return {"skills": await _job(hass, rt.store.list),
            "note": "get_skill reads one. Built-ins the person edited are theirs (user_edited); update_available means a newer shipped text exists."}


async def _get_skill(hass, rt, a, ctx):
    text = await _job(hass, rt.store.read, a["name"])
    if text is None:
        raise HomeAssistantError(f"no skill {a['name']!r}; list_skills lists them")
    out = {"name": a["name"], "text": text}
    if a.get("include_references"):
        out["references"] = {r: await _job(hass, rt.store.reference, r) for r in ("RUBRIC.md", "HOUSE-BASICS.md")}
    return out


async def _skill_update(hass, rt, a, ctx):
    author = a.get("author") or "agent"
    if author == "product":
        raise HomeAssistantError("author is user or agent")
    try:
        return await _job(hass, rt.store.write, a["name"], a["text"], author=author, reason=a.get("reason", ""))
    except SkillError as exc:
        return {"ok": False, "error": str(exc)}


async def _skill_history(hass, rt, a, ctx):
    return {"name": a["name"], "versions": await _job(hass, rt.store.history, a["name"])}


async def _skill_revert(hass, rt, a, ctx):
    try:
        return await _job(hass, rt.store.revert, a["name"], int(a["version"]), author=a.get("author") or "agent")
    except SkillError as exc:
        return {"ok": False, "error": str(exc)}


async def _memory(hass: HomeAssistant, rt: Runtime, fn, *args, **kw) -> dict[str, Any]:
    try:
        out = await _job(hass, fn, *args, **kw)
    except MemoryError_ as exc:
        return {"ok": False, "error": str(exc)}
    if rt.memory_changed:
        rt.memory_changed()
    return out


async def _memory_list(hass, rt, a, ctx):
    return {"files": await _job(hass, rt.store.memory_list), "folder": str(rt.store.memory_dir),
            "note": "Dated claims, not truths: re-check anything that changes over time before acting on it."}


async def _memory_read(hass, rt, a, ctx):
    try:
        text = await _job(hass, rt.store.memory_read, a["name"])
    except MemoryError_ as exc:
        return {"ok": False, "error": str(exc)}
    if text is None:
        return {"ok": False, "error": f"no memory file {a['name']!r}; memory_list lists them"}
    return {"name": a["name"], "text": text}


async def _memory_write(hass, rt, a, ctx):
    return await _memory(hass, rt, rt.store.memory_write, a["name"], a["text"], author=a.get("author") or "agent",
                         reason=a.get("reason", ""))


async def _memory_delete(hass, rt, a, ctx):
    return await _memory(hass, rt, rt.store.memory_delete, a["name"], author=a.get("author") or "agent", reason=a.get("reason", ""))


async def _memory_history(hass, rt, a, ctx):
    try:
        return {"name": a["name"], "versions": await _job(hass, rt.store.memory_history, a["name"])}
    except MemoryError_ as exc:
        return {"ok": False, "error": str(exc)}


async def _memory_revert(hass, rt, a, ctx):
    return await _memory(hass, rt, rt.store.memory_revert, a["name"], int(a["version"]), author=a.get("author") or "agent")


async def _log_run(hass, rt, a, ctx):
    op = a.get("op", "record")
    if op == "calls":
        since = float(a.get("since") or 0)
        return {"calls": [c for c in rt.calls if c["ts"] >= since]}
    rows = await _job(hass, rt.store.rows, "runs")
    if op == "list":
        out = [r for r in rows if (not a.get("skill") or r.get("skill") == a["skill"])
               and (a.get("below") is None or r.get("score", 6) < int(a["below"]))]
        return {"runs": out[-int(a.get("limit") or 20):]}
    if op == "export":
        names = await _house_names(hass)
        path = rt.store.root / "share" / f"runs-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(sanitize(r, names), ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

        await _job(hass, write)
        return {"ok": True, "file": str(path), "runs": len(rows),
                "note": "Names, addresses and ids are replaced. Nothing was sent; the person can share this file by hand."}
    checks = {c: bool((a.get("checks") or {}).get(c)) for c in CHECKS}
    row = {"skill": a.get("skill"), "request": a.get("request"), "tried": a.get("tried"), "outcome": a.get("outcome"),
           "checks": checks, "broke_rule": bool(a.get("broke_rule")), "notes": a.get("notes"),
           "score": score(checks, bool(a.get("broke_rule")))}
    saved = await _job(hass, rt.store.append, "runs", row)
    return {"ok": True, "run": saved, "met_rubric": saved["score"] == 6,
            **({"next": "this run missed the rubric: fix the skill with skill_update, then run it again"} if saved["score"] < 6 else {})}


async def _house_names(hass: HomeAssistant) -> list[str]:
    from homeassistant.helpers import area_registry as ar, device_registry as dr  # noqa: PLC0415

    names = [a.name for a in ar.async_get(hass).areas.values()]
    names += [d.name_by_user or d.name or "" for d in dr.async_get(hass).devices]
    names += [str(s.attributes.get("friendly_name") or "") for s in hass.states.async_all()]
    names += [u.name or "" for u in await hass.auth.async_get_users()]
    return [n for n in names if n]


# --- the specs ----------------------------------------------------------------------------------

def _o(key: str, desc: str, **kw):
    return P.Optional(key, description=desc, **kw)


def _r(key: str, desc: str):
    return P.Required(key, description=desc)


SPECS: list[Spec] = [
    Spec("house_map", "House map", "Rooms -> devices -> things with their state and real entity ids, compact; things with no room last. "
         "Use it to find the real thing before acting.", {_o("room", "only this room"): str,
                                                          _o("everything", "include hidden, config and diagnostic things"): bool}, READ, _house_map),
    Spec("act", "Do something and check it", "Perform one Home Assistant action (e.g. light.turn_on) on things, then read each back: "
         "CHECKED (it shows the change), NOT CONFIRMED (it didn't show in ~6 s) or UNREACHABLE (unavailable: not tried, don't retry). "
         "Locks, alarms and garage doors need confirmed=true after the person said yes.",
         {_r("action", "domain.action, e.g. light.turn_off"): str, _o("entity_ids", "the things, from house_map"): [str],
          _o("data", "action data, e.g. {\"brightness_pct\": 40}"): dict, _o("confirmed", "the person said yes to this lock/alarm/garage action"): bool},
         ANY_ACTION, _act, writes=True),
    Spec("audit", "Audit the house", "What's dead, not in a room, duplicated, badly named or leftover, Home Assistant's noisy "
         "integrations, and what changed since the last audit. Changes nothing in the house (keeps a private snapshot to compare next time).",
         {}, READ, _audit),
    Spec("profile_get", "Read the setup profile", "The house's technical profile: install type, HA version, access, counts, "
         "internet provider and router, remote access. Read it first in every skill. refresh=true detects again.",
         {_o("refresh", "detect again now"): bool}, READ, _profile_get),
    Spec("profile_update", "Update the setup profile", "Add what only the agent or person knows: access (how you reach the house), "
         "isp (fios, spectrum, other), router, remote_access, notes, quirks. Merges; never asks for passwords.",
         {_r("updates", "fields to set"): dict}, WRITE_IDEMPOTENT, _profile_update, writes=True),
    Spec("diagnose_device", "Why is it unreachable?", "Why devices dropped: HA's record, the address HA uses, whether it answers on the "
         "home network, and for WiZ bulbs a search of the network by MAC. Each device gets a cause: moved (fix in software), answering / "
         "not_loaded (reload), off_network (power-cycle at the switch), forgot_wifi (re-pair in the WiZ app), weak_signal. "
         "No target: everything unreachable. power_cycled=true after the person flipped the switches.",
         {_o("target", "a room, a device name, 'the kitchen lights', an entity or device id"): str,
          _o("power_cycled", "the person just turned these off and on"): bool}, READ, _diagnose),
    Spec("fix_device", "Fix a device in software", "op=reload_entry: reconnect Home Assistant to a device. op=update_host: point HA "
         "at a WiZ bulb's new address through WiZ's own setup (host optional: found by MAC); keeps the old address for undo. "
         "Never the router, Wi-Fi or passwords.",
         {_r("op", "reload_entry or update_host"): str, _r("target", "device_id from diagnose_device"): str,
          _o("host", "update_host: the new address"): str}, CHANGES, _fix, writes=True),
    Spec("registry_edit", "Rename or move a thing", "One undoable registry change: op=rename (value=new name), op=set_area (value=room), "
         "op=create_area (value=room name), op=remove_entity (only a leftover whose setup was deleted). Returns change_id for undo.",
         {_r("op", "rename, set_area, create_area or remove_entity"): str, _o("target", "entity id or device id"): str,
          _o("value", "the new name or the room"): str}, CHANGES, _registry_edit, writes=True),
    Spec("changes", "What Sunrise changed", "The latest changes made to the house through these tools, newest first: what, which "
         "thing, when, and whether it was undone. Each has a change_id for undo. Changes nothing.",
         {_o("limit", "how many, default 20"): int}, READ, _changes),
    Spec("routine", "Routines (automations)", "Home Assistant automations by asking. op=list: every routine and when it last ran. "
         "op=get: one routine's config. op=check: validate a config and report what it touches, saving nothing (the dry run). "
         "op=save: validate, save and load it (new, or replacing id); returns change_id for undo. op=try: run it once now, "
         "skipping its conditions. op=delete: remove it (undoable). Locks, alarms, garage doors, heating and sound need confirmed=true.",
         {_o("op", "list, get, check, save, try or delete"): str, _o("id", "the routine's id (omit to make a new one)"): str,
          _o("config", "the automation: alias, description, triggers, conditions, actions, mode"): dict,
          _o("confirmed", "the person said yes to exactly this, in this conversation"): bool}, CHANGES, _routine, writes=True),
    Spec("undo", "Undo a change", "Put back one change made by registry_edit, fix_device or routine, by its change_id.",
         {_r("change_id", "from the change's result"): str}, CHANGES_IDEMPOTENT, _undo, writes=True),
    Spec("backup", "Checkpoint Home Assistant", "A checkpoint to go back to if something breaks: a Home Assistant backup kept on "
         "this machine only, never sent anywhere. op=create: makes one, waits up to a minute and confirms it's listed. "
         "op=list: the latest ones. Make one before any change that isn't undoable in one step.",
         {_o("op", "create or list"): str}, WRITE, _backup, writes=True),
    Spec("network_check", "Check the home network", "The network from the house's side: router sensors (e.g. Fios WAN status and "
         "speed), whether the router answers, how many Wi-Fi devices are unreachable, the WiZ bulbs' signal, error counts. Changes nothing.",
         {}, READ, _network),
    Spec("usage", "How the house is used", "For each light, switch, fan, speaker and thermostat over the last days: changes, the hours it "
         "goes on, the days used, and whether a person or an automation did it.",
         {_o("days", "1-30, default 14"): int}, READ, _usage),
    Spec("suggestions", "Ideas already pitched", "op=list: every improvement idea already pitched and what the person said. "
         "op=record: save one (idea, status pitched/accepted/declined/later, evidence), so it's never pitched again.",
         {_o("op", "list or record"): str, _o("idea", "the idea in one line"): str, _o("status", "pitched, accepted, declined, later"): str,
          _o("evidence", "the numbers behind it"): str}, WRITE_IDEMPOTENT, _suggestions, writes=True),
    Spec("list_skills", "List skills", "Every skill in this house (built-in copies and the person's own) with its description, "
         "version and whether the person edited it.", {}, READ, _list_skills),
    Spec("get_skill", "Read a skill", "A skill's full SKILL.md; include_references=true adds the rubric and house basics.",
         {_r("name", "the skill's name"): str, _o("include_references", "also return RUBRIC.md and HOUSE-BASICS.md"): bool}, READ, _get_skill),
    Spec("skill_update", "Change or add a skill", "Write a skill's SKILL.md (new or changed). The old text is checkpointed first; "
         "the text must keep its frontmatter and the rubric reference, and an edit that weakens a safety rule is refused.",
         {_r("name", "lowercase-with-hyphens"): str, _r("text", "the whole SKILL.md"): str, _r("reason", "why, in one line"): str,
          _o("author", "user (the person asked) or agent"): str}, CHANGES, _skill_update, writes=True),
    Spec("skill_history", "A skill's versions", "Every checkpoint of a skill: version, time, author, reason, lines changed.",
         {_r("name", "the skill"): str}, READ, _skill_history),
    Spec("skill_revert", "Revert a skill", "Put an earlier version of a skill back (saved as a new version; history is kept).",
         {_r("name", "the skill"): str, _r("version", "from skill_history"): int, _o("author", "user or agent"): str},
         CHANGES_IDEMPOTENT, _skill_revert, writes=True),
    Spec("memory_list", "List memory", "Every memory file (Markdown under the house's sunrise/memory folder, which the owner can "
         "open): name, first line, size, when it changed. Read the relevant ones before you start.", {}, READ, _memory_list),
    Spec("memory_read", "Read a memory file", "One memory file's full text. Read the ones that bear on the request before acting.", {_r("name", "e.g. house.md or playbooks/router.md"): str},
         READ, _memory_read),
    Spec("memory_write", "Write a memory file", "Create or replace one memory file (the whole text). Use it for what you learned "
         "that will matter next time: the owner's preferences (owner.md), the house's facts (house.md), how a device or system works "
         "(playbooks/<thing>.md), dated runs (log.md). Date each fact. The old text is checkpointed. Secrets are refused.",
         {_r("name", "lowercase .md, at most two folders deep"): str, _r("text", "the whole file, Markdown"): str,
          _r("reason", "why, in one line"): str, _o("author", "user (the person asked) or agent"): str}, CHANGES, _memory_write, writes=True),
    Spec("memory_delete", "Delete a memory file", "Remove one memory file. Its text is checkpointed first, so memory_revert can bring it back.",
         {_r("name", "the file"): str, _r("reason", "why, in one line"): str, _o("author", "user or agent"): str},
         CHANGES_IDEMPOTENT, _memory_delete, writes=True),
    Spec("memory_history", "A memory file's versions", "Every checkpoint of a memory file: version, time, author, reason, lines changed.",
         {_r("name", "the file"): str}, READ, _memory_history),
    Spec("memory_revert", "Revert a memory file", "Put an earlier version of a memory file back (saved as a new version).",
         {_r("name", "the file"): str, _r("version", "from memory_history"): int, _o("author", "user or agent"): str},
         CHANGES_IDEMPOTENT, _memory_revert, writes=True),
    Spec("log_run", "Log a skill run", "op=record: what you tried, the outcome and the rubric checks R1-R6 (pass/fail); a run under 6 "
         "is what the next edit to that skill learns from. op=list (skill, below=6) reads runs; op=calls (since=unix time) lists this "
         "integration's tool calls; op=export writes a local copy with names and addresses stripped for the person to share by hand.",
         {_o("op", "record, list, calls or export"): str, _o("skill", "the skill"): str, _o("request", "what the person asked"): str,
          _o("tried", "what you did"): str, _o("outcome", "what happened, read back"): str,
          _o("checks", "{\"R1\": true, ...}"): dict, _o("broke_rule", "a fixed safety rule was broken"): bool,
          _o("notes", "evidence for each failed check"): str, _o("below", "list: runs scoring under this"): int,
          _o("since", "calls: unix time"): float, _o("limit", "list: how many"): int}, WRITE, _log_run, writes=True),
]


def _summary(result: dict[str, Any]) -> Any:
    text = json.dumps(result, default=str, ensure_ascii=False)
    return result if len(text) < 6000 else {"keys": list(result), "truncated": text[:2000]}


class SkillTool(llm.Tool):
    integration = DOMAIN

    def __init__(self, spec: Spec, rt: Runtime) -> None:
        self.spec = spec
        self.rt = rt
        self.name = spec.name
        self.title = spec.title
        self.description = spec.description
        self.parameters = P.Schema(spec.params)
        self.annotations = spec.annotations

    async def async_call(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> llm.ToolResult:
        args = dict(tool_input.tool_args or {})
        started = time.time()
        if self.spec.writes and not await _may_write(hass, llm_context):
            result, error = {"error": "Only a Home Assistant administrator's agent can change things."}, True
        else:
            try:
                result, error = await self.spec.handler(hass, self.rt, args, llm_context), False
            except (HomeAssistantError, ValueError, KeyError) as exc:
                result, error = {"error": str(exc).strip("'\"")}, True
        if isinstance(result, dict) and result.get("error") and not error:
            error = False  # a worded refusal the model should read, not a failed call
        self.rt.calls.append({"ts": started, "tool": self.name, "args": args, "error": error, "result": _summary(result)})
        return llm.ToolResult(data=json.loads(json.dumps(result, default=str)), error=error)


async def _may_write(hass: HomeAssistant, ctx: llm.LLMContext) -> bool:
    """A signed-in non-admin can read the house through this API but not change it. Home
    Assistant's own pipelines (no user, e.g. a voice satellite) act for the household."""
    user_id = ctx.context.user_id if ctx.context else None
    if not user_id:
        return True
    user = await hass.auth.async_get_user(user_id)
    return bool(user and user.is_admin)


RULES = """You look after this Home Assistant home with the Sunrise tools.
Fixed rules: never change router settings, Wi-Fi or passwords on your own (give steps; only a skill that says so
may read or change the router, after the person signs in themselves and says yes to each change; never type or
store a password); never lock, unlock, arm or open anything without the person's yes; take a checkpoint (backup op=create, confirmed; it stays on this machine) before a change that isn't undoable in
one step; every change undoable; unavailable means unreachable (diagnose, don't retry); suggest, never decide;
stay on the home network.
Done means: the real outcome, read back (act says CHECKED); plain words; at most 3 numbered steps for a person;
never a wrong instruction (read profile_get first); never claim success without read-back; no ids, addresses or
jargon unless asked. Start with profile_get. Follow a skill (get_skill) when one fits; log_run at the end.
Building blocks: the tools are the shared primitives (map, act with read-back, diagnose, routine, checkpoint, undo,
memory). The skills are repeatable jobs built on them. For a request that needs more than one skill, chain them:
finish one skill's own verify step before starting the next (add-a-device then routines; device-diagnosis then
wifi-diagnosis). If memory is empty, offer learn-the-house first.
Memory: read the memory files that bear on the request first (memory_read). They are dated claims: re-check what
changes over time. At the end, save what you verified and what the owner told you they prefer (memory_write),
dated, replacing what turned out wrong. Never store passwords, keys or tokens. The owner can read every file."""


class SunriseAPI(llm.API):
    def __init__(self, hass: HomeAssistant, rt: Runtime) -> None:
        super().__init__(hass=hass, id=LLM_API_ID, name=LLM_API_NAME)
        self.rt = rt

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        skills = await self.hass.async_add_executor_job(self.rt.store.list)
        index = "\n".join(f"- {s['name']}: {s['description']}" for s in skills)
        files = await self.hass.async_add_executor_job(self.rt.store.memory_list)
        memory = "\n".join(f"- {f['name']}: {f['first_line']}" for f in files[:60]) or "(none yet)"
        tools: list[llm.Tool] = [SkillTool(s, self.rt) for s in SPECS]
        try:  # tools other integrations' llm.py platforms contribute to this API (e.g. the date and time)
            from homeassistant.components.llm import async_get_tools  # noqa: PLC0415

            if "llm" in self.hass.config.components:
                tools += (await async_get_tools(self.hass, llm_context, self.id)).tools
        except ImportError:
            pass
        return llm.APIInstance(api=self, api_prompt=f"{RULES}\n\nSkills (get_skill name=...):\n{index}\n\nMemory (memory_read name=...):\n{memory}",
                               llm_context=llm_context, tools=tools, custom_serializer=llm.selector_serializer)
