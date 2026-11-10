"""
NEXUS System Info Tool

Read-only answers about the PC NEXUS runs on: time, date, battery, CPU,
memory, disk space, uptime, Wi-Fi, running apps and basic specs. It uses
only the standard library, Windows' own system calls and the read-only
tasklist and netsh commands. Nothing is changed.
"""

import csv
import ctypes
import datetime
import io
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


TOPICS = (
    "time", "date", "battery", "cpu", "memory", "disk", "uptime",
    "network", "apps", "summary", "pc", "app"
)

# An app name that is safe to compare against process names.
_APP_NAME = re.compile(r"^[a-z0-9][a-z0-9 ._-]{1,28}$")

_NOT_AN_APP = {
    "it", "that", "this", "everything", "anything", "something", "nothing",
    "my pc", "my computer", "my laptop", "my system", "the pc",
    "the computer", "the laptop", "the system"
}

KB = 1024


# ==========================================================
# RECOGNISING QUESTIONS
# ==========================================================

_TRAILING = re.compile(
    r"\s+(?:please|for me|thanks|thank you|right now|now)$"
)

# Checked in this order; the first match in a clause wins.
_PATTERNS = [
    ("time", r"\bwhat time is it(?: right now| now| currently)?$"),
    ("time", r"\bwhat(?:'s| is) the (?:current |local )?time(?: right now| now)?$"),
    ("time", r"\b(?:tell me|give me|do you know|got) the (?:current )?time$"),
    ("date", r"\bwhat(?:'s| is) (?:the |today's |todays )+date$"),
    ("date", r"\bwhat day (?:is it|is today)(?: today)?$"),
    ("date", r"\bwhat is today$"),
    ("date", r"\btoday's date$|\btodays date$"),
    ("battery", r"\bhow much battery\b"),
    ("battery", r"\bbattery (?:level|percentage|percent|left|life|status)\b"),
    ("battery", r"\bwhat(?:'s| is) my battery\b"),
    ("battery", r"\bis (?:my|the|this) \w+ (?:charging|plugged in)$"),
    ("summary", r"\bhow(?:'s| is) my (?:pc|computer|laptop|system|machine) (?:doing|running|performing)\b"),
    ("summary", r"\bis my (?:pc|computer|laptop|system|machine) (?:running |being )?(?:slow|laggy|lagging|okay|ok|fine)\b"),
    ("summary", r"\b(?:system|pc|computer) (?:info|status|summary)$"),
    ("pc", r"\bwhat (?:pc|computer|laptop) is this\b"),
    ("pc", r"\bwhat (?:version of )?windows\b|\bwhich windows\b"),
    ("pc", r"\b(?:pc|system|computer) specs\b|\bmy specs\b"),
    ("pc", r"\bwhat (?:cpu|processor) do i have\b"),
    ("pc", r"\bwhat(?:'s| is) my (?:pc|computer|laptop) (?:name|called)\b"),
    ("cpu", r"\b(?:cpu|processor)\b.*\b(?:usage|load|using|busy)\b"),
    ("cpu", r"\bhow busy is my (?:cpu|processor)\b"),
    ("memory", r"\bhow much (?:ram|memory)\b"),
    ("memory", r"\b(?:ram|memory)\b.*\b(?:usage|left|free|used|using|available)\b"),
    ("disk", r"\bhow much (?:disk |storage |free |hard drive )?space\b"),
    ("disk", r"\b(?:disk|drive|storage|ssd)\b.*\b(?:space|left|free|full|usage)\b"),
    ("uptime", r"\bhow long (?:has|have) (?:my|this|the) (?:pc|computer|laptop|system|machine) been (?:on|running|up|turned on)\b"),
    ("uptime", r"\buptime\b"),
    ("network", r"\b(?:which|what) (?:wi-?fi|network)\b"),
    ("network", r"\bwi-?fi\b.*\b(?:connected|name|network|using)\b"),
    ("apps", r"\b(?:what|which) (?:apps|programs|applications)\b.*\b(?:running|open)\b"),
    ("apps", r"\bshow (?:the |my )?running (?:apps|programs|applications)\b"),
]

_COMPILED = [(topic, re.compile(pattern)) for topic, pattern in _PATTERNS]

_IS_RUNNING = re.compile(
    r"\b(?:is|check if|check whether|see if) "
    r"(?P<app>[a-z0-9][a-z0-9 ._-]{0,27}?) (?:is )?(?:running|open)\b"
)

_TYPED = re.compile(r"^system info (?P<topic>[a-z]+)(?: (?P<value>.+))?$")

_CLAUSE_SPLIT = re.compile(r"\s*(?:;|,|\band\b|\bthen\b|\bplus\b)\s*")


