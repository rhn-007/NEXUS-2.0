"""
NEXUS Voice Speaker

Handles text-to-speech using Piper.
"""

import html
import re
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

        # Long written answers should not be read aloud in full.
        self.long_text_word_limit = 120
        self.long_text_char_limit = 750
        self.spoken_summary_word_limit = 85

        logger.info(
            "Voice system ready"
        )

    # ==========================================================
    # TEXT CLEANING
    # ==========================================================

    def clean_for_speech(self, text):
        """
        Convert Markdown-heavy written text into readable speech text.
        The original response is not modified.
        """

        text = html.unescape(str(text))

        # Remove fenced code blocks completely.
        text = re.sub(
            r"```[\s\S]*?```",
            " ",
            text
        )

        # Keep the visible label of Markdown links, not their URL.
        text = re.sub(
            r"!?\[([^\]]+)\]\((?:[^()]|\([^()]*\))*\)",
            r"\1",
            text
        )

        # Remove bare web addresses and email addresses.
        text = re.sub(
            r"https?://\S+|www\.\S+",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Remove common citation markers used in research reports.
        text = re.sub(
            r"\(\s*SOURCE\s*\d+(?:\s*,\s*SOURCE\s*\d+)*\s*\)",
            " ",
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            r"\[\s*SOURCE\s*\d+\s*\]",
            " ",
            text,
            flags=re.IGNORECASE
        )

        # Ignore a bibliography/source list when speaking.
        text = re.split(
            r"(?im)^\s{0,3}(?:#{1,6}\s*)?(?:sources|references|bibliography)\s*:?\s*$",
            text,
            maxsplit=1
        )[0]

        # Remove Markdown heading and quote prefixes.
        text = re.sub(
            r"(?m)^\s{0,3}#{1,6}\s*",
            "",
            text
        )
        text = re.sub(
            r"(?m)^\s*>+\s?",
            "",
            text
        )

        # Remove table separator rows. Convert remaining table cells
        # into a simple spoken list rather than reading pipe symbols.
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.fullmatch(r"[\s|:-]+", stripped):
                continue
            if "|" in stripped:
                cells = [
                    cell.strip()
                    for cell in stripped.strip("|").split("|")
                    if cell.strip()
                ]
                if cells:
                    lines.append(". ".join(cells) + ".")
                continue
            lines.append(stripped)

        text = " ".join(lines)

        # Keep the words in bold, italic, and inline-code spans.
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
        text = re.sub(r"(?<!_)_(?!_)(.*?)_(?!_)", r"\1", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)

        # Remove leftover Markdown punctuation and decorative bullets.
        text = re.sub(r"[*_~#|]+", " ", text)
        text = re.sub(r"(?m)^\s*[-+]\s+", "", text)
        text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)

        # Normalize whitespace and punctuation spacing.
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)

        return text.strip()

    # ==========================================================
    # SPOKEN VERSION SELECTION
    # ==========================================================

    def prepare_spoken_text(self, text):
        """
        Select a concise spoken version for long responses while
        leaving the full written response untouched.
        """

        cleaned = self.clean_for_speech(text)

        if not cleaned:
            return ""

        words = cleaned.split()

        is_long = (
            len(words) > self.long_text_word_limit
            or len(cleaned) > self.long_text_char_limit
        )

        if not is_long:
            return cleaned

        # Prefer a dedicated summary/conclusion section in reports.
        summary_match = re.search(
            r"(?is)(?:^|\s)(?:summary|key takeaway|conclusion|overall summary)\s*:?\s*(.*)$",
            cleaned
        )

        if summary_match:
            summary = self.clean_for_speech(
                summary_match.group(1)
            )
            if summary:
                summary_words = summary.split()
                if len(summary_words) > self.spoken_summary_word_limit:
                    summary = " ".join(
                        summary_words[:self.spoken_summary_word_limit]
                    ).rstrip(" ,;:")
                    summary += "."
                return (
                    summary
                    + " The full response is displayed on screen."
                )

        # Otherwise speak the opening sentences, which normally contain
        # the direct answer, rather than reading the entire report.
        sentences = re.split(
            r"(?<=[.!?])\s+",
            cleaned
        )

        selected = []
        selected_words = 0

        for sentence in sentences:
            sentence_words = sentence.split()
            if not sentence_words:
                continue
            if selected_words + len(sentence_words) > 65:
                break
            selected.append(sentence)
            selected_words += len(sentence_words)
            if selected_words >= 45:
                break

        spoken = " ".join(selected).strip()

        if not spoken:
            spoken = " ".join(words[:65]).rstrip(" ,;:") + "."

        return (
            spoken
            + " The full response is displayed on screen."
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

        # Prepare a speech-only version. The original response remains
        # unchanged for the terminal, conversation history, and memory.
        text = self.prepare_spoken_text(text)

        if not text:
            return

        text = self.fix_pronunciation(text)

        output = None

        try:

            filename = (
                f"voice_{uuid.uuid4().hex}.wav"
            )

            output = Path(
                filename
            )

            command = [

                str(self.piper),

                "--model",
                str(self.model),

                "--output_file",
                str(output),

                "--length_scale",
                "1.00",

                "--noise_scale",
                "0.22",

                "--noise_w",
                "0.35",

                "--sentence_silence",
                "0.18"

            ]

            subprocess.run(

                command,

                input=text,

                text=True,

                check=True,

                stdout=subprocess.DEVNULL,

                stderr=subprocess.DEVNULL

            )

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

            try:

                if output and output.exists():

                    output.unlink()

            except Exception as e:

                logger.warning(
                    f"Could not remove temporary voice file: {e}"
                )
