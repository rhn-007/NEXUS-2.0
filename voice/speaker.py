"""
NEXUS Voice Speaker

Handles text-to-speech using Piper.
"""

import subprocess
import uuid
from pathlib import Path
import winsound

from utils.logger import setup_logger


logger = setup_logger(__name__)


class Speaker:

    def __init__(self):

        self.piper = Path(
            "piper/piper.exe"
        )

        self.model = Path(
            "voice/models/en_GB-alan-medium.onnx"
        )

        logger.info(
            "Voice system ready"
        )

    # ==========================================================
    # PRONUNCIATION
    # ==========================================================

    def fix_pronunciation(
        self,
        text
    ):

        replacements = {

            # Rohan
            "Rohan": "Row-han",
            "rohan": "Row-han",
            "ROHAN": "Row-han",

            # NEXUS
            "NEXUS": "Nexus",
            "Nexus": "Nexus",
            "nexus": "Nexus",

            # Python
            "Python": "Pie-thon",
            "python": "Pie-thon"

        }

        for word, replacement in replacements.items():

            text = text.replace(
                word,
                replacement
            )

        return text

    # ==========================================================
    # SPEAK
    # ==========================================================

    def speak(
        self,
        text
    ):

        if not text:

            return

        text = str(text).strip()

        if not text:

            return

        # Fix pronunciation
        text = self.fix_pronunciation(
            text
        )

        output = None

        try:

            # --------------------------------------------------
            # Temporary WAV filename
            # --------------------------------------------------

            filename = (
                f"voice_{uuid.uuid4().hex}.wav"
            )

            output = Path(
                filename
            )

            # --------------------------------------------------
            # Piper configuration
            # --------------------------------------------------

            command = [

                str(self.piper),

                "--model",
                str(self.model),

                "--output_file",
                str(output),

                # Slightly slower speech gives the voice
                # more natural pacing.
                "--length_scale",
                "1.00",

                # Higher variation makes the voice less
                # flat and robotic.
                "--noise_scale",
                "0.22",

                "--noise_w",
                "0.35",

                # Natural pause between sentences.
                "--sentence_silence",
                "0.18"

            ]

            # --------------------------------------------------
            # Generate speech
            # --------------------------------------------------

            subprocess.run(

                command,

                input=text,

                text=True,

                check=True,

                stdout=subprocess.DEVNULL,

                stderr=subprocess.DEVNULL

            )

            # --------------------------------------------------
            # Play speech
            # --------------------------------------------------

            if output.exists():

                winsound.PlaySound(

                    str(output),

                    winsound.SND_FILENAME

                )

        except Exception as e:

            logger.error(
                f"Voice error: {e}"
            )

        finally:

            # --------------------------------------------------
            # Delete temporary audio file
            # --------------------------------------------------

            try:

                if output and output.exists():

                    output.unlink()

            except Exception as e:

                logger.warning(
                    f"Could not remove temporary voice file: {e}"
                )
