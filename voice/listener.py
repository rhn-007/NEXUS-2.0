"""
NEXUS Speech Recognition System
Faster-Whisper Listener
"""

from faster_whisper import WhisperModel

import sounddevice as sd
import scipy.io.wavfile as wav

from pathlib import Path
import tempfile

from utils.logger import setup_logger


logger = setup_logger(__name__)


class Listener:

    def __init__(self):

        print("Loading Whisper model...")

        self.model = WhisperModel(
            "medium.en",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=1
        )

        print("Listener ready.")

    def record_audio(
        self,
        duration=5,
        samplerate=16000
    ):

        print("\nListening...")

        audio = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=1,
            dtype="float32"
        )

        sd.wait()

        print("Processing...")

        return audio.flatten()

    def transcribe(
        self,
        audio,
        samplerate=16000
    ):

        temp_file = (
            Path(tempfile.gettempdir())
            / "nexus_audio.wav"
        )

        wav.write(
            temp_file,
            samplerate,
            audio
        )

        try:

            segments, info = self.model.transcribe(
                str(temp_file),
                beam_size=5,
                language="en",
                vad_filter=True
            )

            text = ""

            for segment in segments:

                text += segment.text + " "

            text = text.strip()

            text = self.fix_transcription(
                text
            )

            return text

        finally:

            try:

                if temp_file.exists():

                    temp_file.unlink()

            except Exception:

                pass

    def fix_transcription(
        self,
        text
    ):

        """
        Correct common Whisper transcription mistakes.

        In particular, Whisper can sometimes hear
        'NEXUS' as 'Lexus', 'Lexis', etc.
        """

        if not text:

            return text

        # Normalize spacing

        text = " ".join(
            text.split()
        )

        # ==========================
        # Common NEXUS misrecognitions
        # ==========================

        nexus_replacements = {

            "lexus": "NEXUS",
            "lexis": "NEXUS",
            "nex us": "NEXUS",
            "next us": "NEXUS",
            "nextus": "NEXUS",
            "nexis": "NEXUS",
            "nexus": "NEXUS"

        }

        # ==========================
        # Other common corrections
        # ==========================

        replacements = {

            "rohan": "Rohan",
            "rowan": "Rohan",
            "rohanh": "Rohan",

            "ollama": "Ollama",
            "python": "Python"

        }

        # ==========================
        # Apply corrections
        # ==========================

        words = text.split()

        corrected_words = []

        for word in words:

            clean_word = word.strip(
                ".,!?;:\"'()[]{}"
            )

            punctuation_before = ""

            punctuation_after = ""

            # Preserve punctuation before word

            if (
                word
                and word[0] in ".,!?;:\"'()[]{}"
            ):

                punctuation_before = word[0]

            # Preserve punctuation after word

            if (
                word
                and word[-1] in ".,!?;:\"'()[]{}"
            ):

                punctuation_after = word[-1]

            lookup = clean_word.lower()

            if lookup in nexus_replacements:

                replacement = nexus_replacements[
                    lookup
                ]

            elif lookup in replacements:

                replacement = replacements[
                    lookup
                ]

            else:

                replacement = clean_word

            corrected_words.append(
                punctuation_before
                + replacement
                + punctuation_after
            )

        text = " ".join(
            corrected_words
        )

        return text

    def listen(self):

        audio = self.record_audio()

        text = self.transcribe(
            audio
        )

        return text


if __name__ == "__main__":

    listener = Listener()

    while True:

        text = listener.listen()

        print(
            "\nYou said:",
            text
        )
