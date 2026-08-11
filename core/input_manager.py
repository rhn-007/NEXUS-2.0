"""
NEXUS Input Manager

Handles voice and keyboard input modes.

Voice flow:

    Wake Word
        ↓
    Whisper
        ↓
    NEXUS

Keyboard flow:

    Keyboard
        ↓
    NEXUS
"""

from voice.listener import Listener
from voice.wake_word import WakeWordDetector

from utils.logger import setup_logger


logger = setup_logger(__name__)


class InputManager:

    def __init__(self):

        # ==================================================
        # DEFAULT MODE
        # ==================================================

        self.mode = "voice"

        # ==================================================
        # VOICE SYSTEMS
        # ==================================================

        logger.info(
            "Loading voice input systems..."
        )

        self.listener = Listener()

        self.wake_word = WakeWordDetector()

        logger.info(
            "Voice input systems ready."
        )

        logger.info(
            "Input manager initialized in voice mode"
        )


    # ======================================================
    # MAIN INPUT
    # ======================================================

    def get_input(self):

        while True:

            # ==============================================
            # VOICE MODE
            # ==============================================

            if self.mode == "voice":

                text = self.voice_input()


            # ==============================================
            # KEYBOARD MODE
            # ==============================================

            else:

                text = self.keyboard_input()


            # ==============================================
            # EMPTY INPUT
            # ==============================================

            if not text:

                continue


            # ==============================================
            # COMMAND HANDLING
            # ==============================================

            if self.handle_command(text):

                continue


            return text


    # ======================================================
    # VOICE INPUT
    # ======================================================

    def voice_input(self):

        try:

            # ----------------------------------------------
            # WAIT FOR WAKE WORD
            # ----------------------------------------------

            detected = (
                self.wake_word.wait_for_wake_word()
            )


            if not detected:

                return ""


            # ----------------------------------------------
            # WAKE WORD ACTIVATED
            # ----------------------------------------------

            print(
                "\nNEXUS listening..."
            )


            # ----------------------------------------------
            # LISTEN FOR COMMAND
            # ----------------------------------------------

            text = self.listener.listen()


            if text:

                print(
                    f"\nYou: {text}"
                )


            return text


        except Exception as e:

            logger.error(
                f"Voice input error: {e}"
            )

            return ""


    # ======================================================
    # KEYBOARD INPUT
    # ======================================================

    def keyboard_input(self):

        try:

            return input(
                "\nYou: "
            )


        except Exception as e:

            logger.error(
                f"Keyboard input error: {e}"
            )

            return ""


    # ======================================================
    # COMMAND HANDLER
    # ======================================================

    def handle_command(
        self,
        text
    ):

        command = (
            text
            .lower()
            .strip()
        )


        # ==================================================
        # KEYBOARD MODE
        # ==================================================

        keyboard_phrases = [

            "keyboard mode",

            "switch to keyboard",

            "switch to keyboard mode",

            "go to keyboard",

            "use keyboard",

            "turn on keyboard mode",

            "enable keyboard mode"

        ]


        if any(

            phrase in command

            for phrase in keyboard_phrases

        ):

            self.mode = "keyboard"


            print(
                "\nNEXUS: Keyboard mode enabled."
            )


            logger.info(
                "Input mode changed to keyboard."
            )


            return True


        # ==================================================
        # VOICE MODE
        # ==================================================

        voice_phrases = [

            "voice mode",

            "switch to voice",

            "switch to voice mode",

            "go to voice",

            "use voice",

            "turn on voice mode",

            "enable voice mode"

        ]


        if any(

            phrase in command

            for phrase in voice_phrases

        ):

            self.mode = "voice"


            print(
                "\nNEXUS: Voice mode enabled."
            )


            logger.info(
                "Input mode changed to voice."
            )


            return True


        # ==================================================
        # CANCEL
        # ==================================================

        cancel_phrases = [

            "cancel",

            "never mind",

            "forget it",

            "stop"

        ]


        if any(

            phrase in command

            for phrase in cancel_phrases

        ):

            print(
                "\nNEXUS: Cancelled."
            )


            logger.info(
                "User cancelled current input."
            )


            return True


        return False


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":

    manager = InputManager()


    print(
        "\n======================================"
    )

    print(
        "       NEXUS INPUT MANAGER TEST"
    )

    print(
        "======================================"
    )

    print()

    print(
        "Current mode:",
        manager.mode
    )

    print()

    print(
        "Press Ctrl+C to stop."
    )


    try:

        while True:

            text = manager.get_input()


            if text:

                print(
                    "\nINPUT:",
                    text
                )


    except KeyboardInterrupt:

        print(
            "\n\nInput manager stopped."
        )
