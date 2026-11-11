"""
NEXUS Capabilities

One honest list of what NEXUS can and cannot do. The system prompt, the
"what can you do" answers and the tests all read from it, so they cannot
disagree with each other. Add a feature here when it is built.
"""

import re


# (name, what it does, an example the user can say)
CAPABILITIES = (
    ("Apps and websites",
     "open apps, folders and websites",
     "open notepad"),
    ("Search",
     "search Google, YouTube, GitHub, Wikipedia and Reddit",
     "search youtube for the weeknd"),
    ("Research",
     "research a topic from the web and summarise it",
     "research quantum computing"),
    ("Maths",
     "do arithmetic",
     "what is 15 percent of 240"),
    ("Google Meet",
     "open a Google Meet from a meeting code",
     "join the meeting abc-defg-hij"),
    ("New meeting",
     "start a new Google Meet (you must be signed in to Google in Opera)",
     "start a new meeting"),
    ("PC checks",
     "read the time, date, battery, CPU, memory, disk space, uptime, "
     "Wi-Fi, running apps and PC specs",
     "how much free space do i have"),
    ("Media",
     "play, pause, skip or go back a track, mute, and change or set the volume",
     "set the volume to 40"),
    ("About Nexus",
     "show the speech profile, the performance report and what it knows about you",
     "what do you know about me"),
    ("Conversation",
     "answer questions and talk things through",
     "explain how a transistor works"),
)

# Things NEXUS cannot do today, and a few words that point at each.
LIMITS = (
    ("send or read email and messages", ("email", "e-mail", "gmail", "text message", "sms", "whatsapp message", "dm")),
    ("make phone calls", ("call", "phone", "ring")),
    ("set reminders, alarms or timers", ("remind", "reminder", "alarm", "timer")),
    ("see your screen or take screenshots", ("screenshot", "screen shot", "my screen")),
    ("click or type inside other apps", ("click", "type into", "fill in", "fill out")),
    ("pick a specific song or playlist (it only uses the play, skip and volume keys)", ("playlist",)),
    ("delete, move or edit your files", ("delete", "remove file", "rename", "move file")),
    ("install software or run arbitrary commands", ("install", "uninstall", "run command", "terminal", "cmd")),
    ("shut down, restart or lock the PC", ("shut down", "shutdown", "restart", "reboot", "lock my")),
    ("check the weather or live news without researching it", ("weather", "forecast")),
    ("schedule a meeting for later or invite people to one", ("schedule a meeting", "invite")),
    ("turn your camera or mic on in a meeting (it only opens the meeting link)", ("camera", "unmute me")),
)


def prompt_block():
    """The CAPABILITIES section of the system prompt."""

    can = "\n".join(f"- {what}" for _, what, _ in CAPABILITIES)
    cannot = "\n".join(f"- {what}" for what, _ in LIMITS)

    return (
        "NEXUS can:\n"
        f"{can}\n\n"
        "NEXUS cannot (today):\n"
        f"{cannot}\n\n"
        "The things NEXUS can do run before a message reaches you. If Rohan "
        "asks for one of them and the message is in front of you, the "
        "action did not run. Do not say you cannot do such things, and do "
        "not claim you did them. Say it did not go through and ask him to "
        "say it again. For anything on the cannot list, say plainly that NEXUS "
        "cannot do it yet. Never offer to run a system check or use a "
        "tool you do not have."
    )


# ----------------------------------------------------------
# QUESTIONS ABOUT NEXUS ITSELF
# ----------------------------------------------------------

_OVERVIEW = re.compile(
    r"\b(?:what|which) (?:all )?(?:can|could) (?:you|u) (?:do|help (?:me )?with)\b"
    r"|\bwhat are (?:you|u) (?:capable of|able to do)\b"
    r"|\bwhat (?:are|is) your (?:capabilities|abilities|features|skills|functions)\b"
    r"|\bwhat (?:can|do) (?:you|u) (?:know|support)\b"
    r"|\bwhat are your powers\b|\bhow can you help (?:me)?\b"
)

_LIMIT_OVERVIEW = re.compile(
    r"\bwhat (?:can'?t|cannot|can not) (?:you|u) do\b"
    r"|\bwhat (?:are|is) your (?:limits|limitations|weaknesses)\b"
    r"|\bwhat (?:are|aren't|arent) (?:you|u) (?:not )?(?:unable|not able) to do\b"
    r"|\bwhat can (?:you|u) not do\b"
)

_CAN_YOU = re.compile(
    r"^(?:ok |okay |hey |so )?(?:can|could|will|would) (?:you|u)\b|"
    r"^(?:are|r) (?:you|u) (?:able|capable) to\b|^do (?:you|u) (?:know how to|support)\b"
)


# "can you explain how to delete a file" is a question about the topic.
_ASKING_ABOUT = {
    "explain", "tell", "show", "teach", "describe", "help", "write",
    "give", "say", "summarise", "summarize", "suggest", "recommend"
}


def _words(text):
    return re.sub(r"[^a-z0-9' -]", " ", str(text or "").lower())


def overview():

    lines = ["Here's what I can do:"]

    for name, what, example in CAPABILITIES:
        lines.append(f"- {name}: {what}. Try: \"{example}\".")

    return "\n".join(lines)


def limits():

    lines = ["Here's what I can't do yet:"]

    for what, _ in LIMITS:
        lines.append(f"- {what}")

    return "\n".join(lines)


def _limit_for(text):

    lowered = f" {_words(text)} "

    for what, keywords in LIMITS:

        for word in keywords:

            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return what

    return None


def answer(text):
    """
    A reply when the message asks what NEXUS can or cannot do, else None.
    Plain facts, no model needed.
    """

    lowered = " ".join(_words(text).split())

    if not lowered or len(lowered) > 120:
        return None

    if _LIMIT_OVERVIEW.search(lowered):
        return limits()

    if _OVERVIEW.search(lowered):
        return overview()

    asked = _CAN_YOU.search(lowered)

    if asked:

        # Only the action right after "can you": "can you explain how to
        # delete a file" is a question for the model, not a request.
        rest = lowered[asked.end():].split()

        limit = None

        if rest and rest[0] not in _ASKING_ABOUT:
            limit = _limit_for(" ".join(rest[:4]))

        if limit:
            return f"No, I can't do that yet. I can't {limit}."

    return None
