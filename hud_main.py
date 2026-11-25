"""
NEXUS 2.0
Launch NEXUS with the HUD window.

    python hud_main.py

main.py is unchanged and still starts the terminal version.
"""

import os
import sys
import threading

from ui.hud_state import (
    MODE_LABELS,
    HudBridge,
    TeeStream,
    derive_state,
)
from ui.status import get_status


EXIT_WORDS = ("exit", "quit", "shutdown")


class HudRuntime:
    """Connects the HUD window to the assistant without changing it."""

    def __init__(self):

        self.bridge = HudBridge()

        self.assistant = None

        self.original_process = None

        # One request at a time, whether it came from voice or the text box.
        self.lock = threading.Lock()

    # ======================================================
    # WHAT THE WINDOW SHOWS
    # ======================================================

    def snapshot(self):

        mode = "voice"
        recording = False

        assistant = self.assistant

        if assistant is not None:

            manager = assistant.input_manager

            mode = getattr(manager, "mode", "voice")
            recording = bool(getattr(manager, "recording", False))

        state = derive_state(
            get_status(),
            recording=recording,
            mode=mode,
            speaking=self.bridge.speaking,
            booting=self.bridge.booting
        )

        return state, MODE_LABELS.get(mode, "")

    # ======================================================
    # ASSISTANT THREAD
    # ======================================================

    def run_assistant(self):

        finished = False

        try:

            from core.assistant import NexusAssistant

            assistant = NexusAssistant()

            self._attach(assistant)

            self.assistant = assistant

            self.bridge.set_ready()

            assistant.start()

            finished = True

        except Exception as error:

            print(f"\nNEXUS could not run: {error}")

        finally:

            self.bridge.set_ready()

            # NEXUS ended normally (for example "goodbye"): close the window.
            if finished:
                self.bridge.close_requested.set()

    def _attach(self, assistant):
        """Add the window's hooks on the running objects, not in the code."""

        self.original_process = assistant.process_input

        def process_input(user_input):

            with self.lock:
                return self.original_process(user_input)

        assistant.process_input = process_input

        speaker = assistant.speaker

        original_speak = speaker.speak

        def speak(text, quiet=False):

            self.bridge.begin_speaking()

            try:
                return original_speak(text, quiet=quiet)
            finally:
                self.bridge.end_speaking()

        speaker.speak = speak

        assistant.input_manager.command_speaker = speak

    # ======================================================
    # TEXT TYPED IN THE WINDOW
    # ======================================================

    def submit(self, text):

        if text.lower() in EXIT_WORDS:

            self.bridge.close_requested.set()

            return

        if self.assistant is None:

            print("\nNEXUS: Still starting up, one moment.")

            return

        threading.Thread(
            target=self._run_typed,
            args=(text,),
            daemon=True
        ).start()

    def _run_typed(self, text):

        assistant = self.assistant

        with self.lock:

            try:

                assistant.input_manager.last_input_was_voice = False

                print(f"\nYou: {text}")

                response = self.original_process(text)

                if assistant.response_displayed:

                    # Already written while it was generated.
                    assistant.response_displayed = False

                    print()

                else:

                    print("\nNEXUS:", response, "\n")

            except Exception as error:

                print(f"\nNEXUS error: {error}")

    # ======================================================
    # SHUTDOWN
    # ======================================================

    def shutdown(self):

        if self.assistant is not None:

            try:
                self.assistant.shutdown()
            except Exception as error:
                print(f"Shutdown error: {error}", file=sys.stderr)


def main():

    from ui.hud import HudWindow

    runtime = HudRuntime()

    original_stdout = sys.stdout

    sys.stdout = TeeStream(original_stdout, runtime.bridge)

    try:

        window = HudWindow(
            runtime.bridge,
            runtime.snapshot,
            runtime.submit
        )

    except ImportError:

        sys.stdout = original_stdout

        print(
            "tkinter is not installed with this Python. Re-run the Python "
            "installer, choose Modify, and tick 'tcl/tk and IDLE'."
        )

        return

    threading.Thread(
        target=runtime.run_assistant,
        daemon=True
    ).start()

    try:

        window.run()

    finally:

        sys.stdout = original_stdout

        runtime.shutdown()

        # The assistant thread may still be waiting for a key or the
        # microphone, so end the process once the databases are closed.
        sys.stdout.flush()

        os._exit(0)


if __name__ == "__main__":

    main()
