import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from core.action_history import ActionHistory
from core.conversation import ConversationManager
from learning.knowledge_engine import KnowledgeEngine
from learning.observation import PerformanceObserver
from learning.personal_language import PersonalLanguageLearner
from memory.database import MemoryDatabase
from research.store import ResearchStore


class SQLiteConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "shared.db")

        # These are the seven independent connections NEXUS opens against
        # its shared database (MemoryDatabase is used by memory and knowledge).
        self.memory = MemoryDatabase(self.database_path)
        self.knowledge = KnowledgeEngine(self.database_path)
        self.conversation = ConversationManager(self.database_path)
        self.observer = PerformanceObserver(self.database_path)
        self.language = PersonalLanguageLearner(self.database_path)
        self.actions = ActionHistory(self.database_path)
        self.research = ResearchStore(self.database_path)

    def tearDown(self):
        for component in (
            self.research,
            self.actions,
            self.language,
            self.observer,
            self.conversation,
            self.knowledge,
            self.memory,
        ):
            component.close()
        self.temp_dir.cleanup()

    def test_every_component_uses_wal_and_a_30_second_busy_timeout(self):
        connections = (
            self.memory.connection,
            self.knowledge.db.connection,
            self.conversation.connection,
            self.observer.connection,
            self.language.connection,
            self.actions.connection,
            self.research.connection,
        )

        for connection in connections:
            with self.subTest(connection=connection):
                journal_mode = connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]
                busy_timeout = connection.execute(
                    "PRAGMA busy_timeout"
                ).fetchone()[0]

                self.assertEqual(journal_mode.lower(), "wal")
                self.assertEqual(busy_timeout, 30000)

    def test_seven_connections_can_write_concurrently(self):
        worker_count = 7
        write_count = 15
        start = threading.Barrier(worker_count)

        def write_memory():
            start.wait(timeout=10)
            for index in range(write_count):
                self.memory.insert(
                    f"memory-{index}", f"value-{index}"
                )

        def write_knowledge():
            start.wait(timeout=10)
            for index in range(write_count):
                self.knowledge.save_knowledge(
                    topic="concurrency",
                    title=f"Knowledge {index}",
                    content=f"Unique knowledge content {index}",
                )

        def write_conversation():
            start.wait(timeout=10)
            for index in range(write_count):
                self.conversation.add_user_message(
                    f"Message {index}"
                )

        def write_observation():
            start.wait(timeout=10)
            for index in range(write_count):
                self.observer.record_event(
                    "concurrency_test",
                    metadata={"index": index},
                )

        def write_language():
            start.wait(timeout=10)
            for index in range(write_count):
                self.language.add_correction(
                    f"heard {index}", f"intended {index}"
                )

        def write_actions():
            start.wait(timeout=10)
            for index in range(write_count):
                self.actions.record(
                    f"request {index}", "test", f"command {index}",
                    True, "ok"
                )

        def write_research():
            start.wait(timeout=10)
            for index in range(write_count):
                session_id = self.research.create_session(
                    "concurrency", f"Research {index}"
                )
                self.research.finish_session(
                    session_id, f"Summary {index}"
                )

        workers = (
            write_memory,
            write_knowledge,
            write_conversation,
            write_observation,
            write_language,
            write_actions,
            write_research,
        )

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker) for worker in workers]
            for future in futures:
                future.result(timeout=30)

        self.assertEqual(len(self.memory.search("memory-")), write_count)
        self.assertEqual(
            len(self.knowledge.search("Unique knowledge content")), write_count
        )
        self.assertEqual(
            len(self.conversation.get_recent_transcript(write_count)),
            write_count,
        )
        self.assertEqual(
            len(self.observer.get_recent_events(limit=write_count)),
            write_count,
        )
        self.assertEqual(len(self.language.get_corrections()), write_count)
        self.assertEqual(len(self.actions.recent(write_count)), write_count)
        sessions = self.research.connection.execute(
            "SELECT COUNT(*) FROM research_sessions"
        ).fetchone()[0]
        self.assertEqual(sessions, write_count)


if __name__ == "__main__":
    unittest.main()
