"""Run the existing NEXUS assistant away from the Qt UI thread.

The worker lives on its own QThread. Everything slow (loading models, thinking,
speaking, recording and transcribing) happens here; the UI only receives
signals. The assistant itself is not modified: the worker calls its public
methods (process_input, speaker.speak through the assistant, the listener's
push-to-talk recording) and observes Piper playback through the optional
`playback_hook` on the speaker.
"""

from PySide6.QtCore import QObject, Signal, Slot

from desktop.audio_levels import rms_level, wav_envelope


class AssistantWorker(QObject):
    ready = Signal()
    response = Signal(str)
    state_changed = Signal(str)
    failed = Signal(str)
    stopped = Signal()

    # Added for the full desktop interface.
    user_text = Signal(str)               # what the microphone heard
    busy_changed = Signal(bool)           # a request is being handled
    recording_changed = Signal(bool)      # push-to-talk recording on / off
    speech_started = Signal(object, float)  # loudness envelope, seconds per step
    speech_ended = Signal()

    def __init__(self):
        super().__init__()
        self.assistant = None
        self._recording = False
        self._busy = False

    # ------------------------------------------------------------------
    # Start-up
    # ------------------------------------------------------------------

    @Slot()
    def initialize(self):
        try:
            from core.assistant import NexusAssistant
            self.assistant = NexusAssistant()
            self.assistant.speaker.playback_hook = self._on_playback
            self.ready.emit()
        except Exception as error:
            self.failed.emit(f"Could not initialize NEXUS: {error}")

    # ------------------------------------------------------------------
    # Typed commands
    # ------------------------------------------------------------------

    @Slot(str)
    def process_command(self, command):
        if self.assistant is None:
            self.failed.emit("NEXUS is still initializing.")
            return
        command = str(command or "").strip()
        if not command:
            return
        self._set_busy(True)
        try:
            self._mark_input_source(voice=False)
            self._run_command(command)
        finally:
            self._set_busy(False)

    def _run_command(self, command):
        try:
            self.state_changed.emit("thinking")
            result = self.assistant.process_input(command)
            self.response.emit(str(result or ""))
            self.state_changed.emit("idle")
        except Exception as error:
            self.state_changed.emit("error")
            self.failed.emit(str(error))

    def _mark_input_source(self, voice):
        manager = getattr(self.assistant, "input_manager", None)
        if manager is not None:
            manager.last_input_was_voice = bool(voice)

    # ------------------------------------------------------------------
    # Push-to-talk
    # ------------------------------------------------------------------

    @Slot()
    def start_listening(self):
        """Begin recording from the microphone (mic button or Space held)."""
        if self.assistant is None or self._recording or self._busy:
            return
        try:
            self.assistant.input_manager.listener.start_recording()
        except Exception as error:
            self.failed.emit(f"Could not start the microphone: {error}")
            return
        self._recording = True
        self.recording_changed.emit(True)

    @Slot()
    def stop_listening(self):
        """Stop recording, transcribe, then handle the text like a typed command."""
        if self.assistant is None or not self._recording:
            return
        self._recording = False
        self.recording_changed.emit(False)
        self._set_busy(True)
        try:
            try:
                text = self.assistant.input_manager.listener.stop_recording()
            except Exception as error:
                self.failed.emit(f"Could not transcribe the recording: {error}")
                return
            text = str(text or "").strip()
            if not text:
                return
            self.user_text.emit(text)
            self._mark_input_source(voice=True)
            self._run_command(text)
        finally:
            self._set_busy(False)

    def mic_level(self):
        """
        Loudness (0..1) of the most recent microphone chunk. Safe to call from
        the UI thread: it only reads the listener's latest recorded chunk
        while holding the listener's own lock.
        """
        if not self._recording or self.assistant is None:
            return 0.0
        listener = self.assistant.input_manager.listener
        try:
            with listener.audio_lock:
                frames = listener.audio_frames
                chunk = frames[-1].copy() if frames else None
        except Exception:
            return 0.0
        return rms_level(chunk)

    # ------------------------------------------------------------------
    # Piper playback
    # ------------------------------------------------------------------

    def _on_playback(self, event, path):
        """Called on this thread by the speaker around each spoken reply."""
        if event == "start":
            levels, hop = wav_envelope(path)
            self.speech_started.emit(levels, float(hop))
        else:
            self.speech_ended.emit()

    # ------------------------------------------------------------------
    # Helpers and shutdown
    # ------------------------------------------------------------------

    def _set_busy(self, busy):
        if busy != self._busy:
            self._busy = busy
            self.busy_changed.emit(busy)

    @Slot()
    def shutdown(self):
        try:
            if self.assistant is not None:
                self.assistant.speaker.playback_hook = None
                self.assistant.shutdown()
                self.assistant = None
        finally:
            self.stopped.emit()
