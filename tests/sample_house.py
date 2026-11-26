"""A sample house as plain data (no Home Assistant imports), for tests: a messy but realistic setup.
Made up: no real person's house, names or devices.

166 entities, 80 unavailable or unknown, 68 with no room, 28 devices, 4 rooms, no floors or labels.
A mix of makers and ways to connect: 11 WiZ bulbs (8 unavailable, "Failed to update device" logged
~956 times), two Shelly plugs on the Wi-Fi (one unreachable, with a signal sensor), a Hue lamp,
a Zigbee door sensor gone quiet, speakers, TV, thermostat, printer, vacuum, two ESPHome voice
satellites mostly unavailable, and a router seen through UPnP under its own maker and model.
Two "Night mode" automations at 8 pm, two weather services, five leftover automations whose
configs were deleted. Home Assistant runs as a Container install at 10.0.0.213:8123.

`house()` returns {areas, entries, devices, entities, system_log}. Every entity has
{entity_id, platform, entry, device, area, state, attributes, category, unique_id}.
"""

from __future__ import annotations

from typing import Any

AREAS = ["Den", "Kitchen", "Loft", "Study"]
HA_HOST = "10.0.0.213"
WIZ = [  # name, room, last octet, unavailable
    ("Den Lamp", "Den", 215, False), ("Den Ceiling 1", "Den", 216, False),
    ("Kitchen Island 1", "Kitchen", 217, False), ("Kitchen Island 2", "Kitchen", 220, True),
    ("Kitchen Island 3", "Kitchen", 221, True), ("Den Ceiling 2", "Den", 222, True),
    ("Loft Lamp", "Loft", 223, True), ("Loft Ceiling", "Loft", 224, True),
    ("Study Lamp", "Study", 225, True), ("Study Ceiling", "Study", 226, True),
    ("Hallway Light", None, 228, True),
]
SHELLY = {"Study plug": 233, "Garage plug": 234}  # last octet of each plug's address
TOTAL, DOWN_OR_UNKNOWN, NO_AREA, DEVICES = 166, 80, 68, 28


def wiz_mac(octet: int) -> str:
    return f"a8bb50{octet:06x}"[-12:]


