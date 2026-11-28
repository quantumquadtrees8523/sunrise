"""A person's hand wins. A routine is the house's guess; what someone just did (in the app, by asking, at a
wall switch, a scene they ran) is what they want now. Owner, 2026-11-28: "automations and reactions should be
ephemeral ... the user's preference must be respected in the immediate term. if that preference happens
regularly then the automations must be updated silently and auditably."

Now: when a routine's run switches a light, switch, fan or cover away from what a person set it to in the
last HOLD_S, Sunrise stops that run and puts the thing back as the person left it. Nobody is asked. It's a line
in Home Assistant's logbook and a row in hand.json, which `usage` reports as `overruled`.

Learned: once a person has overruled the same routine on the same thing on ADAPT_DAYS different days in the
last LEARN_DAYS, at about the same time of day, Sunrise changes the routine so it leaves that thing alone at
that time: only the step that switches it is wrapped in an "only outside these hours" check, so the rest of the
routine runs as before. That edit is one change in the log (`changes`, `undo`), the routine's description
and its "Adapted" label say what and why, and memory's log.md gets a line, so a person and any agent can
see it. Never a lock, alarm, garage door or gate (house.guarded).

Which run made a change is Home Assistant's own context: an automation's run fires `automation_triggered`
with the run's context, and everything the run switches carries that context's id. A run started by a
person (a button, or a change of theirs that triggered it) is their hand too."""

from __future__ import annotations

import copy
import time
from typing import Any

from homeassistant.core import Context, Event, HomeAssistant, State, callback
from homeassistant.util import dt as dt_util

from .listening import _clock, _day, _minute, _span
from .store import MemoryError_, Store

HAND_DOMAINS = ("light", "switch", "fan", "cover")
HOLD_S = 2 * 3600  # how long a person's change outranks a routine
LEARN_DAYS = 14
ADAPT_DAYS = 3
ADAPTED_LABEL = "Adapted"
KEPT_CONTEXTS = 500
LIGHT_KEPT = ("brightness", "color_temp_kelvin", "hs_color")  # what a light is put back with


def _trim(d: dict, n: int = KEPT_CONTEXTS) -> None:
    while len(d) > n:
        d.pop(next(iter(d)))


