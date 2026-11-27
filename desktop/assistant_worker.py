"""Run NEXUS core work away from the Qt UI thread."""
from PySide6.QtCore import QObject, Signal, Slot


class AssistantWorker(QObject):
    ready = Signal()
    response = Signal(str)
    state_changed = Signal(str)
    failed = Signal(str)
    snapshot_ready = Signal(str, object)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.assistant = None
        self._ptt_recording = False

    @Slot()
    def initialize(self):
        try:
            from core.assistant import NexusAssistant
            self.assistant = NexusAssistant()
            self.ready.emit()
        except Exception as error:
            self.failed.emit(f"Could not initialize NEXUS: {error}")

    @Slot(str)
    def process_command(self, command):
        if self.assistant is None:
            self.failed.emit("NEXUS is still initializing.")
            return
        command = str(command or "").strip()
        if not command:
            return
        try:
            self.state_changed.emit("thinking")
            result = self.assistant.process_input(command)
            self.response.emit(str(result or ""))
            self.state_changed.emit("idle")
        except Exception as error:
            self.state_changed.emit("error")
            self.failed.emit(str(error))

    @Slot(str)
    def load_snapshot(self, section):
        """Read existing memory, knowledge and research data without mutating it."""
        if self.assistant is None:
            self.snapshot_ready.emit(section, {"error": "NEXUS is not ready."})
            return
        try:
            if section == "memory":
                rows = self.assistant.memory.get_memory_context()
                payload = {"facts": [
                    {"key": str(row[0]), "value": str(row[1])}
                    for row in rows
                ]}
            elif section == "knowledge":
                payload = {"items": self.assistant.knowledge.get_all_knowledge(100)}
            elif section == "research":
                from desktop.research_service import ResearchService
                service = ResearchService()
                payload = {
                    "sessions": service.list_sessions(),
                    "topics": service.list_topic_knowledge(),
                }
            elif section.startswith("research_detail:"):
                from desktop.research_service import ResearchService
                session_id = section.split(":", 1)[1]
                payload = {"session": ResearchService().get_session(session_id)}
            elif section == "settings":
                from ai.ollama import DEFAULT_MODEL
                payload = {
                    "model": str(DEFAULT_MODEL),
                    "voice": str(getattr(self.assistant.speaker, "model", "Unknown")),
                    "speech_speed": str(getattr(self.assistant.speaker, "speech_length_scale", "Unknown")),
                    "input_mode": str(getattr(self.assistant.input_manager, "mode", "Unknown")),
                    "database": "nexus_memory.db",
                }
            else:
                payload = {}
            self.snapshot_ready.emit(section, payload)
        except Exception as error:
            self.snapshot_ready.emit(section, {"error": str(error)})

    @Slot()
    def start_voice_capture(self):
        """Start a desktop hold-to-talk recording using the existing Whisper listener."""
        if self.assistant is None:
            self.failed.emit("NEXUS is still initializing.")
            return
        if self._ptt_recording:
            return
        try:
            input_manager = self.assistant.input_manager
            input_manager.mode = "voice"
            input_manager.listener.start_recording()
            self._ptt_recording = True
            self.state_changed.emit("listening")
        except Exception as error:
            self._ptt_recording = False
            self.state_changed.emit("error")
            self.failed.emit(f"Could not start microphone recording: {error}")

    @Slot()
    def stop_voice_capture(self):
        """Stop the current recording, transcribe it, and process the result."""
        if self.assistant is None or not self._ptt_recording:
            return
        self._ptt_recording = False
        try:
            self.state_changed.emit("thinking")
            text = self.assistant.input_manager.listener.stop_recording()
            text = str(text or "").strip()
            if text:
                self.process_command(text)
            else:
                self.state_changed.emit("idle")
        except Exception as error:
            self.state_changed.emit("error")
            self.failed.emit(f"Could not process the voice recording: {error}")

    @Slot()
    def shutdown(self):
        try:
            if self.assistant is not None:
                if self._ptt_recording:
                    self._ptt_recording = False
                    try:
                        self.assistant.input_manager.listener.stop_recording()
                    except Exception:
                        pass
                self.assistant.shutdown()
                self.assistant = None
        finally:
            self.stopped.emit()
