"""Names and settings in one place. The domain is a working name: change it here only."""

DOMAIN = "sunrise"
NAME = "Sunrise"
VERSION = "0.1.0"
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

# The opt-in cloud mode seam (see cloud.py). Off by default and nothing implements it yet.
CONF_CLOUD_MODE = "cloud_mode"
CLOUD_MODE_DEFAULT = False