def house() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    devices: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []

    def entry(domain: str, title: str, data: dict | None = None, unique_id: str | None = None, state: str = "loaded") -> str:
        eid = f"e_{domain}_{len(entries)}"
        entries.append({"entry_id": eid, "domain": domain, "title": title, "data": data or {}, "unique_id": unique_id, "state": state})
        return eid

    def device(did: str, entry_id: str, name: str, area: str | None, maker: str, model: str, mac: str | None = None,
               service: bool = False, zigbee: str | None = None) -> str:
        devices.append({"id": did, "entry": entry_id, "name": name, "area": area, "manufacturer": maker, "model": model,
                        "mac": mac, "service": service, "zigbee": zigbee})
        return did

    def ent(entity_id: str, platform: str, entry_id: str | None, dev: str | None, state: str, attrs: dict | None = None,
            area: str | None = None, category: str | None = None) -> None:
        entities.append({"entity_id": entity_id, "platform": platform, "entry": entry_id, "device": dev, "area": area,
                         "state": state, "attributes": attrs or {}, "category": category, "unique_id": f"u_{entity_id}"})

    for name, room, octet, down in WIZ:
        mac = wiz_mac(octet)
        e = entry("wiz", name, {"host": f"10.0.0.{octet}"}, mac, "setup_retry" if down else "loaded")
        d = device(f"d_wiz_{octet}", e, name, room, "WiZ", "ESP25_SHRGB_01", mac)
        slug = name.lower().replace(" ", "_")
        state = "unavailable" if down else ("on" if octet == 215 else "off")
        ent(f"light.{slug}", "wiz", e, d, state, {"friendly_name": name, "supported_color_modes": ["rgb", "color_temp"],
                                                   **({"brightness": 128} if state == "on" else {})})
        ent(f"sensor.{slug}_signal_strength", "wiz", e, d, "unavailable" if down else "-71",
            {"friendly_name": f"{name} Signal strength", "unit_of_measurement": "dBm"}, category="diagnostic")

    # Two ESPHome voice satellites, mostly unavailable.
    for i, (room, up) in enumerate([(None, 1), (None, 2)], start=1):
        e = entry("esphome", f"voice-satellite-{i}", {"host": f"10.0.0.{240 + i}"}, f"voice{i}")
        d = device(f"d_voice_{i}", e, f"Voice Satellite {i}", room, "Espressif", "ESP32-S3 voice kit", f"c0ffee0000{i:02d}")
        for j, kind in enumerate(["assist_satellite", "media_player", "switch", "select", "select", "select", "button", "light",
                                  "sensor", "binary_sensor"]):
            eid = f"{kind}.voice_satellite_{i}_{j}"
            ent(eid, "esphome", e, d, "on" if j < up and kind in ("switch", "binary_sensor") else ("idle" if j < up else "unavailable"),
                {"friendly_name": f"Voice Satellite {i} {kind.replace('_', ' ')} {j}"},
                category="config" if kind in ("select", "button") else None)

    # The router, as Home Assistant sees it through UPnP: its name says nothing of being a router.
    e = entry("upnp", "Acme AX3000")
    d = device("d_router", e, "Acme AX3000", None, "Acme Networks", "AX3000")
    ent("sensor.acme_ax3000_download_speed", "upnp", e, d, "412.5", {"friendly_name": "Acme AX3000 Download speed", "unit_of_measurement": "Mbit/s"})
    ent("sensor.acme_ax3000_upload_speed", "upnp", e, d, "38.1", {"friendly_name": "Acme AX3000 Upload speed", "unit_of_measurement": "Mbit/s"})
    ent("sensor.acme_ax3000_external_ip", "upnp", e, d, "203.0.113.7", {"friendly_name": "Acme AX3000 External IP"})
    ent("binary_sensor.acme_ax3000_wan_status", "upnp", e, d, "on", {"friendly_name": "Acme AX3000 WAN status"})

    # Two weather services.
    e = entry("met", "Home")
    ent("weather.forecast_home", "met", e, device("d_met", e, "Forecast", None, "Met.no", "Forecast", service=True), "cloudy",
        {"friendly_name": "Forecast Home"})
    e = entry("openweathermap", "OpenWeatherMap")
    ent("weather.openweathermap", "openweathermap", e, device("d_owm", e, "OpenWeatherMap", None, "OpenWeather", "API", service=True),
        "unknown", {"friendly_name": "OpenWeatherMap"})

    # Other devices: 14 more, for 28 in all (the two weather services are services, not devices).
    others = [
        ("cast", "Den TV", "Den", "Google", "Chromecast", "media_player", "off"),
        ("cast", "Kitchen speaker", "Kitchen", "Google", "Nest Mini", "media_player", "unavailable"),
        ("sonos", "Loft speaker", "Loft", "Sonos", "One SL", "media_player", "paused"),
        ("dlna_dmr", "Study speaker", "Study", "Generic", "Media renderer", "media_player", "unavailable"),
        ("shelly", "Study plug", "Study", "Shelly", "Plus Plug S", "switch", "on"),
        ("shelly", "Garage plug", None, "Shelly", "Plug US", "switch", "unavailable"),
        ("tplink", "Porch plug", None, "TP-Link", "KP400", "switch", "off"),
        ("zha", "Back door sensor", None, "IKEA of Sweden", "PARASOLL door sensor", "binary_sensor", "unavailable"),
        ("hue", "Loft reading light", "Loft", "Signify Netherlands B.V.", "Hue white lamp", "light", "off"),
        ("ecobee", "Thermostat", "Den", "ecobee", "Smart Thermostat Premium", "climate", "heat"),
        ("ipp", "Printer", None, "HP", "OfficeJet 8020", "sensor", "idle"),
        ("roborock", "Vacuum", None, "Roborock", "S7", "vacuum", "docked"),
        ("mobile_app", "Owner Phone", None, "Generic", "Phone", "device_tracker", "home"),
        ("mobile_app", "Family Tablet", None, "Generic", "Tablet", "device_tracker", "not_home"),
    ]
    for i, (domain, name, room, maker, model, kind, state) in enumerate(others):
        octet = SHELLY.get(name)
        e = entry(domain, name, {"host": f"10.0.0.{octet}"} if octet else None, None, "setup_retry" if octet and state == "unavailable" else "loaded")
        d = device(f"d_{domain}_{i}", e, name, room, maker, model, f"b0b0b0b0b0{octet:02x}" if octet else None,
                   zigbee=f"00:12:4b:00:00:00:00:{i:02x}" if domain == "zha" else None)
        slug = name.lower().replace(" ", "_").replace("-", "_")
        ent(f"{kind}.{slug}", domain, e, d, state, {"friendly_name": name})
        if octet:  # Shelly reports its Wi-Fi signal to Home Assistant
            ent(f"sensor.{slug}_signal_strength", domain, e, d, "unavailable" if state == "unavailable" else "-65",
                {"friendly_name": f"{name} Signal strength", "unit_of_measurement": "dBm"}, category="diagnostic")

    # Automations: the 8 pm duplicate, two that work, and five leftovers whose configs were deleted.
    for oid, name, state in [("night_mode", "Night mode", "on"), ("night_mode_2", "Night mode", "on"),
                             ("morning_lights", "Morning lights", "on"), ("porch_on_at_sunset", "Porch on at sunset", "off")]:
        ent(f"automation.{oid}", "automation", None, None, state, {"friendly_name": name, "id": oid,
                                                                    **({"trigger": "20:00:00"} if "night" in oid else {})})
    for name in ["Old hallway motion", "Vacation lights", "Garage reminder", "Test automation", "Bedtime (old)"]:
        oid = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        ent(f"automation.{oid}", "automation", None, None, "unavailable", {"friendly_name": name, "restored": True})

    ent("sun.sun", "sun", None, None, "below_horizon", {"friendly_name": "Sun"})
    ent("zone.home", "zone", None, None, "0", {"friendly_name": "Home"})
    ent("person.owner", "person", None, None, "home", {"friendly_name": "Owner"})
    ent("script.movie_time", "script", None, None, "off", {"friendly_name": "Movie time"}, area="Den")
    ent("scene.evening", "scene", None, None, "unknown", {"friendly_name": "Evening"}, area="Den")

    # Pad with the phone's sensors (no room) and room sensors until the audit's counts hold.
    n = 0
    phone = next(d["id"] for d in devices if d["name"] == "Owner Phone")
    phone_entry = next(d["entry"] for d in devices if d["id"] == phone)
    while len(entities) < TOTAL:
        n += 1
        ent(f"sensor.owner_phone_sensor_{n}", "mobile_app", phone_entry, phone, "42", {"friendly_name": f"Owner Phone sensor {n}"})
    _balance(entities, devices)
    log = [{"name": "homeassistant.components.wiz", "message": ["Failed to update device at 10.0.0.220: timed out"],
            "level": "WARNING", "count": 956, "source": ["components/wiz/__init__.py", 80]},
           {"name": "homeassistant.components.shelly", "message": ["Error fetching Garage plug data: 10.0.0.234 timed out"],
            "level": "WARNING", "count": 12, "source": ["components/shelly/coordinator.py", 400]}]
    return {"areas": AREAS, "entries": entries, "devices": devices, "entities": entities, "system_log": log}


