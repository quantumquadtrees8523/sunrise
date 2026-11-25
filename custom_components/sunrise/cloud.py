"""The one seam for a later, opt-in cloud mode. Off by default; nothing here talks to the internet.

What it is for (not built): when a person signs in to a paid cloud tier, selected Home Assistant
signals (an event a skill asked to watch) would be forwarded to a cloud queue for background or
proactive work, and a relay would let a remote agent reach this integration's tools.

Until then:
- `enabled()` is False unless the config entry's options say `cloud_mode: true` AND a sign-in
  exists, and there is no sign-in flow, so it is always False.
- `forward()` is the hook every place that would send a signal calls. With cloud mode off it does
  nothing and returns False. It never opens a connection in this version, on or off.

The no-outbound test (tests/test_local_only.py) asserts this default.
"""

from __future__ import annotations

from typing import Any

from .const import CLOUD_MODE_DEFAULT, CONF_CLOUD_MODE


def enabled(options: dict[str, Any] | None, signed_in: bool = False) -> bool:
    return bool((options or {}).get(CONF_CLOUD_MODE, CLOUD_MODE_DEFAULT)) and signed_in


def forward(options: dict[str, Any] | None, kind: str, payload: dict[str, Any]) -> bool:
    """Hand one signal to the cloud queue when cloud mode is on. Not built: always local."""
    if not enabled(options):
        return False
    raise NotImplementedError("cloud mode isn't part of this version")
