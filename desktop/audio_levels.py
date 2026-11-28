"""Real audio levels for the orb: microphone chunks and Piper WAV output.

The microphone level comes from the chunk the Listener most recently
recorded. The speech level comes from the WAV file Piper just produced: its
loudness is measured in short slices before playback and then followed in time
while the sound plays. Nothing is random.
"""

import wave

import numpy as np


def rms_level(samples, floor=0.004, ceiling=0.20):
    """Loudness of a float audio chunk (-1..1) as 0..1; quiet room -> ~0."""

    if samples is None:
        return 0.0

    data = np.asarray(samples, dtype=np.float32).reshape(-1)

    if data.size == 0:
        return 0.0

    rms = float(np.sqrt(np.mean(np.square(data))))

    level = (rms - floor) / (ceiling - floor)

    return float(min(1.0, max(0.0, level)) ** 0.6)


def wav_envelope(path, hop_seconds=0.03):
    """
    Measure a WAV file's loudness in slices of `hop_seconds`.

    Returns (levels, hop_seconds) where levels is a float32 array of 0..1
    values, or (None, hop_seconds) if the file cannot be read.
    Levels are relative to the file's own loud passages, so quiet voices still
    move the orb and loud ones do not clip.
    """

    try:

        with wave.open(str(path), "rb") as handle:

            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())

    except (OSError, EOFError, wave.Error):

        return None, hop_seconds

    if width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        return None, hop_seconds

    if channels > 1:
        usable = (samples.size // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    hop = max(1, int(rate * hop_seconds))

    slices = samples.size // hop

    if slices == 0:
        return None, hop_seconds

    blocks = samples[:slices * hop].reshape(slices, hop)

    rms = np.sqrt(np.mean(np.square(blocks), axis=1))

    reference = max(float(np.percentile(rms, 95)), 0.02)

    levels = np.clip(rms / reference, 0.0, 1.0) ** 0.8

    return levels.astype(np.float32), hop / float(rate)


def envelope_at(levels, hop_seconds, elapsed):
    """Level of an envelope at `elapsed` seconds after playback began."""

    if levels is None or hop_seconds <= 0 or elapsed < 0:
        return 0.0

    index = int(elapsed / hop_seconds)

    if index >= len(levels):
        return 0.0

    return float(levels[index])
