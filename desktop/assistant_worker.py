"""Run the existing NEXUS assistant away from the Qt UI thread."""

from PySide6.QtCore import QObject, Signal, Slot


class AssistantWorker(QObject):
    ready = Signal()
    response = Signal(str)
    state_changed = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.assistant = None

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

    @Slot()
    def shutdown(self):
        if self.assistant is not None:
            try:
                self.assistant.shutdown()
            finally:
                self.assistant = None
