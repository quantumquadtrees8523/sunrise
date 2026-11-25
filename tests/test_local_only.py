"""Local by default: the integration makes no outbound internet calls. No HTTP
client in its code, every socket send goes through the LAN check, the cloud seam is off by default
and never connects, and a full tool run sends nothing off the home network (the autouse `lan_only`
guard in conftest fails any test whose code reaches a non-LAN address or makes an HTTP request)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from custom_components.sunrise import cloud
from custom_components.sunrise.const import CLOUD_MODE_DEFAULT

from .conftest import OUTBOUND, call, load_house, setup_integration

CODE = Path(__file__).resolve().parent.parent / "custom_components" / "sunrise"
NETWORK_CLIENTS = {"aiohttp", "requests", "httpx", "urllib", "urllib3", "http", "websockets", "ftplib", "smtplib",
                   "homeassistant.helpers.aiohttp_client", "homeassistant.helpers.httpx_client"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


@pytest.mark.parametrize("path", sorted(CODE.glob("*.py")), ids=lambda p: p.name)
def test_no_http_client_in_the_code(path: Path) -> None:
    bad = {m for m in _imports(path) if any(m == c or m.startswith(c + ".") for c in NETWORK_CLIENTS)}
    assert not bad, f"{path.name} imports a network client: {bad}"


def test_sockets_only_in_net_and_every_send_checked() -> None:
    for path in CODE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name != "net.py":
            assert "socket" not in _imports(path), path.name
            continue
        for fn in ("sendto(", "create_connection("):
            for line in [ln for ln in text.splitlines() if fn in ln and not ln.strip().startswith(("#", '"'))]:
                assert "_lan(" in line, f"unchecked send: {line.strip()}"


def test_cloud_mode_is_off_by_default_and_never_connects() -> None:
    assert CLOUD_MODE_DEFAULT is False
    assert cloud.enabled({}) is False and cloud.enabled({"cloud_mode": True}) is False  # no sign-in exists
    assert cloud.forward({}, "state_changed", {"entity_id": "light.x"}) is False
    assert cloud.forward({"cloud_mode": True}, "state_changed", {}) is False


async def test_a_full_tool_run_stays_on_the_home_network(hass, socket_enabled) -> None:
    await load_house(hass, loopback=False)  # the sample house's 10.0.0.x addresses
    entry = await setup_integration(hass)
    from custom_components.sunrise import net as N

    entry.runtime_data.net = N.Net(probe_timeout=0.05, discover_timeout=0.1, broadcast=True, sweep=[])
    for tool, args in [("house_map", {}), ("behavior_log", {}), ("audit", {}), ("list_skills", {}),
                       ("diagnose_device", {"target": "Kitchen Pendant 2"}), ("log_run", {"op": "export"})]:
        res = await call(hass, tool, args)
        assert not res.error, (tool, res.data)
    assert OUTBOUND == []
