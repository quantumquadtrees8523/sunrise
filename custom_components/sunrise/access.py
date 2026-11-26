"""What an agent may touch through Sunrise: never more than Home Assistant's own Assist would let it.

- Switching things (`act`) needs the thing exposed to the assistant that's asking (Settings -> Voice
  assistants -> Expose), the same list Assist's own tools follow, whoever is asking.
- Changing the house's setup (routines, names, rooms, device fixes, adding devices, undo, checkpoints)
  needs a signed-in administrator. A voice speaker, where nobody is signed in, can't: Assist can't either.
- Reading: by default the read tools also see things that aren't exposed, so diagnosis can say why
  something dropped off. The owner can turn that off in Sunrise's options (CONF_READ_UNEXPOSED); then
  every tool sees only what's exposed.

Sunrise's own checks (a yes for locks, alarms and garage doors; admin-only for the setup) only ever add
to these. Nothing here changes what is exposed or who may do what: that stays the owner's, in Home
Assistant's own settings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm

DEFAULT_ASSISTANT = "conversation"  # what the MCP Server and Assist itself pass

# Set for the length of one tool call when the owner keeps unexposed things private; None means "see everything".
_view: ContextVar[Callable[[str], bool] | None] = ContextVar("sunrise_view", default=None)


def exposed(hass: HomeAssistant, assistant: str | None, entity_id: str) -> bool:
    """Home Assistant's own answer to "may this assistant use this thing?". Unreadable settings mean no."""
    from homeassistant.components.homeassistant.exposed_entities import async_should_expose  # noqa: PLC0415

    try:
        return async_should_expose(hass, assistant or DEFAULT_ASSISTANT, entity_id)
    except KeyError:  # the exposure settings aren't loaded: fail closed
        return False


def seen(entity_id: str) -> bool:
    """Whether the read tools may show this thing in the current call."""
    only = _view.get()
    return only is None or only(entity_id)


def device_seen(hass: HomeAssistant, device_id: str) -> bool:
    """A device shows when any of its things may be shown (always, when nothing is kept private)."""
    if _view.get() is None:
        return True
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    return any(seen(e.entity_id) for e in er.async_entries_for_device(er.async_get(hass), device_id))


@contextmanager
def view(only: Callable[[str], bool] | None) -> Iterator[None]:
    token = _view.set(only)
    try:
        yield
    finally:
        _view.reset(token)


def speaker(ctx: llm.LLMContext) -> bool:
    """Nobody is signed in: a voice speaker or another of Home Assistant's own pipelines."""
    return not (ctx.context and ctx.context.user_id)


def asking_from(hass: HomeAssistant, ctx: llm.LLMContext) -> str | None:
    """The room of the device the request came from (a voice speaker says which it is), if it has one."""
    if not ctx.device_id or not (device := dr.async_get(hass).async_get(ctx.device_id)):
        return None
    area_id = dr.async_get_effective_area_id(hass, device) if hasattr(dr, "async_get_effective_area_id") else device.area_id
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    return area.name if area else None