def _area(e: dict[str, Any], devices: dict[str, dict[str, Any]]) -> str | None:
    return e["area"] or (devices[e["device"]]["area"] if e["device"] else None)


def _balance(entities: list[dict[str, Any]], devices_list: list[dict[str, Any]]) -> None:
    """Move padding sensors between 'unknown'/'42' and no room / a room until the counts are the audit's."""
    devices = {d["id"]: d for d in devices_list}
    pad = [e for e in entities if e["entity_id"].startswith("sensor.owner_phone_sensor_")]
    for e in pad:
        e["state"] = "42"
    bad = sum(1 for e in entities if e["state"] in ("unavailable", "unknown"))
    for e in pad[: max(0, DOWN_OR_UNKNOWN - bad)]:
        e["state"] = "unknown"
    no_area = sum(1 for e in entities if not _area(e, devices))
    for e in reversed(pad):
        if no_area <= NO_AREA:
            break
        e["area"] = "Study"
        no_area -= 1


def summary(h: dict[str, Any]) -> dict[str, int]:
    devices = {d["id"]: d for d in h["devices"]}
    return {"entities": len(h["entities"]),
            "down_or_unknown": sum(1 for e in h["entities"] if e["state"] in ("unavailable", "unknown")),
            "no_area": sum(1 for e in h["entities"] if not _area(e, devices)),
            "devices": sum(1 for d in h["devices"] if not d["service"]), "areas": len(h["areas"]),
            "wiz": sum(1 for d in h["devices"] if d["manufacturer"] == "WiZ"),
            "wiz_down": sum(1 for e in h["entities"] if e["entity_id"].startswith("light.") and e["platform"] == "wiz" and e["state"] == "unavailable")}


if __name__ == "__main__":
    print(summary(house()))
