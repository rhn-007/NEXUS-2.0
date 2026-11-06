import tempfile
import unittest
from pathlib import Path

from learning.observation import PerformanceObserver


class PerformanceObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "observer.db")
        self.observer = PerformanceObserver(self.db_path)

    def tearDown(self):
        self.observer.close()
        self.temp_dir.cleanup()

    def test_records_operational_event_without_raw_message(self):
        self.observer.record_event(
            "assistant_interaction",
            status="completed",
            duration_ms=1250,
            metadata={"request_type": "conversation", "input_length": 18}
        )
        events = self.observer.get_recent_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "assistant_interaction")
        self.assertEqual(events[0]["metadata"]["request_type"], "conversation")
        self.assertNotIn("content", events[0]["metadata"])

    def test_metrics_group_completed_and_failed_events(self):
        self.observer.record_event("model_generation", "completed", 1000)
        self.observer.record_event("model_generation", "failed", 2000)
        metrics = self.observer.get_metrics()
        self.assertEqual(len(metrics), 2)
        statuses = {item["status"] for item in metrics}
        self.assertEqual(statuses, {"completed", "failed"})

    def test_report_handles_empty_database(self):
        self.assertIn("not have enough", self.observer.get_report())


if __name__ == "__main__":
    unittest.main()
