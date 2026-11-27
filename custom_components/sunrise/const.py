"""Names and settings in one place. The domain is a working name: change it here only."""

DOMAIN = "sunrise"
NAME = "Sunrise"
VERSION = "0.3.0"
MIN_HA_VERSION = "2026.10.0"

LLM_API_ID = DOMAIN  # MCP endpoint: /api/mcp/sunrise
LLM_API_NAME = NAME

DATA_FOLDER = DOMAIN  # <config>/sunrise/, outside custom_components
SHIPPED_SKILLS = "bundled_skills"  # inside this integration: the product's copies

ACT_CUTOFF_S = 6.0  # how long `act` waits for a device to show the change
RELOAD_WAIT_S = 3.0  # after a reload, before reading the entry and its entities back

# Locks, alarms and garage doors move only with the person's yes in the same conversation (rule S2).
GUARDED_DOMAINS = ("lock", "alarm_control_panel")
GUARDED_DEVICE_CLASSES = ("garage", "door", "gate")
# A discovered integration that can make any of these is accepted only with the owner's yes for that device.
# Covers count because doors and gates are covers, and which kind it is only shows once it's added.
GUARDED_PLATFORMS = (*GUARDED_DOMAINS, "cover", "climate", "water_heater", "valve")

# Where a device Home Assistant found by itself (its Discovered list) came from. Not user, reauth,
# reconfigure, import, ignore or system: those aren't discoveries waiting for a yes.
DISCOVERY_SOURCES = ("zeroconf", "dhcp", "ssdp", "bluetooth", "homekit", "usb", "mqtt", "integration_discovery",
                     "discovery", "hassio")

# Options (Settings > Devices & services > Sunrise > Configure). Off: the read tools see only what's exposed to
# voice assistants, like everything else Sunrise does (access.py).
CONF_READ_UNEXPOSED = "read_unexposed"
READ_UNEXPOSED_DEFAULT = True

# The opt-in cloud mode seam (see cloud.py). Off by default and nothing implements it yet.
CONF_CLOUD_MODE = "cloud_mode"
CLOUD_MODE_DEFAULT = False
