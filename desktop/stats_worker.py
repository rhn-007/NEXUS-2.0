"""Polls real PC statistics on a background thread (reading CPU load takes
about half a second, so it must never run on the UI thread)."""

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from desktop import system_stats


class StatsWorker(QObject):
    updated = Signal(dict)

    def __init__(self, interval_ms=3000):
        super().__init__()
        self._interval = interval_ms
        self._timer = None
        self._reader = None

    @Slot()
    def start(self):
        # Created here so the timer and the reader belong to the worker thread.
        from tools.system_info import SystemReader

        self._reader = SystemReader()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(self._interval)
        self.poll()

    @Slot()
    def poll(self):
        self.updated.emit(system_stats.collect(self._reader))
