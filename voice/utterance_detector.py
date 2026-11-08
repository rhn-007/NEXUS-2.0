"""
NEXUS Utterance Detector

Finds spoken sentences in a live stream of microphone audio so that NEXUS
can listen continuously without a push-to-talk key.

It uses the loudness (RMS) of short audio frames:

1. The first moments of audio are used to measure the background noise.
2. Speech starts when the sound stays clearly louder than that noise.
3. Speech ends after a period of quiet.
4. Very short sounds (clicks, coughs, keyboard noise) are discarded.

The detector only finds where speech starts and stops. Whether the audio
really contains words is decided afterwards by Faster-Whisper, which also
applies its own voice-activity filter.

Tuning values are arguments of UtteranceDetector.__init__.
"""

from collections import deque

import numpy as np


class UtteranceDetector:

    def __init__(
        self,
        samplerate=16000,
        frame_ms=30,
        calibration_ms=300,
        pre_roll_ms=300,
        start_ms=90,
        end_silence_s=1.0,
        min_speech_s=0.4,
        max_utterance_s=30.0,
        trailing_silence_s=0.3,
        threshold_multiplier=3.0,
        min_threshold=0.01
    ):

        self.samplerate = samplerate

        self.frame_size = int(samplerate * frame_ms / 1000)
        self.frame_seconds = self.frame_size / samplerate

        self.calibration_frames = max(
            1, round(calibration_ms / frame_ms)
        )
        self.pre_roll_frames = max(
            1, round(pre_roll_ms / frame_ms)
        )
        self.start_frames = max(
            1, round(start_ms / frame_ms)
        )
        self.end_silence_frames = max(
            1, round(end_silence_s / self.frame_seconds)
        )
        self.max_frames = max(
            1, round(max_utterance_s / self.frame_seconds)
        )
        self.trailing_frames = max(
            0, round(trailing_silence_s / self.frame_seconds)
        )

        self.min_speech_s = min_speech_s
        self.threshold_multiplier = threshold_multiplier
        self.min_threshold = min_threshold

        self.reset()

    # ======================================================
    # STATE
    # ======================================================

    def reset(self):
        """Forget everything, including the measured background noise."""

        self._pending = np.zeros(0, dtype=np.float32)
        self._calibration_rms = []
        self.noise_floor = None

        self._pre_roll = deque(maxlen=self.pre_roll_frames)
        self._reset_utterance()

    def _reset_utterance(self):

        self._pre_roll.clear()
        self._voiced_run = 0
        self._frames = []
        self._in_speech = False
        self._speech_frames = 0
        self._silence_run = 0

    @property
    def threshold(self):
        """Loudness above which a frame counts as speech."""

        floor = self.noise_floor or 0.0

        return max(
            self.min_threshold,
            floor * self.threshold_multiplier
        )

    @property
    def in_speech(self):

        return self._in_speech

    # ======================================================
    # FEED AUDIO
    # ======================================================

    def feed(self, samples):
        """
        Add mono float32 audio of any length.

        Returns the audio of one finished utterance as a numpy array,
        or None when no utterance has finished yet.
        """

        samples = np.asarray(
            samples,
            dtype=np.float32
        ).reshape(-1)

        self._pending = np.concatenate(
            (self._pending, samples)
        )

        while len(self._pending) >= self.frame_size:

            frame = self._pending[:self.frame_size]
            self._pending = self._pending[self.frame_size:]

            utterance = self._process_frame(frame)

            if utterance is not None:
                return utterance

        return None

    # ======================================================
    # FRAME PROCESSING
    # ======================================================

    def _process_frame(self, frame):

        rms = float(
            np.sqrt(np.mean(np.square(frame)))
        )

        # Measure the background noise before listening for speech.

        if self.noise_floor is None:

            self._calibration_rms.append(rms)
            self._pre_roll.append(frame)

            if len(self._calibration_rms) >= self.calibration_frames:

                self.noise_floor = float(
                    np.median(self._calibration_rms)
                )

            return None

        voiced = rms > self.threshold

        if not self._in_speech:

            if not voiced:

                # Follow slow changes in background noise.

                self.noise_floor = (
                    0.98 * self.noise_floor
                    + 0.02 * rms
                )

                self._pre_roll.append(frame)
                self._voiced_run = 0

                return None

            self._voiced_run += 1
            self._pre_roll.append(frame)

            if self._voiced_run >= self.start_frames:

                self._in_speech = True
                self._frames = list(self._pre_roll)
                self._speech_frames = self._voiced_run
                self._silence_run = 0

            return None

        self._frames.append(frame)

        if voiced:

            self._speech_frames += 1
            self._silence_run = 0

        else:

            self._silence_run += 1

        if (
            self._silence_run >= self.end_silence_frames
            or len(self._frames) >= self.max_frames
        ):

            return self._finish()

        return None

    def _finish(self):

        speech_seconds = self._speech_frames * self.frame_seconds

        frames = self._frames

        # Keep a short tail of silence, not the whole waiting period.

        trim = max(0, self._silence_run - self.trailing_frames)

        if trim:
            frames = frames[:-trim]

        self._reset_utterance()

        if speech_seconds < self.min_speech_s:
            return None

        return np.concatenate(frames)
