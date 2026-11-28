"""Pure logic that turns what NEXUS is really doing into an orb state.

No Qt here, so it can be tested anywhere. The inputs are real signals:
the activity label from ui.status (set by the assistant, router, listener and
speaker), whether the microphone is recording, whether Piper audio is playing,
and whether a command is being processed.
"""

STATE_LABELS = {
    "idle": "STANDING BY",
    "listening": "LISTENING",
    "thinking": "THINKING",
    "speaking": "SPEAKING",
    "researching": "RESEARCHING",
    "error": "SYSTEM ERROR",
}


def state_from_status(label, recording=False, speaking=False, busy=False):
    """
    Work out the orb state.

    label      current ui.status activity label (or None)
    recording  the microphone is recording (push-to-talk held)
    speaking   Piper audio is playing right now
    busy       a command is being processed
    """

    text = str(label or "").strip().lower()

    if recording:
        return "listening"

    if speaking or text.startswith("speaking"):
        return "speaking"

    if "research" in text:
        return "researching"

    if text.startswith("listening"):
        return "listening"

    # Anything else (Thinking, Transcribing, Preparing speech, Calculating,
    # Opening application ...) is NEXUS working on something.
    if text or busy:
        return "thinking"

    return "idle"


def describe_state(state):
    return STATE_LABELS.get(state, STATE_LABELS["idle"])


def mic_status(ready, recording, busy):
    """Text for the microphone indicator."""

    if not ready:
        return "OFFLINE"

    if recording:
        return "RECORDING"

    if busy:
        return "BUSY"

    return "READY"
