
"""
NEXUS Input Manager

Handles Push-to-Talk voice input and keyboard mode.

Voice mode:
    Hold SPACE  -> Start recording
    Release     -> Stop recording and transcribe
    Press ESC   -> Switch to keyboard mode

Keyboard mode:
    Type normally
    Type "voice mode" -> Return to Push-to-Talk
"""

from pynput import keyboard
from voice.listener import Listener
from utils.logger import setup_logger
from threading import Event

logger = setup_logger(__name__)


class InputManager:

    def __init__(self):

        self.mode = "voice"

        logger.info("Loading voice input system...")

        self.listener = Listener()

        self.recording = False
        self.completed = Event()
        self.recorded_text = ""
        self.keyboard_listener = None

        logger.info("Push-to-Talk input manager initialized.")

    # ======================================================
    # MAIN INPUT
    # ======================================================

    def get_input(self):

        while True:

            if self.mode == "voice":

                text = self.voice_input()

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

        print("\nHold SPACE to speak. Release to send.")
        print("Press ESC to switch to keyboard mode.")

        def on_press(key):

            if key == keyboard.Key.esc:

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

            if key == keyboard.Key.space and not self.recording:

                try:

                    self.listener.start_recording()

                    self.recording = True

                    print("\nNEXUS listening...")

                except Exception as e:

                    logger.error(f"Recording start error: {e}")

                    self.completed.set()

                    return False

        def on_release(key):

            if key == keyboard.Key.space and self.recording:

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

            if self.mode == "keyboard":

                print("\nNEXUS: Keyboard mode enabled.")

                logger.info("Switched to keyboard mode.")

                return ""

            text = self.recorded_text.strip()

            if text:

                print(f"\nYou: {text}")

            return text

        except Exception as e:

            logger.error(f"Push-to-Talk error: {e}")

            return ""

        finally:

            if self.keyboard_listener:

                self.keyboard_listener.stop()

            self.recording = False

    # ======================================================
    # KEYBOARD INPUT
    # ======================================================

    def keyboard_input(self):

        try:

            return input("\nYou: ").strip()

        except Exception as e:

            logger.error(f"Keyboard input error: {e}")

            return ""

    # ======================================================
    # COMMAND HANDLER
    # ======================================================

    def handle_command(self, text):

        command = text.lower().strip()

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
