"""
NEXUS Wake Word Detector

Dedicated low-cost wake-word detection layer.

Current test wake word:
    Hey Jarvis

This will later be replaced with:
    Hey NEXUS
"""

import time

import numpy as np
import sounddevice as sd
import openwakeword

from openwakeword.model import Model

from utils.logger import setup_logger


logger = setup_logger(__name__)


class WakeWordDetector:

    def __init__(
        self,
        threshold=0.5
    ):

        logger.info(
            "Initializing wake-word detector..."
        )

        self.sample_rate = 16000

        # openWakeWord works best with 80 ms frames.
        # 16000 samples/sec * 0.08 sec = 1280 samples.
        self.block_size = 1280

        self.threshold = threshold

        # ------------------------------------------------------
        # Load the pretrained model.
        #
        # IMPORTANT:
        # This currently detects "Hey Jarvis".
        #
        # We will replace this with a custom "Hey NEXUS"
        # model after the pipeline is confirmed working.
        # ------------------------------------------------------

        try:

            model_path = (
                openwakeword.models[
                    "hey_jarvis"
                ][
                    "model_path"
                ]
            )

            self.model = Model(
                wakeword_models=[
                    model_path
                ],
                inference_framework="onnx"
            )

        except Exception as e:

            logger.error(
                f"Could not load wake-word model: {e}"
            )

            raise

        self.detected = False

        logger.info(
            "Wake-word detector ready."
        )

    # ==========================================================
    # PROCESS AUDIO FRAME
    # ==========================================================

    def process_frame(
        self,
        audio
    ):

        """
        Process one microphone frame.

        Audio must be:
            16 kHz
            mono
            16-bit PCM
        """

        if audio is None:

            return False

        # Convert sounddevice float audio
        # into the 16-bit PCM format expected
        # by openWakeWord.
        audio = np.asarray(
            audio,
            dtype=np.float32
        )

        audio = np.clip(
            audio,
            -1.0,
            1.0
        )

        audio = (
            audio * 32767
        ).astype(
            np.int16
        )

        try:

            prediction = (
                self.model.predict(
                    audio
                )
            )

        except Exception as e:

            logger.error(
                f"Wake-word prediction error: {e}"
            )

            return False

        # ------------------------------------------------------
        # Check every loaded wake-word model.
        # ------------------------------------------------------

        for wake_word, score in prediction.items():

            if score >= self.threshold:

                logger.info(
                    f"Wake word detected: "
                    f"{wake_word} "
                    f"(score={score:.2f})"
                )

                return True

        return False

    # ==========================================================
    # WAIT FOR WAKE WORD
    # ==========================================================

    def wait_for_wake_word(
        self
    ):

        """
        Continuously monitor the microphone until
        the wake word is detected.

        Returns:
            True when detected.
        """

        print(
            "\nWaiting for wake word..."
        )

        self.detected = False

        try:

            with sd.InputStream(

                samplerate=self.sample_rate,

                channels=1,

                dtype="float32",

                blocksize=self.block_size

            ) as stream:

                while True:

                    audio, overflowed = (
                        stream.read(
                            self.block_size
                        )
                    )

                    if overflowed:

                        logger.warning(
                            "Microphone buffer overflow."
                        )

                    if self.process_frame(
                        audio.flatten()
                    ):

                        self.detected = True

                        print(
                            "Wake word detected."
                        )

                        # Small cooldown prevents the
                        # same activation from being
                        # detected repeatedly.
                        time.sleep(
                            0.3
                        )

                        return True

        except KeyboardInterrupt:

            return False

        except Exception as e:

            logger.error(
                f"Wake-word microphone error: {e}"
            )

            return False


# ==============================================================
# DIRECT TEST
# ==============================================================

if __name__ == "__main__":

    detector = WakeWordDetector()

    print()
    print(
        "NEXUS Wake Word Test"
    )
    print(
        "Current wake word: Hey Jarvis"
    )
    print(
        "Press Ctrl+C to stop."
    )
    print()

    while True:

        detected = (
            detector.wait_for_wake_word()
        )

        if detected:

            print(
                "Wake word activated."
            )