def _normal(text):

    lowered = str(text or "").lower().replace("’", "'")

    return re.sub(r"\s+", " ", lowered).strip(" .!?,")


def _topic_for_clause(clause):

    clause = clause.strip(" .!?,")

    while _TRAILING.search(clause):
        clause = _TRAILING.sub("", clause)

    for topic, pattern in _COMPILED:

        if pattern.search(clause):
            return topic, ""

    running = _IS_RUNNING.search(clause)

    if running:

        app = running.group("app").strip()

        if app not in _NOT_AN_APP and _APP_NAME.match(app):
            return "app", app

    return None


def detect_topics(text):
    """
    Questions about the PC found in a sentence, in order: a list of
    (topic, value) pairs. value is only used for 'app'. Empty when the
    text is not about the PC.
    """

    lowered = _normal(text)

    typed = _TYPED.match(lowered)

    if typed:

        topic = typed.group("topic")
        value = (typed.group("value") or "").strip()

        if topic == "app":
            return [("app", value)] if _APP_NAME.match(value) else []

        if topic in TOPICS and topic != "app" and not value:
            return [(topic, "")]

        return []

    found = []

    for clause in _CLAUSE_SPLIT.split(lowered):

        result = _topic_for_clause(clause)

        if result and result not in found:
            found.append(result)

    return found


# ==========================================================
# WORDING
# ==========================================================

def format_size(value):

    gigabytes = value / (1024 ** 3)

    if gigabytes >= 100:
        return f"{gigabytes:.0f} GB"

    if gigabytes >= 1:
        return f"{gigabytes:.1f} GB"

    return f"{value / (1024 ** 2):.0f} MB"


def _plural(count, word):

    return f"{count} {word}{'' if count == 1 else 's'}"


def format_duration(seconds):

    seconds = int(seconds)

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    if days:

        parts = [_plural(days, "day")]

        if hours:
            parts.append(_plural(hours, "hour"))

        return " ".join(parts)

    if hours:

        parts = [_plural(hours, "hour")]

        if minutes:
            parts.append(_plural(minutes, "minute"))

        return " ".join(parts)

    return _plural(minutes, "minute")


def format_time(now):

    hour = now.hour % 12 or 12

    return f"{hour}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}"


def format_date(now):

    return f"{now:%A}, {now.day} {now:%B} {now.year}"


def describe_battery(info):

    if info is None:
        return "I couldn't read the battery."

    if not info.get("has_battery"):

        return (
            "No battery detected. This looks like a desktop on mains power."
        )

    percent = info.get("percent")

    if percent is None:
        return "I couldn't read the battery level."

    if info.get("charging"):
        return f"Battery is at {percent}% and charging."

    text = f"Battery is at {percent}%, not charging"

    seconds_left = info.get("seconds_left")

    if seconds_left:
        return text + f", about {format_duration(seconds_left)} left."

    return text + "."


def describe_cpu(percent):

    if percent is None:
        return "I couldn't read the CPU usage."

    return f"CPU usage is {percent:.0f}%."


def describe_memory(memory):

    if not memory:
        return "I couldn't read the memory usage."

    used = memory["total"] - memory["available"]
    percent = round(used / memory["total"] * 100)

    return (
        f"Using {format_size(used)} of {format_size(memory['total'])} RAM "
        f"({percent}%). {format_size(memory['available'])} free."
    )


def describe_disks(disks):

    if not disks:
        return "I couldn't read the disk space."

    return ". ".join(
        f"{letter}: {format_size(free)} free of {format_size(total)}"
        for letter, total, free in disks[:4]
    ) + "."


def describe_uptime(seconds):

    if seconds is None:
        return "I couldn't read how long the PC has been on."

    return f"Your PC has been on for {format_duration(seconds)}."


def describe_network(info):

    if info is None:
        return "I couldn't check the network."

    if info.get("connected") and info.get("ssid"):
        return f'You\'re connected to the Wi-Fi network "{info["ssid"]}".'

    return (
        "You're not connected to Wi-Fi. You may be on a cable or offline."
    )


# Processes that are always running and not worth listing as apps.
_BACKGROUND = {
    "system", "system idle process", "registry", "memcompression", "dwm",
    "csrss", "svchost", "smss", "wininit", "winlogon", "services", "lsass",
    "fontdrvhost", "sihost", "taskhostw", "ctfmon", "searchhost",
    "runtimebroker", "textinputhost", "conhost", "tasklist", "python",
    "pythonw", "secure system", "wmiprvse", "audiodg", "ollama",
    "ollama app", "ollama_llama_server"
}

