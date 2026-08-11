"""
NEXUS Wake Word Detector

Dedicated wake-word detection system.

TEST WAKE WORD:
    Hey Jarvis

This will later be replaced with:
    Hey NEXUS
"""

import sys
import time
from pathlib import Path


# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)

if str(PROJECT_ROOT) not in sys.path:

    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


# ==========================================================
# IMPORTS
# ==========================================================

import numpy as np
import sounddevice as sd

from openwakeword.model import Model
from openwakeword.utils import download_models

from utils.logger import setup_logger


logger = setup_logger(__name__)


# ==========================================================
# WAKE WORD DETECTOR
# ==========================================================

class WakeWordDetector:

    def __init__(
        self,
        threshold=0.5
    ):

        logger.info(
            "Initializing wake-word detector..."
        )

        self.sample_rate = 16000

        # 80 ms audio frames
        self.block_size = 1280

        self.threshold = threshold

        # ==================================================
        # DOWNLOAD / VERIFY MODELS
        # ==================================================

        try:

            logger.info(
                "Checking wake-word models..."
            )

            download_models()

        except Exception as e:

            logger.error(
                f"Could not download wake-word models: {e}"
            )

            raise

        # ==================================================
        # LOAD HEY JARVIS MODEL
        # ==================================================

        try:

            logger.info(
                "Loading Hey Jarvis wake-word model..."
            )

            self.model = Model(
                wakeword_models=[
                    "hey_jarvis"
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


    # ======================================================
    # PROCESS AUDIO FRAME
    # ======================================================

    def process_frame(
        self,
        audio
    ):

        """
        Process one microphone frame.

        Input:
            16 kHz mono float32 audio.
        """

        if audio is None:

            return False


        audio = np.asarray(
            audio,
            dtype=np.float32
        )


        audio = np.clip(
            audio,
            -1.0,
            1.0
        )


        # Convert float32 audio
        # to signed 16-bit PCM.

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


        # ==================================================
        # CHECK WAKE-WORD SCORE
        # ==================================================

        for wake_word, score in prediction.items():

            if score >= self.threshold:

                logger.info(
                    f"Wake word detected: "
                    f"{wake_word} "
                    f"(score={score:.2f})"
                )

                return True


        return False


    # ======================================================
    # WAIT FOR WAKE WORD
    # ======================================================

    def wait_for_wake_word(
        self
    ):

        """
        Continuously listen until
        the wake word is detected.
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


                        # Small cooldown to prevent
                        # immediate duplicate detection.

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


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":


    detector = (
        WakeWordDetector()
    )


    print()

    print(
        "======================================"
    )

    print(
        "       NEXUS WAKE WORD TEST"
    )

    print(
        "======================================"
    )

    print()

    print(
        "Current wake word:"
    )

    print(
        "    Hey Jarvis"
    )

    print()

    print(
        "Press Ctrl+C to stop."
    )

    print()


    while True:


        detected = (
            detector.wait_for_wake_word()
        )


        if detected:

            print()

            print(
                "Wake word activated."
            )

            print()
