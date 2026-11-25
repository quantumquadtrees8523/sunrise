"""The first real case: 8 of 11 WiZ bulbs unavailable. Fake bulbs answer WiZ's own UDP
protocol on 127.0.0.x (the sample house's 10.0.0.x), so the diagnosis sorts each dead bulb into:
(a) moved (on the Wi-Fi at a new address: fixed in software through WiZ's config flow),
(b) off_network (power-cycle at the switch), (c) forgot_wifi (only these need the WiZ app)."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import mock_config_flow, mock_platform

from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant

from custom_components.sunrise import net as N

from .conftest import Bulbs, call, load_house, setup_integration

import sample_house  # noqa: E402  (tests/, put on the path by conftest)

MAC = {o: sample_house.wiz_mac(o) for _n, _r, o, _d in sample_house.WIZ}
SWEEP = [f"127.0.0.{i}" for i in range(210, 240)]


def ip(octet: int) -> str:
    return f"127.0.0.{octet}"


@pytest.fixture
def bulbs(socket_enabled, monkeypatch):
    # TCP checks (ESPHome's port, the router's web page) answer "closed" here: the test HA may only
    # connect to 127.0.0.1. The LAN-only guard still sees every UDP packet.
    tcp = []
    monkeypatch.setattr(N, "tcp_open", lambda host, port, timeout=1.0: tcp.append((N._lan(host), port)) and False)
    b = Bulbs({ip(215): (MAC[215], -60), ip(216): (MAC[216], -70), ip(217): (MAC[217], -79),   # working; .217 weak
               ip(230): (MAC[220], -66), ip(231): (MAC[221], -66), ip(232): (MAC[222], -66)})  # three moved
    yield b
    b.close()


def net(b: Bulbs) -> N.Net:
    return N.Net(wiz_port=b.port, probe_timeout=0.3, discover_timeout=0.8, broadcast=False, sweep=SWEEP)


async def _house(hass, b):
    await load_house(hass)
    return await setup_integration(hass, net=net(b))


class FakeWizFlow(ConfigFlow, domain="wiz"):
    """WiZ's own user step, as HA core has it: ask the bulb at the host for its MAC, and if an entry
    has that MAC, update its host and abort with already_configured."""

    VERSION = 1
    NET: N.Net | None = None

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user")
        host = user_input["host"]
        probe = await self.hass.async_add_executor_job(N.wiz_probe, host, self.NET)
        if not probe["answers"]:
            return self.async_show_form(step_id="user", errors={"base": "cannot_connect"})
        await self.async_set_unique_id(probe["mac"], raise_on_progress=False)
        self._abort_if_unique_id_configured(updates={"host": host})
        return self.async_create_entry(title=host, data={"host": host})


def by_name(rows):
    return {r["device"]: r for r in rows}


async def test_net_probe_discover_and_classify(bulbs) -> None:
    n = net(bulbs)
    p = N.wiz_probe(ip(215), n)
    assert p["answers"] and p["mac"] == MAC[215] and p["rssi"] == -60
    assert N.wiz_probe(ip(220), n) == {"answers": False}
    found = N.wiz_discover(n, [])
    assert found[MAC[220]] == ip(230) and found[MAC[215]] == ip(215)
    assert N.classify_wiz(down=True, ha_mac=MAC[220], host=ip(220), probe={"answers": False}, found=found, power_cycled=False)["cause"] == "moved"
    assert N.classify_wiz(down=True, ha_mac=MAC[223], host=ip(223), probe={"answers": False}, found=found, power_cycled=False)["cause"] == "off_network"
    assert N.classify_wiz(down=True, ha_mac=MAC[223], host=ip(223), probe={"answers": False}, found=found, power_cycled=True)["cause"] == "forgot_wifi"
    assert N.classify_wiz(down=False, ha_mac=MAC[217], host=ip(217), probe=N.wiz_probe(ip(217), n), found=found, power_cycled=False)["cause"] == "weak_signal"


def test_lan_only_addresses() -> None:
    assert N.is_lan("10.0.0.220") and N.is_lan("10.0.0.5") and N.is_lan("127.0.0.215") and N.is_lan("255.255.255.255")
    assert not N.is_lan("8.8.8.8") and not N.is_lan("203.0.113.7") and not N.is_lan("example.com")
    with pytest.raises(N.NotLocal):
        N.wiz_ask("8.8.8.8", "getPilot", N.Net())
    assert N.sweep_targets(["8.8.8.0/24"], N.Net()) == []


async def test_get_my_lights_back_up(hass: HomeAssistant, bulbs) -> None:
    await _house(hass, bulbs)
    first = await call(hass, "diagnose_device", {"target": "all my lights"})
    rows = by_name(first.data["devices"])
    assert {n for n, r in rows.items() if r["cause"] == "moved"} == {"Kitchen Pendant 2", "Kitchen Pendant 3", "Living Room Ceiling 2"}
    assert rows["Kitchen Pendant 2"]["found_at"] == ip(230)
    off = {n for n, r in rows.items() if r["cause"] == "off_network"}
    assert off == {"Bedroom Lamp", "Bedroom Ceiling", "Office Lamp", "Office Ceiling", "Hallway Light"}
    assert rows["Kitchen Pendant 1"]["cause"] == "weak_signal" and rows["Living Room Lamp"]["cause"] == "ok"
    assert first.data["wiz_errors_since_start"] == 956
    assert "Bedroom Lamp (Bedroom)" in first.data["for_the_person"][0]
    assert rows["Bedroom Lamp"]["fix"]["person"].startswith("turn its switch off")

    # (a) fix the moved ones in software, through WiZ's own config flow, with undo.
    FakeWizFlow.NET = net(bulbs)
    mock_platform(hass, "wiz.config_flow", None)
    with mock_config_flow("wiz", FakeWizFlow):
        fixed = []
        for name in ("Kitchen Pendant 2", "Kitchen Pendant 3", "Living Room Ceiling 2"):
            res = await call(hass, "fix_device", {"op": "update_host", "target": rows[name]["device_id"]})
            assert res.data["ok"], res.data
            fixed.append(res.data)
    assert fixed[0]["read_back"]["host_now"] == ip(230)
    entry = next(e for e in hass.config_entries.async_entries("wiz") if e.unique_id == MAC[220])
    assert entry.data["host"] == ip(230)

    # (b) the person flips five switches: two come back (one at its old address, one at a new one).
    bulbs.add(ip(223), MAC[223])
    bulbs.add(ip(234), MAC[224])
    again = await call(hass, "diagnose_device", {"target": "all my lights", "power_cycled": True})
    rows = by_name(again.data["devices"])
    assert rows["Bedroom Lamp"]["cause"] == "answering" and rows["Bedroom Lamp"]["fix"]["op"] == "reload_entry"
    assert rows["Bedroom Ceiling"]["cause"] == "moved"
    # (c) the three still silent after a power cycle forgot the Wi-Fi: only these get re-paired.
    assert {n for n, r in rows.items() if r["cause"] == "forgot_wifi"} == {"Office Lamp", "Office Ceiling", "Hallway Light"}
    assert any("WiZ phone app" in s and "Hallway Light" in s for s in again.data["for_the_person"])
    # Remembered next time without the flag.
    third = await call(hass, "diagnose_device", {"target": "Hallway Light"})
    assert third.data["devices"][0]["cause"] == "forgot_wifi"

    # Undo puts the old address back.
    await call(hass, "undo", {"change_id": fixed[0]["change_id"]})
    assert entry.data["host"] == "127.0.0.220"


async def test_update_host_refuses_wrong_bulb_and_non_lan(hass: HomeAssistant, bulbs) -> None:
    await _house(hass, bulbs)
    dev = next(r for r in (await call(hass, "diagnose_device", {"target": "Kitchen Pendant 2"})).data["devices"])
    wrong = await call(hass, "fix_device", {"op": "update_host", "target": dev["device_id"], "host": ip(215)})
    assert wrong.data["ok"] is False and "different one" in wrong.data["error"]
    outside = await call(hass, "fix_device", {"op": "update_host", "target": dev["device_id"], "host": "8.8.8.8"})
    assert outside.error and "home network" in outside.data["error"]
    router = await call(hass, "fix_device", {"op": "reload_entry", "target": "router password"})
    assert "never change the router" in router.data["refused"]


async def test_reload_entry_reads_back(hass: HomeAssistant, bulbs) -> None:
    await _house(hass, bulbs)
    dev = next(r for r in (await call(hass, "diagnose_device", {"target": "Living Room Lamp"})).data["devices"])
    res = await call(hass, "fix_device", {"op": "reload_entry", "target": dev["device_id"]})
    assert res.data["read_back"]["connection"] == "loaded" and res.data["ok"]


async def test_network_check_fios(hass: HomeAssistant, bulbs) -> None:
    await _house(hass, bulbs)
    res = await call(hass, "network_check")
    d = res.data
    assert d["isp_guess"] == "fios" and d["internet"] == "on"
    assert "The internet connection is up." in d["findings"]
    assert d["wifi_devices"]["unreachable"] >= 8
    assert d["wiz_signal"][0]["device"] == "Kitchen Pendant 1"  # weakest first
    assert not any("External IP" in k for k in d["router"])  # the house's public address is never needed
