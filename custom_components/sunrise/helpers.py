"""Device helpers: what Sunrise can do for one kind of device beyond the general checks.

The general checks (diagnose.py) work for every integration: Home Assistant's own record of the
device, its integration's state, the address it uses, whether anything answers there, the log.
A helper adds what only that kind of device allows: asking the device itself (its signal, its
MAC), searching the network for it, and moving Home Assistant to its new address.

`HELPERS` maps an integration domain to its helper. Today there is one, for WiZ. Another (Shelly,
ESPHome, ...) is a `Helper` subclass here plus one line in `HELPERS`; diagnose.py needs no change.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant

from . import net as N

if TYPE_CHECKING:
    from .diagnose import Dev


def label(row: dict[str, Any]) -> str:
    return f"{row['device']}" + (f" ({row['room']})" if row.get("room") else "")


class Helper:
    """One kind of device. Every hook is optional; the defaults leave the device to the general checks."""

    domain = ""
    can_move = False  # fix_device op=update_host works for this kind

    def mac(self, device: Any, entry: Any) -> str | None:
        """The device's MAC when Home Assistant's device record doesn't list one."""
        return None

    async def look(self, hass: HomeAssistant, net: N.Net, devs: list[Dev], subnets: list[str], power_cycled: bool) -> Any:
        """Ask the devices (and the network) once, for all of `devs`; what `classify` reads."""
        return None

    def classify(self, d: Dev, seen: Any, cycled: bool, loaded: bool) -> dict[str, Any]:
        """{cause, why, ...} for one device, from what `look` saw."""
        raise NotImplementedError

    def fix(self, cause: str) -> dict[str, str] | None:
        """This kind's own fix for a cause, when it differs from the general one."""
        return None

    def person(self, rows: list[dict[str, Any]]) -> list[str]:
        """Lines for the person that only this kind needs."""
        return []

    def summary(self, seen: Any) -> dict[str, Any]:
        return {}

    async def signal(self, hass: HomeAssistant, net: N.Net, devs: list[Dev]) -> list[dict[str, Any]]:
        """Live Wi-Fi signal of working devices: [{device_id, rssi}]."""
        return []

    async def find(self, hass: HomeAssistant, net: N.Net, d: Dev, subnets: list[str]) -> str | None:
        """The device's new address, by searching the network."""
        return None

    async def move(self, hass: HomeAssistant, net: N.Net, d: Dev, entry: Any, new: str) -> str | None:
        """Point Home Assistant at `new` through the integration's own setup; an error, or None when it took."""
        return "Sunrise can't change this kind of device's address."


class Wiz(Helper):
    """WiZ bulbs and plugs: their local UDP protocol (net.py) and WiZ's own config flow."""

    domain = "wiz"
    can_move = True

    def mac(self, device: Any, entry: Any) -> str | None:
        return next((N.norm_mac(v) for _k, v in device.identifiers if len(N.norm_mac(v)) == 12), None) or N.norm_mac(entry.unique_id)

    async def look(self, hass, net, devs, subnets, power_cycled):
        tasks = {d.id: hass.async_add_executor_job(N.wiz_probe, d.host, net) for d in devs if d.host and N.is_lan(d.host)}
        disc = hass.async_add_executor_job(N.wiz_discover, net, subnets) if any(d.down for d in devs) or power_cycled else None
        results = await asyncio.gather(*tasks.values())
        probes = dict(zip(tasks, results, strict=True))
        found = await disc if disc else {}
        return {"probes": probes, "found": found}

    def classify(self, d, seen, cycled, loaded):
        out = N.classify_wiz(down=d.down, ha_mac=d.mac, host=d.host, probe=seen["probes"].get(d.id), found=seen["found"],
                             power_cycled=cycled, entry_loaded=loaded)
        if out["cause"] == "forgot_wifi":
            out["why"] = ("It still doesn't answer after its power was turned off and on, so it has most likely forgotten the "
                          "Wi-Fi. Only this kind needs re-pairing, in the WiZ phone app over Bluetooth.")
        return out

    def fix(self, cause):
        if cause == "forgot_wifi":
            return {"person": "re-pair it in the WiZ phone app (add a light, follow the app; it uses Bluetooth)"}
        return None

    def person(self, rows):
        names = [label(r) for r in rows if r["cause"] == "forgot_wifi"]
        return ["Re-pair in the WiZ phone app (add a light; it uses Bluetooth): " + ", ".join(names)] if names else []

    def summary(self, seen):
        return {"answered_search": len(seen["found"])}

    async def signal(self, hass, net, devs):
        probes = await asyncio.gather(*(hass.async_add_executor_job(N.wiz_probe, d.host, net) for d in devs))
        return [{"device_id": d.id, "rssi": p["rssi"]} for d, p in zip(devs, probes, strict=True)
                if p.get("answers") and p.get("rssi") is not None]

    async def find(self, hass, net, d, subnets):
        return (await hass.async_add_executor_job(N.wiz_discover, net, subnets)).get(d.mac or "")

    async def move(self, hass, net, d, entry, new):
        """WiZ's own config flow reads the bulb's MAC, finds the entry with that MAC, updates its host and reloads it."""
        probe = await hass.async_add_executor_job(N.wiz_probe, new, net)
        if not probe.get("answers"):
            return f"Nothing answers like a WiZ bulb at {new}; nothing changed."
        if d.mac and probe.get("mac") and probe["mac"] != d.mac:
            return f"The bulb at {new} is a different one; nothing changed."
        flow = await hass.config_entries.flow.async_init("wiz", context={"source": SOURCE_USER})
        res = await hass.config_entries.flow.async_configure(flow["flow_id"], {"host": new})
        if res.get("type") == "create_entry":
            return "Home Assistant added it as a new bulb instead of moving the old one; remove the duplicate in Devices."
        if res.get("type") != "abort" or res.get("reason") != "already_configured":
            if res.get("type") == "form":
                hass.config_entries.flow.async_abort(res["flow_id"])
            return f"WiZ didn't take the new address ({res.get('reason') or res.get('errors') or res.get('type')}); nothing changed."
        await hass.async_block_till_done()
        return None


HELPERS: dict[str, Helper] = {h.domain: h for h in (Wiz(),)}
