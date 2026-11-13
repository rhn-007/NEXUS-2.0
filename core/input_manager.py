"""
NEXUS Input Manager

Handles Push-to-Talk voice input and keyboard mode.

Voice mode:
    Hold SPACE  -> Start recording
    Release     -> Stop recording and transcribe
    Press ESC   -> Switch to keyboard mode
    Press Ctrl+Alt+X -> Switch to continuous listening

Continuous listening:
    NEXUS listens on its own and answers each spoken sentence
    Press Ctrl+Alt+X again -> Return to Push-to-Talk
    Press ESC              -> Switch to keyboard mode
    (the key combination can be changed with NEXUS_CONTINUOUS_KEY)

Keyboard mode:
    Type normally
    Type "voice mode" -> Return to Push-to-Talk
"""

import os
import time

from pynput import keyboard
from voice.listener import Listener
from core.power_command import ShutdownPhraseHandler
from core.hotkey import (
    DEFAULT_HOTKEY,
    HotkeyTracker,
    format_hotkey,
    key_name
)
from utils.logger import setup_logger
from threading import Event, Lock, Timer

logger = setup_logger(__name__)


class InputManager:

    # Ignore very brief SPACE events, which can be caused by accidental
    # taps or transient keyboard events.
    SPACE_HOLD_THRESHOLD = 0.25

    # Pause before the microphone opens again in continuous listening, so
    # the end of NEXUS's own spoken reply is not heard as a new request.
    CONTINUOUS_RESUME_DELAY = 0.6

    def __init__(self):

        self.mode = "voice"
        self.last_input_was_voice = False

        self.shutdown_phrase = ShutdownPhraseHandler()
        self.command_speaker = None

        logger.info("Loading voice input system...")

        self.listener = Listener()

        self.recording = False
        self.completed = Event()
        self.recorded_text = ""
        self.keyboard_listener = None

        self.space_down = False
        self.start_timer = None
        self.state_lock = Lock()

        # Continuous listening
        self.hotkey = self._load_hotkey()
        self.hotkey_label = format_hotkey(self.hotkey)
        self.hotkey_tracker = HotkeyTracker(self.hotkey)
        self.continuous_stop = Event()
        self.pending_mode = None
        self.mode_key_listener = None
        self.continuous_active = False

        logger.info("Push-to-Talk input manager initialized.")

    def _load_hotkey(self):
        """Read the continuous-listening key combination from the environment."""

        configured = os.environ.get(
            "NEXUS_CONTINUOUS_KEY",
            DEFAULT_HOTKEY
        )

        try:

            format_hotkey(configured)

            return configured

        except ValueError as e:

            logger.warning(
                f"Invalid NEXUS_CONTINUOUS_KEY '{configured}': {e} "
                f"Using {DEFAULT_HOTKEY}."
            )

            return DEFAULT_HOTKEY

    # ======================================================
    # MAIN INPUT
    # ======================================================

    def get_input(self):

        while True:

            if self.mode != "continuous":

                self._stop_mode_keys()
                self.continuous_active = False

            if self.mode == "voice":

                text = self.voice_input()

            elif self.mode == "continuous":

                text = self.continuous_input()

            else:

                text = self.keyboard_input()

            if not text:

                continue

            if self.handle_command(text):

                continue

            return text

    # ======================================================
    # PUSH-TO-TALK VOICE INPUT
    # ======================================================

    def voice_input(self):

        self.completed.clear()
        self.recorded_text = ""
        self.recording = False
        self.space_down = False
        self.start_timer = None

        self.hotkey_tracker.reset()

        print("\nHold SPACE to speak. Release to send.")
        print(f"Press {self.hotkey_label} for continuous listening.")
        print("Press ESC to switch to keyboard mode.")

        def begin_recording():

            with self.state_lock:

                if not self.space_down or self.mode != "voice":
                    return

                try:

                    self.listener.start_recording()
                    self.recording = True

                    print("\nNEXUS listening...")

                except Exception as e:

                    logger.error(f"Recording start error: {e}")
                    self.recording = False
                    self.completed.set()

        def on_press(key):

            if self.hotkey_tracker.press(key_name(key)):

                with self.state_lock:

                    self.space_down = False

                    if self.start_timer:
                        self.start_timer.cancel()
                        self.start_timer = None

                    if self.recording:

                        try:
                            self.listener.stop_recording()

                        except Exception as e:
                            logger.error(f"Recording cancellation error: {e}")

                        finally:
                            self.recording = False

                self.mode = "continuous"
                self.completed.set()

                return False

            if key == keyboard.Key.esc:

                with self.state_lock:

                    self.space_down = False

                    if self.start_timer:
                        self.start_timer.cancel()
                        self.start_timer = None

                    if self.recording:

                        try:
                            self.listener.stop_recording()

                        except Exception as e:
                            logger.error(f"Recording cancellation error: {e}")

                        finally:
                            self.recording = False

                self.mode = "keyboard"
                self.completed.set()

                return False

            if key == keyboard.Key.space:

                with self.state_lock:

                    if not self.space_down and not self.recording:

                        self.space_down = True

                        self.start_timer = Timer(
                            self.SPACE_HOLD_THRESHOLD,
                            begin_recording
                        )
                        self.start_timer.daemon = True
                        self.start_timer.start()

        def on_release(key):

            self.hotkey_tracker.release(key_name(key))

            if key == keyboard.Key.space:

                with self.state_lock:

                    self.space_down = False

                    if self.start_timer:
                        self.start_timer.cancel()
                        self.start_timer = None

                    if not self.recording:
                        return

                    try:

                        print("\nProcessing speech...")

                        self.recorded_text = self.listener.stop_recording()

                    except Exception as e:

                        logger.error(f"Recording stop error: {e}")
                        self.recorded_text = ""

                    finally:

                        self.recording = False
                        self.completed.set()

                return False

        try:

            self.keyboard_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release
            )

            self.keyboard_listener.start()

            self.completed.wait()

            self.keyboard_listener.stop()
            self.keyboard_listener.join()

            if self.mode == "continuous":

                print("\nNEXUS: Continuous listening enabled.")

            if self.mode == "keyboard":

                print("\nNEXUS: Keyboard mode enabled.")

                logger.info("Switched to keyboard mode.")

                return ""

            if self.mode == "continuous":

                logger.info("Switched to continuous listening.")

                return ""

            text = self.recorded_text.strip()
            self.last_input_was_voice = bool(text)

            if text:

                print(f"\nYou: {text}")

            return text

        except Exception as e:

            logger.error(f"Push-to-Talk error: {e}")

            return ""

        finally:

            with self.state_lock:

                self.space_down = False

                if self.start_timer:
                    self.start_timer.cancel()
                    self.start_timer = None

                if self.keyboard_listener:
                    self.keyboard_listener.stop()

                self.recording = False

    # ======================================================
    # CONTINUOUS LISTENING
    # ======================================================

    def continuous_input(self):
        """
        Listen for one spoken sentence without any key being held.

        The key listener stays active between calls, so pressing the toggle
        key (or ESC) while NEXUS is busy answering is still noticed and
        applied the next time input is requested.
        """

        self._start_mode_keys()

        pending = self._take_pending_mode()

        if pending:

            self._switch_mode(pending)

            return ""

        if not self.continuous_active:

            self.continuous_active = True

            print(
                f"\nNEXUS listening continuously. "
                f"Press {self.hotkey_label} to stop, ESC for keyboard mode."
            )

        else:

            print("\nListening...")

        time.sleep(self.CONTINUOUS_RESUME_DELAY)

        try:

            text = self.listener.listen_for_utterance(
                self.continuous_stop
            )

        except Exception as e:

            logger.error(f"Continuous listening error: {e}")

            print(
                "\nNEXUS: Continuous listening failed. "
                "Returning to Push-to-Talk."
            )

            self._take_pending_mode()
            self._switch_mode("voice", announce=False)

            return ""

        pending = self._take_pending_mode()

        if pending:

            self._switch_mode(pending)

        text = (text or "").strip()

        self.last_input_was_voice = bool(text)

        if text:

            print(f"\nYou: {text}")

        return text

    def _request_mode(self, mode):
        """Ask for a mode change and wake up the listening loop."""

        with self.state_lock:

            self.pending_mode = mode

        self.continuous_stop.set()

    def _take_pending_mode(self):
        """Return the requested mode (or None) and clear the request."""

        with self.state_lock:

            mode = self.pending_mode
            self.pending_mode = None

        self.continuous_stop.clear()

        return mode

    def _switch_mode(self, mode, announce=True):

        self.mode = mode
        self.continuous_active = False

        self._stop_mode_keys()

        if mode == "keyboard":

            if announce:
                print("\nNEXUS: Keyboard mode enabled.")

            logger.info("Switched to keyboard mode.")

        else:

            if announce:
                print("\nNEXUS: Push-to-Talk mode enabled.")

            logger.info("Switched to Push-to-Talk mode.")

    def _start_mode_keys(self):
        """Watch for the toggle key and ESC while in continuous listening."""

        if self.mode_key_listener is not None:
            return

        self.hotkey_tracker.reset()

        def on_press(key):

            name = key_name(key)

            if name == "esc":

                self._request_mode("keyboard")

            elif self.hotkey_tracker.press(name):

                self._request_mode("voice")

        def on_release(key):

            self.hotkey_tracker.release(key_name(key))

        self.mode_key_listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release
        )

        self.mode_key_listener.daemon = True
        self.mode_key_listener.start()

    def _stop_mode_keys(self):

        listener = self.mode_key_listener
        self.mode_key_listener = None

        if listener is not None:
            listener.stop()

    # ======================================================
    # KEYBOARD INPUT
    # ======================================================

    def keyboard_input(self):

        try:

            self.last_input_was_voice = False
            return input("\nYou: ").strip()

        except Exception as e:

            logger.error(f"Keyboard input error: {e}")

            return ""

    # ======================================================
    # COMMAND HANDLER
    # ======================================================

    def handle_command(self, text):

        command = text.lower().strip()

        # High-impact power commands are handled before generic cancellation.
        # Only exact standalone phrases are accepted; sentence mentions pass
        # through to normal conversation.
        power_response = self.shutdown_phrase.handle(text)
        if power_response is not None:
            print("\\nNEXUS: " + power_response)
            if self.command_speaker:
                try:
                    self.command_speaker(power_response)
                except Exception as error:
                    logger.warning("Could not speak power-command response: %s", error)
            return True

        # Return to voice mode

        if command in [
            "voice mode",
            "switch to voice",
            "switch to voice mode",
            "enable voice mode",
            "use voice"
        ]:

            self.mode = "voice"

            print("\nNEXUS: Push-to-Talk mode enabled.")

            logger.info("Switched to Push-to-Talk mode.")

            return True

        # Cancel input

        if command in [
            "cancel",
            "never mind",
            "forget it",
            "stop"
        ]:

            print("\nNEXUS: Cancelled.")

            logger.info("User cancelled input.")

            return True

        return False


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":

    manager = InputManager()

    print("\nNEXUS INPUT MANAGER TEST")
    print("========================")

    try:

        while True:

            text = manager.get_input()

            if text:

                print("\nINPUT:", text)

    except KeyboardInterrupt:

        print("\nInput manager stopped.")
