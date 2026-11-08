"""
NEXUS Hotkey Helper

Parses key combinations such as "ctrl+alt+x" and detects when one has been
pressed. It works with plain key names, so it does not depend on pynput
and can be tested without a keyboard.
"""

DEFAULT_HOTKEY = "ctrl+alt+x"

MODIFIERS = ("ctrl", "alt", "shift")

MODIFIER_ALIASES = {
    "control": "ctrl"
}


def parse_hotkey(text):
    """
    Turn "ctrl+alt+x" into ({"ctrl", "alt"}, "x").

    A hotkey needs at least one modifier (ctrl, alt or shift) so that an
    ordinary key can never trigger it by accident.
    """

    parts = [
        part.strip().lower()
        for part in str(text).split("+")
        if part.strip()
    ]

    parts = [
        MODIFIER_ALIASES.get(part, part)
        for part in parts
    ]

    if len(parts) < 2:

        raise ValueError(
            "A hotkey needs at least one modifier and a key, "
            "for example ctrl+alt+x."
        )

    *modifiers, key = parts

    unknown = [
        item for item in modifiers
        if item not in MODIFIERS
    ]

    if unknown:

        raise ValueError(
            f"Unknown modifier: {', '.join(unknown)}. "
            f"Use ctrl, alt or shift."
        )

    if key in MODIFIERS:

        raise ValueError(
            "The last part of a hotkey must be a normal key, "
            "not a modifier."
        )

    return frozenset(modifiers), key


def format_hotkey(text):
    """Return a readable label such as "Ctrl+Alt+X"."""

    modifiers, key = parse_hotkey(text)

    ordered = [
        modifier.capitalize()
        for modifier in MODIFIERS
        if modifier in modifiers
    ]

    label = key.upper() if len(key) == 1 else key.capitalize()

    return "+".join(ordered + [label])


def key_name(key):
    """
    Convert a pynput key into a plain name.

    Modifiers become "ctrl", "alt" or "shift" (left and right keys are the
    same). Letters and digits are identified by their virtual-key code,
    because holding Ctrl changes the character pynput reports.
    Returns None for keys that cannot be named.
    """

    name = getattr(key, "name", None)

    if isinstance(name, str):

        for modifier in MODIFIERS:

            if name.startswith(modifier):
                return modifier

        return name

    code = getattr(key, "vk", None)

    if isinstance(code, int):

        if 65 <= code <= 90 or 48 <= code <= 57:
            return chr(code).lower()

    char = getattr(key, "char", None)

    if char and char.isprintable():
        return char.lower()

    return None


class HotkeyTracker:
    """
    Tracks which keys are held and reports when the hotkey is pressed.

    press() returns True once per press of the hotkey. Holding the key
    down (key repeat) does not trigger it again until it is released.
    Extra modifiers held at the same time (for example Shift) prevent it
    from triggering.
    """

    def __init__(self, hotkey=DEFAULT_HOTKEY):

        self.modifiers, self.key = parse_hotkey(hotkey)

        self.held = set()
        self._fired = False

    def reset(self):

        self.held.clear()
        self._fired = False

    def press(self, name):

        if not name:
            return False

        self.held.add(name)

        if name != self.key or self._fired:
            return False

        held_modifiers = {
            item for item in self.held
            if item in MODIFIERS
        }

        if held_modifiers != set(self.modifiers):
            return False

        self._fired = True

        return True

    def release(self, name):

        if not name:
            return

        self.held.discard(name)

        if name == self.key:
            self._fired = False