class Hand:
    def __init__(self, hass: HomeAssistant, store: Store) -> None:
        self.hass, self.store = hass, store
        self.runs: dict[str, dict[str, Any]] = {}  # an automation run's context id → which, what started it, whose
        self.people: dict[str, float] = {}  # context ids a signed-in person made, recently
        self.ours: dict[str, None] = {}  # contexts Sunrise used to put things back
        self.stopped: dict[str, None] = {}  # runs already stopped
        self.held: dict[str, dict[str, Any]] = {}  # thing → the person's last change of it
        self.data: dict[str, list] = {"overruled": [], "adapted": []}

    def load(self) -> None:
        got = self.store.get("hand", {}) or {}
        self.data = {k: list(got.get(k) or []) for k in ("overruled", "adapted")}

    def save(self) -> None:
        cutoff = time.time() - LEARN_DAYS * 86400
        self.data["overruled"] = [r for r in self.data["overruled"] if r["at"] >= cutoff]
        self.store.put("hand", self.data)

    # --- whose change is it ---------------------------------------------------------------------

    @callback
    def triggered(self, event: Event) -> None:
        """An automation started a run (`automation_triggered`, fired with the run's own context)."""
        ctx, source = event.context, str(event.data.get("source") or "")
        # A button or remote (an event trigger), a run someone started by hand (no trigger) or one a person's
        # own change set off: that run is the person's hand, not the house's guess.
        theirs = source.startswith("event ") or not source or ctx.parent_id in self.people
        self.runs[ctx.id] = {"routine": event.data.get("entity_id"), "name": event.data.get("name"), "source": source,
                             "person": theirs}
        _trim(self.runs)

    @callback
    def seen(self, context: Context) -> None:
        if context.user_id:
            self.people[context.id] = time.time()
            _trim(self.people)

    def automated(self, context: Context) -> bool:
        """A change a routine made on its own (not on a person's behalf). Clock-started runs have no parent
        context, so a parent alone doesn't tell; the run record does."""
        run = self.runs.get(context.id)
        return (not run["person"]) if run else bool(context.parent_id and not context.user_id)

    def _person(self, context: Context) -> bool:
        if context.id in self.ours:
            return False
        if run := self.runs.get(context.id):
            return run["person"]
        return bool(context.user_id) or not context.parent_id  # the app, a voice request, a wall switch

    # --- now: the hand wins -----------------------------------------------------------------------

    @callback
    def change(self, new: State) -> None:
        if new.domain not in HAND_DOMAINS or new.context.id in self.ours:
            return
        from .house import guarded  # noqa: PLC0415

        if guarded(self.hass, new.entity_id):
            return
        now = time.time()
        if self._person(new.context):
            attrs = {k: new.attributes[k] for k in LIGHT_KEPT if new.domain == "light" and new.attributes.get(k) is not None}
            if attrs.get("color_temp_kelvin"):
                attrs.pop("hs_color", None)
            self.held[new.entity_id] = {"state": new.state, "attrs": attrs, "at": now}
            return
        run = self.runs.get(new.context.id)
        held = self.held.get(new.entity_id)
        if not run or run["person"] or not held or now - held["at"] > HOLD_S or new.state == held["state"]:
            return
        self.hass.async_create_task(self._keep(new.entity_id, held, run, new.context.id, now))

    async def _keep(self, thing: str, held: dict[str, Any], run: dict[str, Any], run_id: str, now: float) -> None:
        ctx = Context()
        self.ours[ctx.id] = None
        _trim(self.ours)
        services = self.hass.services
        routine = run["routine"]
        if run_id not in self.stopped and routine and (st := self.hass.states.get(routine)) and st.state == "on":
            self.stopped[run_id] = None  # end this run so its later steps don't fight the person; it stays on for next time
            _trim(self.stopped)
            await services.async_call("automation", "turn_off", {"entity_id": routine, "stop_actions": True}, blocking=True, context=ctx)
            await services.async_call("automation", "turn_on", {"entity_id": routine}, blocking=True, context=ctx)
        domain = thing.split(".", 1)[0]
        if domain == "cover":
            service, data = ("open_cover" if held["state"] == "open" else "close_cover"), {}
        else:
            service, data = f"turn_{'on' if held['state'] == 'on' else 'off'}", (held["attrs"] if held["state"] == "on" else {})
        try:
            await services.async_call(domain, service, {"entity_id": thing, **data}, blocking=True, context=ctx)
        except Exception:  # noqa: BLE001  (the thing may be unreachable: still recorded, nothing else to do)
            pass
        minutes = max(1, round((now - held["at"]) / 60))
        row = {"at": round(now), "thing": thing, "kept": held["state"], "routine": routine, "name": run["name"],
               "source": run["source"], "after_min": minutes}
        self.data["overruled"].append(row)
        name = _name(self.hass, thing)
        await self._logbook(f"kept the {name} {held['state']}: someone set it by hand {minutes} min before "
                            f"{run['name']} changed it", thing)
        await self.learn(routine, thing)

    async def _logbook(self, message: str, entity_id: str) -> None:
        if self.hass.services.has_service("logbook", "log"):
            await self.hass.services.async_call("logbook", "log", {"name": "Sunrise", "message": message, "entity_id": entity_id},
                                                blocking=True, context=Context())

    # --- learned: the routine changes -----------------------------------------------------------

    async def learn(self, routine: str | None, thing: str) -> dict[str, Any] | None:
        """Adapt `routine` for `thing` once the person has overruled it often enough at about the same time."""
        if not routine or not (st := self.hass.states.get(routine)) or not (rid := st.attributes.get("id")):
            return None
        cutoff = time.time() - LEARN_DAYS * 86400
        rows = [r for r in self.data["overruled"]
                if r["routine"] == routine and r["thing"] == thing and r["at"] >= cutoff and not r.get("learned")]
        days = sorted({_day(r["at"]) for r in rows})
        if len(days) < ADAPT_DAYS or (span := _span([_minute(r["at"]) for r in rows])) is None:
            return None  # not often enough yet, or spread over the whole day: the person's hand keeps winning, nothing changes
        from . import routines as R  # noqa: PLC0415
        from .house import _record  # noqa: PLC0415

        before = next((r for r in await self.hass.async_add_executor_job(R._read, self.hass.config.path(R.FILE))
                       if r.get("id") == rid), None)
        if before is None:
            return None  # not one of automations.yaml's: Sunrise can't edit it, so the hand keeps winning
        a, b = f"{_clock(span[0])}:00", f"{_clock(span[1])}:00"
        name = _name(self.hass, thing)
        alias = f"Sunrise: leave the {name} alone {a[:5]}-{b[:5]}"
        actions, changed = _leave_alone(copy.deepcopy(before.get("actions") or before.get("action") or []), thing, a, b, alias)
        if not changed:
            return None  # it reaches the thing through an area, a device or a scene: no step to wrap
        kept = {r["kept"] for r in rows}
        evidence = (f"on {len(days)} days in the last {LEARN_DAYS} ({', '.join(days)}), someone had set the {name} "
                    f"{'/'.join(sorted(kept))} by hand and this routine changed it between {a[:5]} and {b[:5]}, so it now "
                    f"leaves the {name} alone then")
        after = {k: v for k, v in before.items() if k not in ("id", "action")}
        after["actions"] = actions
        after["description"] = ((before.get("description") or "").rstrip() + "\n\n").lstrip() + \
            f"Adapted by Sunrise on {dt_util.now().date().isoformat()}: {evidence}."
        await R._put(self.hass, rid, after)
        await R._reload(self.hass, rid)
        R._label(self.hass, R._entity(self.hass, rid), True, ADAPTED_LABEL)
        change = await _record(self.hass, self.store, op="routine_adapt", target=rid, before=before, after=after,
                               thing=thing, between=[a[:5], b[:5]], evidence=evidence)
        for r in rows:
            r["learned"] = change["id"]
        self.data["adapted"].append({"at": round(time.time()), "routine": routine, "name": st.name, "thing": thing,
                                     "between": [a[:5], b[:5]], "change_id": change["id"], "evidence": evidence})
        self.data["adapted"] = self.data["adapted"][-100:]
        await self.hass.async_add_executor_job(self._log_md, f"{st.name}: {evidence} (change {change['id']}; `undo` puts it back).")
        await self._logbook(f"changed {st.name}: {evidence}", routine)
        await self.hass.async_add_executor_job(self.save)
        return change

    def _log_md(self, line: str) -> None:
        old = self.store.memory_read("log.md") or "# Log\n"
        text = old.rstrip("\n") + f"\n- {dt_util.now().date().isoformat()} Adapted a routine: {line}\n"
        try:
            self.store.memory_write("log.md", text, author="agent", reason="Sunrise adapted a routine to how it's used")
        except MemoryError_:
            pass  # log.md is full: the change log and the routine's own description still say it

    def report(self) -> dict[str, Any]:
        """For `usage`: the recent times a person's hand won, and the routines changed because of it."""
        rows = self.data["overruled"][-20:]
        return {"overruled": [{**{k: r[k] for k in ("thing", "kept", "routine", "name", "after_min")},
                               "when": dt_util.as_local(dt_util.utc_from_timestamp(r["at"])).isoformat(timespec="minutes"),
                               **({"learned": r["learned"]} if r.get("learned") else {})} for r in rows][::-1],
                "adapted": self.data["adapted"][-10:][::-1]}