_FRIENDLY_NAMES = {
    "msedge": "Edge", "chrome": "Chrome", "opera": "Opera",
    "firefox": "Firefox", "code": "VS Code", "explorer": "File Explorer",
    "spotify": "Spotify", "whatsapp": "WhatsApp", "discord": "Discord",
    "notepad": "Notepad", "excel": "Excel", "winword": "Word",
    "powerpnt": "PowerPoint", "teams": "Teams", "zoom": "Zoom"
}


def _stem(image):

    return re.sub(r"\.exe$", "", image.strip(), flags=re.IGNORECASE).lower()


def describe_apps(processes):

    if not processes:
        return "I couldn't read the running apps."

    ranked = sorted(
        (
            (stem, kilobytes)
            for stem, kilobytes in (
                (_stem(image), kb) for image, kb in processes.items()
            )
            if stem not in _BACKGROUND
        ),
        key=lambda item: item[1],
        reverse=True
    )

    if not ranked:
        return "I couldn't see any apps running."

    listed = ", ".join(
        f"{_FRIENDLY_NAMES.get(stem, stem.replace('-', ' ').title())} "
        f"{format_size(kilobytes * KB)}"
        for stem, kilobytes in ranked[:5]
    )

    return f"Using the most memory: {listed}."


def describe_app_running(name, processes):

    if processes is None:
        return "I couldn't check the running apps."

    wanted = _stem(name)

    running = any(wanted in _stem(image) for image in processes)

    if running:
        return f"Yes, {name.strip().title()} is running."

    return f"No, I don't see {name.strip()} running."


def describe_pc(info, memory=None):

    if not info:
        return "I couldn't read the PC details."

    text = f"This is {info.get('name') or 'your PC'}"

    if info.get("os"):
        text += f", running {info['os']}"

    if info.get("cpu"):

        cores = f" ({info['cores']} cores)" if info.get("cores") else ""
        text += f", with a {info['cpu']}{cores}"

    if memory:
        text += f" and {format_size(memory['total'])} of RAM"

    return text + "."


def describe_summary(cpu, memory, battery, disks):

    problems = []

    if cpu is not None and cpu >= 85:
        problems.append(f"CPU is very busy ({cpu:.0f}%)")

    if memory and (memory["total"] - memory["available"]) / memory["total"] >= 0.9:
        problems.append("memory is nearly full")

    if (
        battery and battery.get("has_battery")
        and battery.get("percent") is not None
        and battery["percent"] <= 20
        and not battery.get("charging")
    ):
        problems.append(f"battery is low ({battery['percent']}%)")

    for letter, total, free in disks or []:

        if total and free / total < 0.1:
            problems.append(f"{letter}: is almost full")

    if problems:
        return "Heads up: " + ", ".join(problems) + "."

    details = []

    if cpu is not None:
        details.append(f"CPU at {cpu:.0f}%")

    if memory:

        used = (memory["total"] - memory["available"]) / memory["total"]
        details.append(f"memory {used * 100:.0f}% used")

    if battery and battery.get("has_battery") and battery.get("percent") is not None:

        state = "and charging" if battery.get("charging") else "on battery"
        details.append(f"battery {battery['percent']}% {state}")

    if disks:

        letter, total, free = disks[0]
        details.append(f"{letter}: {format_size(free)} free")

    return "Everything looks fine. " + ", ".join(details) + "."


# ==========================================================
# READING THE PC
# ==========================================================

def _kernel32():

    windll = getattr(ctypes, "windll", None)

    return getattr(windll, "kernel32", None) if windll else None


