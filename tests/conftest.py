"""Shared test setup: a sample house loaded into a test Home Assistant, fake WiZ bulbs that
answer their real UDP protocol on 127.0.0.x, a LAN-only guard on every socket, and a helper that
calls this integration's tools exactly as the MCP Server does (through the registered LLM API)."""

from __future__ import annotations

import json
import socket
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry, MockModule, mock_integration

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import llm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import sample_house  # noqa: E402

from custom_components.sunrise import net as N  # noqa: E402
from custom_components.sunrise.const import DOMAIN, LLM_API_ID  # noqa: E402


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# --- local only ----------------------------------------------------------------------------------

OUTBOUND: list[tuple[str, Any]] = []


@pytest.fixture(autouse=True)
def lan_only(monkeypatch):
    """Every packet, connection and HTTP request a test causes must go to a LAN address (rule S7)."""
    OUTBOUND.clear()
    real_sendto, real_connect = socket.socket.sendto, socket.socket.connect

    def check(addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, str) and host and not host.startswith("/") and not N.is_lan(host):
            OUTBOUND.append(("socket", host))
            raise AssertionError(f"non-LAN connection to {host}")

    def sendto(self, data, *args):
        check(args[-1])
        return real_sendto(self, data, *args)

    def connect(self, addr):
        check(addr)
        return real_connect(self, addr)

    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket.socket, "connect", connect)

    import aiohttp

    from yarl import URL

    real_request = aiohttp.ClientSession._request

    async def lan_http(self, method, url, *a, **kw):
        if not N.is_lan(URL(str(url)).host or ""):
            OUTBOUND.append(("http", str(url)))
            raise AssertionError(f"HTTP request to {url}")
        return await real_request(self, method, url, *a, **kw)

    monkeypatch.setattr(aiohttp.ClientSession, "_request", lan_http)
    yield OUTBOUND


# --- fake WiZ bulbs ------------------------------------------------------------------------------

class Bulbs:
    """WiZ bulbs on loopback, all on one port: each answers getPilot, getSystemConfig and
    registration with its MAC and signal. `move` and `kill` change the network under the test."""

    def __init__(self, bulbs: dict[str, tuple[str, int]]):
        self.socks: dict[str, tuple[socket.socket, str, int]] = {}
        self.threads: dict[str, threading.Thread] = {}
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.250", 0))
        self.port = probe.getsockname()[1]
        probe.close()
        for ip, (mac, rssi) in bulbs.items():
            self.add(ip, mac, rssi)

    def add(self, ip: str, mac: str, rssi: int = -60) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((ip, self.port))
        s.settimeout(0.05)
        self.socks[ip] = (s, mac, rssi)
        t = threading.Thread(target=self._serve, args=(s, mac, rssi), daemon=True)
        self.threads[ip] = t
        t.start()

    def kill(self, ip: str) -> None:
        s, *_ = self.socks.pop(ip)
        s.close()
        self.threads.pop(ip).join(1)

    @staticmethod
    def _serve(s, mac, rssi):
        while True:
            try:
                data, addr = s.recvfrom(4096)
            except TimeoutError:
                if s.fileno() == -1:
                    return
                continue
            except OSError:
                return
            method = json.loads(data).get("method")
            result = {"getPilot": {"mac": mac, "rssi": rssi, "state": True},
                      "getSystemConfig": {"mac": mac, "fwVersion": "1.26.0", "moduleName": "ESP25_SHRGB_01"},
                      "registration": {"mac": mac, "success": True}}.get(method)
            if result:
                with __import__("contextlib").suppress(OSError):
                    s.sendto(json.dumps({"method": method, "result": result}).encode(), addr)

    def close(self) -> None:
        for ip in list(self.socks):
            self.kill(ip)


def loop(host: str) -> str:
    """The sample house's 10.0.0.x as 127.0.0.x, so fake bulbs can answer."""
    return host.replace("10.0.0.", "127.0.0.")


# --- the sample house in a test Home Assistant --------------------------------------------------