def _name(hass: HomeAssistant, entity_id: str) -> str:
    st = hass.states.get(entity_id)
    return st.name if st else entity_id


def _targets(step: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    """Where a step names its entities: its target, or (the old way) its data."""
    for key in ("target", "data"):
        if isinstance(step.get(key), dict) and "entity_id" in step[key]:
            return step[key], key
    return None


def _leave_alone(steps: Any, thing: str, a: str, b: str, alias: str) -> tuple[Any, bool]:
    """Every step that switches `thing` by its entity id: the thing comes out of it into its own copy of that
    step, which runs only outside a-b. Walks choose, if, sequence, parallel and repeat."""
    changed = False
    if isinstance(steps, dict):
        steps = [steps]
    if not isinstance(steps, list):
        return steps, False
    out: list[Any] = []
    for step in steps:
        if not isinstance(step, dict):
            out.append(step)
            continue
        if step.get("action") and (found := _targets(step)):
            holder, key = found
            ids = holder["entity_id"]
            ids = [x.strip() for x in ids.split(",")] if isinstance(ids, str) else list(ids or [])
            if thing in ids:
                rest = [x for x in ids if x != thing]
                if rest:
                    out.append({**step, key: {**holder, "entity_id": rest}})
                only = {**step, key: {**holder, "entity_id": thing}}
                out.append({"alias": alias, "if": [{"condition": "not", "conditions": [{"condition": "time", "after": a, "before": b}]}],
                            "then": [only]})
                changed = True
                continue
        step = dict(step)
        for key in ("sequence", "then", "else", "default", "parallel"):
            if key in step:
                step[key], did = _leave_alone(step[key], thing, a, b, alias)
                changed |= did
        if isinstance(step.get("choose"), list):
            options = []
            for opt in step["choose"]:
                if isinstance(opt, dict) and "sequence" in opt:
                    seq, did = _leave_alone(opt["sequence"], thing, a, b, alias)
                    opt, changed = {**opt, "sequence": seq}, changed or did
                options.append(opt)
            step["choose"] = options
        if isinstance(step.get("repeat"), dict) and "sequence" in step["repeat"]:
            seq, did = _leave_alone(step["repeat"]["sequence"], thing, a, b, alias)
            step["repeat"], changed = {**step["repeat"], "sequence": seq}, changed or did
        out.append(step)
    return out, changed
