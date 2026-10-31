
"""
NEXUS Speech Recognition System
Faster-Whisper Listener with Push-to-Talk Recording
"""

from faster_whisper import WhisperModel

import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np

from pathlib import Path
import tempfile
import uuid
import threading

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

        self.samplerate = 16000
        self.audio_frames = []
        self.stream = None
        self.audio_lock = threading.Lock()

        print("Listener ready.")

    # ======================================================
    # START RECORDING
    # ======================================================

    def start_recording(self):

        with self.audio_lock:

            if self.stream is not None:

                return

            self.audio_frames = []

        def audio_callback(indata, frames, time, status):

            if status:

                logger.warning(f"Audio status: {status}")

            with self.audio_lock:

                self.audio_frames.append(
                    indata.copy()
                )

        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=audio_callback
        )

        self.stream.start()

    # ======================================================
    # STOP RECORDING
    # ======================================================

    def stop_recording(self):

        if self.stream is None:

            return ""

        stream = self.stream
        self.stream = None

        stream.stop()
        stream.close()

        with self.audio_lock:

            if not self.audio_frames:

                return ""

            audio = np.concatenate(
                self.audio_frames,
                axis=0
            ).flatten()

            self.audio_frames = []

        if len(audio) < int(self.samplerate * 0.3):

            print("Recording too short.")

            return ""

        print("Transcribing...")

        return self.transcribe(
            audio,
            self.samplerate
        )

    # ======================================================
    # TRANSCRIBE AUDIO
    # ======================================================

    def transcribe(
        self,
        audio,
        samplerate=16000
    ):

        temp_file = (
            Path(tempfile.gettempdir())
            / f"nexus_audio_{uuid.uuid4().hex}.wav"
        )

        try:

            wav.write(
                temp_file,
                samplerate,
                audio.astype(np.float32)
            )

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

            return self.fix_transcription(text)

        except Exception as e:

            logger.error(f"Transcription error: {e}")

            return ""

        finally:

            try:

                if temp_file.exists():

                    temp_file.unlink()

            except Exception:

                pass

    # ======================================================
    # TRANSCRIPTION CORRECTIONS
    # ======================================================

    def fix_transcription(self, text):

        if not text:

            return text

        text = " ".join(
            text.split()
        )

        nexus_replacements = {

            "lexus": "NEXUS",
            "lexis": "NEXUS",
            "nex us": "NEXUS",
            "next us": "NEXUS",
            "nextus": "NEXUS",
            "nexis": "NEXUS",
            "nexus": "NEXUS"

        }

        replacements = {

            "rohan": "Rohan",
            "rowan": "Rohan",
            "rohanh": "Rohan",

            "ollama": "Ollama",
            "python": "Python",
            "Oprah": "Opera",
            "What's up": "Whatsapp"

        }

        words = text.split()

        corrected_words = []

        for word in words:

            clean_word = word.strip(
                ".,!?;:\"'()[]{}"
            )

            punctuation_before = ""
            punctuation_after = ""

            if (
                word
                and word[0] in ".,!?;:\"'()[]{}"
            ):

                punctuation_before = word[0]

            if (
                word
                and word[-1] in ".,!?;:\"'()[]{}"
            ):

                punctuation_after = word[-1]

            lookup = clean_word.lower()

            if lookup in nexus_replacements:

                replacement = nexus_replacements[lookup]

            elif lookup in replacements:

                replacement = replacements[lookup]

            else:

                replacement = clean_word

            corrected_words.append(
                punctuation_before
                + replacement
                + punctuation_after
            )

        return " ".join(corrected_words)

    # ======================================================
    # LEGACY FIXED-DURATION RECORDING
    # ======================================================

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

    # ======================================================
    # LEGACY LISTEN METHOD
    # ======================================================

    def listen(self):

        audio = self.record_audio()

        return self.transcribe(
            audio,
            self.samplerate
        )


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":

    listener = Listener()

    print("\nNEXUS LISTENER TEST")
    print("===================")

    while True:

        input("\nPress ENTER to record for 5 seconds...")

        text = listener.listen()

        print("\nYou said:", text)
