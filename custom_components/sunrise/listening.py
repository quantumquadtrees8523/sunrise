"""Listening: what follows what in the house. Home Assistant's history keeps states, but not that the
hall light went on forty seconds after the front door opened, by hand, most evenings. So the
integration hears each door, window, motion and presence sensor and each person coming or going as
it happens, and when someone switches a light, switch, fan or cover by hand within FOLLOW_S of one,
that is a pair. Saved with the usage tally (heard.json), 30 days at most. Nothing leaves the machine.

`patterns` is the evidence the `routines` skill suggests from: a pair that held on at least MIN_DAYS
days and after at least MIN_SHARE of the times the sensor changed in that stretch of the day, with
the routine that would do it written out. Checked here, in code; no model reads raw events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.core import Context, HomeAssistant, State
from homeassistant.util import dt as dt_util

from .store import Store

HEARD_CLASSES = ("motion", "occupancy", "presence", "door", "window", "opening", "garage_door")
HEARD_STATES = {"binary_sensor": ("on", "off"), "person": ("home", "not_home")}
FOLLOWED = {"light": ("on", "off"), "switch": ("on", "off"), "fan": ("on", "off"), "cover": ("open", "closed")}
FOLLOW_S = 120
KEEP_DAYS = 30
MIN_DAYS = 4
MIN_SHARE = 0.6
MARGIN_MIN = 30  # a routine's hours are the occasions' own, this much wider each side
MAX_SPAN_MIN = 12 * 60  # occasions spread wider than this run all day, with no hours
OPENS = ("door", "window", "opening", "garage_door")


def hears(state: State) -> bool:
    """A change worth hearing: a person, or a sensor of a kind a routine could start from."""
    if state.state not in HEARD_STATES.get(state.domain, ()):
        return False
    return state.domain == "person" or state.attributes.get("device_class") in HEARD_CLASSES


class Heard:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.data: dict[str, dict[str, list]] = {"heard": {}, "pairs": {}, "kinds": {}}
        self._last: dict[str, float] = {}  # sensor key → when it last changed (an episode goes on while it keeps firing)
        self._paired: set[tuple[str, float, str]] = set()

    def load(self) -> None:
        got = self.store.get("heard", {}) or {}
        self.data = {k: got.get(k) or {} for k in ("heard", "pairs", "kinds")}

    def save(self) -> None:
        cutoff = dt_util.utcnow().timestamp() - KEEP_DAYS * 86400
        for kind in ("heard", "pairs"):
            self.data[kind] = {k: kept for k, v in self.data[kind].items() if (kept := [r for r in v if _ts(r) >= cutoff])}
        self.store.put("heard", self.data)

    def sensor(self, state: State) -> None:
        """A sensor or a person changed. One that fires again within FOLLOW_S is the same episode."""
        key, when = f"{state.entity_id}|{state.state}", state.last_changed.timestamp()
        if when - self._last.get(key, -1e18) >= FOLLOW_S:
            self.data["heard"].setdefault(key, []).append(round(when))
        self._last[key] = when
        self.data["kinds"][state.entity_id] = state.attributes.get("device_class") or state.domain

    def change(self, entity_id: str, new_state: str, context: Context, when: datetime) -> None:
        """Someone switched a thing (an automation's own change has a parent and doesn't count): pair it
        with every sensor that changed in the FOLLOW_S before, once per episode."""
        domain = entity_id.split(".", 1)[0]
        if context.parent_id or new_state not in FOLLOWED.get(domain, ()):
            return
        at = when.timestamp()
        for key, last in self._last.items():
            if not 0 <= at - last <= FOLLOW_S or key.split("|", 1)[0] == entity_id:
                continue
            episode = self.data["heard"].get(key) or [round(last)]
            mark = (key, episode[-1], f"{entity_id}|{new_state}")
            if mark in self._paired:
                continue
            if len(self._paired) > 5000:
                self._paired.clear()
            self._paired.add(mark)
            self.data["pairs"].setdefault(f"{key}>{entity_id}|{new_state}", []).append([episode[-1], round(at - last)])


def _ts(row: Any) -> float:
    return float(row[0] if isinstance(row, list) else row)


def _minute(ts: float) -> int:
    local = dt_util.as_local(datetime.fromtimestamp(ts, UTC))
    return local.hour * 60 + local.minute


def _day(ts: float) -> str:
    return dt_util.as_local(datetime.fromtimestamp(ts, UTC)).date().isoformat()


def _span(minutes: list[int]) -> tuple[int, int] | None:
    """The shortest stretch of the day (it may cross midnight) that holds every minute, widened by
    MARGIN_MIN; None when the occasions are spread over more than MAX_SPAN_MIN."""
    m = sorted(set(minutes))
    gap, i = max(((m[(k + 1) % len(m)] - m[k]) % 1440 or 1440, k) for k in range(len(m)))
    if 1440 - gap > MAX_SPAN_MIN:
        return None
    return (m[(i + 1) % len(m)] - MARGIN_MIN) % 1440, (m[i] + MARGIN_MIN) % 1440


def _inside(minute: int, span: tuple[int, int] | None) -> bool:
    if span is None:
        return True
    a, b = span
    return a <= minute <= b if a <= b else minute >= a or minute <= b


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _name(hass: HomeAssistant, entity_id: str) -> str:
    st = hass.states.get(entity_id)
    return st.name if st else entity_id.split(".", 1)[1].replace("_", " ")


def _when_words(name: str, entity_id: str, to: str, kind: str) -> str:
    if entity_id.startswith("person."):
        return f"{name} {'comes home' if to == 'home' else 'leaves'}"
    if kind in OPENS:
        return f"the {name} {'opens' if to == 'on' else 'closes'}"
    return f"the {name} {'notices someone' if to == 'on' else 'goes quiet'}"


def _then_words(name: str, entity_id: str, to: str) -> str:
    if entity_id.startswith("cover."):
        return f"{'open' if to == 'open' else 'close'} the {name}"
    return f"turn the {name} {to}"


def _action(entity_id: str, to: str) -> dict[str, Any]:
    domain = entity_id.split(".", 1)[0]
    service = {"open": "open_cover", "closed": "close_cover"}.get(to, f"turn_{to}")
    return {"action": f"{domain}.{service}", "target": {"entity_id": entity_id}}


def patterns(hass: HomeAssistant, heard: Heard, existing: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every "when this changes, someone does that" that cleared the bar, strongest first. `existing` is
    the house's automations and the suggestions it turned down: a pair one of them names (the sensor and
    the thing) is left out."""
    done = [str(row) for row in existing or []]
    out = []
    for key, hits in heard.data["pairs"].items():
        trigger, effect = key.split(">", 1)
        (t_id, t_to), (e_id, e_to) = trigger.split("|", 1), effect.split("|", 1)
        if hass.states.get(t_id) is None or hass.states.get(e_id) is None:
            continue
        days = {_day(h[0]) for h in hits}
        if len(days) < MIN_DAYS or any(t_id in row and e_id in row for row in done):
            continue
        span = _span([_minute(h[0]) for h in hits])
        fired = [ts for ts in heard.data["heard"].get(trigger, []) if _inside(_minute(ts), span)]
        share = len(hits) / max(len(fired), len(hits))
        if share < MIN_SHARE:
            continue
        when = _when_words(_name(hass, t_id), t_id, t_to, heard.data["kinds"].get(t_id, ""))
        then = _then_words(_name(hass, e_id), e_id, e_to)
        hours = f" between {_clock(span[0])} and {_clock(span[1])}" if span else ""
        evidence = (f"{len(hits)} of the {max(len(fired), len(hits))} times {when}{hours} in the last {KEEP_DAYS} days, someone "
                    f"went and did this by hand within {max(h[1] for h in hits)} seconds, on {len(days)} different days.")
        out.append({
            "when": {"id": t_id, "to": t_to}, "then": {"id": e_id, "to": e_to}, "days": len(days), "times": len(hits),
            "of": max(len(fired), len(hits)), "between": [_clock(span[0]), _clock(span[1])] if span else None, "evidence": evidence,
            "routine": {
                "alias": f"{then[0].upper()}{then[1:]} when {when}"[:80],
                "description": evidence,
                "triggers": [{"trigger": "state", "entity_id": t_id, "to": t_to}],
                "conditions": [{"condition": "time", "after": f"{_clock(span[0])}:00", "before": f"{_clock(span[1])}:00"}] if span else [],
                "actions": [_action(e_id, e_to)],
                "mode": "single",
            },
        })
    return sorted(out, key=lambda p: (-p["days"], -p["times"] / p["of"], p["then"]["id"]))
