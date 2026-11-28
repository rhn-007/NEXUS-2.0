"""Real PC statistics for the HUD, read with NEXUS's own SystemReader.

Values are None when they cannot be read (for example on a desktop PC with no
battery, or off Windows); the HUD then shows "--" instead of inventing a number.
"""

from tools.system_info import SystemReader


def collect(reader=None):
    """CPU %, memory % in use, and battery info, each possibly None."""

    reader = reader or SystemReader()

    cpu = _safe(reader.cpu_percent)

    memory = None
    info = _safe(reader.memory)

    if info and info.get("total"):
        memory = (1.0 - info["available"] / info["total"]) * 100.0

    return {
        "cpu": cpu,
        "memory": memory,
        "battery": _safe(reader.battery),
    }


def _safe(call):

    try:
        return call()
    except Exception:
        return None


def format_percent(value):
    return "--" if value is None else f"{value:.0f}%"


def format_battery(battery):

    if not battery:
        return "--"

    if not battery.get("has_battery"):
        return "AC POWER"

    percent = battery.get("percent")

    if percent is None:
        return "--"

    return f"{percent}% CHARGING" if battery.get("charging") else f"{percent}%"