class SystemReader:
    """Reads the real PC. Methods return None when they cannot."""

    def _windows(self):

        return sys.platform == "win32"

    def _run(self, command):

        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    def now(self):

        return datetime.datetime.now()

    def battery(self):

        if not self._windows():
            return None

        class PowerStatus(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_ubyte),
                ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong)
            ]

        status = PowerStatus()

        if not _kernel32().GetSystemPowerStatus(ctypes.byref(status)):
            return None

        return {
            "has_battery": (
                not (status.BatteryFlag & 128) and status.BatteryFlag != 255
            ),
            "percent": (
                status.BatteryLifePercent
                if status.BatteryLifePercent != 255 else None
            ),
            "charging": status.ACLineStatus == 1,
            "seconds_left": (
                None if status.BatteryLifeTime == 0xFFFFFFFF
                else status.BatteryLifeTime
            )
        }

    def memory(self):

        if not self._windows():
            return None

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)

        if not _kernel32().GlobalMemoryStatusEx(ctypes.byref(status)):
            return None

        return {
            "total": status.ullTotalPhys,
            "available": status.ullAvailPhys
        }

    def cpu_percent(self):

        if not self._windows():
            return None

        kernel32 = _kernel32()

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low", ctypes.c_ulong),
                ("high", ctypes.c_ulong)
            ]

        def sample():

            idle, kernel, user = FileTime(), FileTime(), FileTime()

            if not kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            ):
                return None

            def number(value):
                return (value.high << 32) | value.low

            # Kernel time already includes idle time.
            return number(idle), number(kernel) + number(user)

        first = sample()

        if first is None:
            return None

        time.sleep(0.5)

        second = sample()

        if second is None:
            return None

        total = second[1] - first[1]

        if total <= 0:
            return None

        return max(0.0, min(100.0, (1 - (second[0] - first[0]) / total) * 100))

    def disks(self):

        if not self._windows():
            return None

        kernel32 = _kernel32()

        drives = []

        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":

            root = f"{letter}:\\"

            if not os.path.exists(root):
                continue

            # 3 means a fixed disk; skip CD drives, USB sticks and shares.
            if kernel32.GetDriveTypeW(root) != 3:
                continue

            try:
                usage = shutil.disk_usage(root)
            except OSError:
                continue

            drives.append((letter, usage.total, usage.free))

        return drives or None

    def uptime_seconds(self):

        if not self._windows():
            return None

        kernel32 = _kernel32()

        kernel32.GetTickCount64.restype = ctypes.c_ulonglong

        return kernel32.GetTickCount64() / 1000

    def pc_info(self):

        info = {"name": platform.node(), "cores": os.cpu_count()}

        try:

            build = sys.getwindowsversion().build

            info["os"] = (
                f"{'Windows 11' if build >= 22000 else 'Windows 10'} "
                f"(build {build})"
            )

        except AttributeError:

            info["os"] = platform.platform()

        try:

            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:

                info["cpu"] = re.sub(
                    r"\s+", " ",
                    winreg.QueryValueEx(key, "ProcessorNameString")[0]
                ).strip()

        except Exception:

            info["cpu"] = platform.processor() or None

        return info

    def network(self):

        if not self._windows():
            return None

        try:
            output = self._run(
                ["netsh", "wlan", "show", "interfaces"]
            ).stdout
        except Exception:
            return None

        state = re.search(r"^\s*State\s*:\s*(.+)$", output, re.MULTILINE)
        ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", output, re.MULTILINE)

        if state and state.group(1).strip().lower() == "connected" and ssid:

            return {"connected": True, "ssid": ssid.group(1).strip()}

        return {"connected": False}

    def processes(self):
        """Memory in KB per program, summed over its processes."""

        if not self._windows():
            return None

        try:
            output = self._run(["tasklist", "/FO", "CSV", "/NH"]).stdout
        except Exception:
            return None

        totals = {}

        for row in csv.reader(io.StringIO(output)):

            if len(row) < 5:
                continue

            digits = re.sub(r"\D", "", row[4])

            image = row[0].strip().lower()

            totals[image] = totals.get(image, 0) + (int(digits) if digits else 0)

        return totals or None


# ==========================================================
# THE TOOL
# ==========================================================

class SystemInfoTool(BaseTool):

    name = "system"

    description = (
        "Answers read-only questions about this PC: time, date, battery, "
        "CPU, memory, disk, uptime, Wi-Fi, running apps and specs."
    )

    def __init__(self, reader=None):

        self.reader = reader or SystemReader()

    def can_handle(self, query):

        return bool(query) and bool(detect_topics(query))

    def execute(self, query):

        topics = detect_topics(query)

        if not topics:

            return ToolResponse.failure(
                "I'm not sure what you'd like to know about the PC."
            )

        try:

            answers = [self.answer(topic, value) for topic, value in topics]

        except Exception as error:

            logger.warning("System info failed: %s", error)

            return ToolResponse.failure(
                "I couldn't read that from the PC."
            )

        return ToolResponse.success(" ".join(answers))

    def answer(self, topic, value=""):

        reader = self.reader

        if topic == "time":
            return f"It's {format_time(reader.now())}."

        if topic == "date":
            return f"Today is {format_date(reader.now())}."

        if topic == "battery":
            return describe_battery(reader.battery())

        if topic == "cpu":
            return describe_cpu(reader.cpu_percent())

        if topic == "memory":
            return describe_memory(reader.memory())

        if topic == "disk":
            return describe_disks(reader.disks())

        if topic == "uptime":
            return describe_uptime(reader.uptime_seconds())

        if topic == "network":
            return describe_network(reader.network())

        if topic == "apps":
            return describe_apps(reader.processes())

        if topic == "pc":
            return describe_pc(reader.pc_info(), reader.memory())

        if topic == "app":
            return describe_app_running(value, reader.processes())

        if topic == "summary":

            return describe_summary(
                reader.cpu_percent(),
                reader.memory(),
                reader.battery(),
                reader.disks()
            )

        return "I'm not sure what you'd like to know about the PC."