class SystemLog:
    def __init__(self, rows):
        self.records = type("R", (), {"to_list": staticmethod(lambda: rows)})()


async def load_house(hass: HomeAssistant, *, loopback: bool = True) -> dict[str, Any]:
    h = sample_house.house()
    areas = ar.async_get(hass)
    area_ids = {name: areas.async_create(name).id for name in h["areas"]}
    entries = {}
    for domain in sorted({e["domain"] for e in h["entries"]}):  # stand-ins: no real integration code runs
        mock_integration(hass, MockModule(domain, async_setup_entry=AsyncMock(return_value=True),
                                          async_unload_entry=AsyncMock(return_value=True), partial_manifest={"config_flow": True}))
    for e in h["entries"]:
        data = {k: (loop(v) if loopback and k == "host" else v) for k, v in e["data"].items()}
        entry = MockConfigEntry(domain=e["domain"], title=e["title"], data=data, unique_id=e["unique_id"],
                                state=ConfigEntryState(e["state"]))
        entry.add_to_hass(hass)
        entries[e["entry_id"]] = entry
    devs = dr.async_get(hass)
    dev_ids = {}
    for d in h["devices"]:
        entry = entries[d["entry"]]
        kw = {"connections": {(dr.CONNECTION_NETWORK_MAC, N.norm_mac(d["mac"]))}} if d["mac"] else {}
        dev = devs.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(entry.domain, d["id"])}, name=d["name"],
                                       manufacturer=d["manufacturer"], model=d["model"],
                                       entry_type=dr.DeviceEntryType.SERVICE if d["service"] else None, **kw)
        if d["area"]:
            devs.async_update_device(dev.id, area_id=area_ids[d["area"]])
        dev_ids[d["id"]] = dev.id
    ents = er.async_get(hass)
    for e in h["entities"]:
        domain, object_id = e["entity_id"].split(".", 1)
        if e["platform"] in ("sun", "zone", "person"):
            hass.states.async_set(e["entity_id"], e["state"], e["attributes"])
            continue
        reg = ents.async_get_or_create(domain, e["platform"], e["unique_id"], suggested_object_id=object_id,
                                       config_entry=entries[e["entry"]] if e["entry"] else None,
                                       device_id=dev_ids.get(e["device"]),
                                       entity_category=er.EntityCategory(e["category"]) if e["category"] else None)
        assert reg.entity_id == e["entity_id"], (reg.entity_id, e["entity_id"])
        if e["area"]:  # HA lets only an entity with its own name have its own room
            ents.async_update_entity(reg.entity_id, name=e["attributes"].get("friendly_name"), area_id=area_ids[e["area"]])
        hass.states.async_set(e["entity_id"], e["state"], e["attributes"])
    hass.data["system_log"] = SystemLog(h["system_log"])
    await hass.async_block_till_done()
    return h


async def setup_integration(hass: HomeAssistant, **runtime: Any) -> MockConfigEntry:
    import tempfile  # noqa: PLC0415

    hass.config.config_dir = runtime.get("config_dir") or tempfile.mkdtemp(prefix="sunrise-test-")  # a clean data folder
    entry = MockConfigEntry(domain=DOMAIN, title="Sunrise", unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rt = entry.runtime_data
    rt.act_cutoff = runtime.get("act_cutoff", 1.5)
    rt.reload_wait = runtime.get("reload_wait", 0.0)
    rt.net = runtime.get("net", N.Net(probe_timeout=0.3, discover_timeout=0.6, broadcast=False, sweep=[]))
    return entry


async def call(hass: HomeAssistant, tool: str, args: dict[str, Any] | None = None, user_id: str | None = None) -> llm.ToolResult:
    ctx = llm.LLMContext(platform="mcp_server", context=Context(user_id=user_id), language="en", assistant="conversation", device_id=None)
    api = await llm.async_get_api(hass, LLM_API_ID, ctx)
    return await api.async_call_tool(llm.ToolInput(tool_name=tool, tool_args=args or {}))
