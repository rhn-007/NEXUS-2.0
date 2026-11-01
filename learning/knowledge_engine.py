from memory.database import MemoryDatabase


class KnowledgeEngine:
    def __init__(self, database_path="nexus_memory.db"):
        self.db = MemoryDatabase(database_path)

    def save_knowledge(
        self,
        topic,
        title,
        content,
        source_url=None,
        source_name=None,
        confidence=0.0,
        verification_status="unverified",
        tags=None
    ):
        if not topic or not title or not content:
            raise ValueError(
                "Topic, title, and content are required."
            )

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "Confidence must be between 0.0 and 1.0."
            )

        knowledge_id = self.db.insert_knowledge(
            topic=topic,
            title=title,
            content=content,
            source_url=source_url,
            source_name=source_name,
            confidence=confidence,
            verification_status=verification_status,
            tags=tags
        )

        if knowledge_id is not None:
            self.db.record_learning_activity(
                activity="knowledge_saved",
                topic=topic,
                details=f"Saved: {title}",
                status="completed"
            )

        return knowledge_id

    def search(self, keyword, limit=20):
        return self.db.search_knowledge(
            keyword,
            limit
        )

    def get_knowledge(self, knowledge_id):
        return self.db.get_knowledge(knowledge_id)

    def get_all_knowledge(self, limit=100):
        return self.db.get_all_knowledge(limit)

    def update_verification(
        self,
        knowledge_id,
        verification_status,
        confidence=None
    ):
        updated = self.db.update_knowledge_status(
            knowledge_id,
            verification_status,
            confidence
        )

        if updated:
            self.db.record_learning_activity(
                activity="knowledge_verification_updated",
                details=(
                    f"Knowledge ID {knowledge_id}: "
                    f"{verification_status}"
                ),
                status="completed"
            )

        return updated

    def record_activity(
        self,
        activity,
        topic=None,
        details=None,
        status="completed"
    ):
        return self.db.record_learning_activity(
            activity=activity,
            topic=topic,
            details=details,
            status=status
        )

    def get_learning_history(self, limit=50):
        return self.db.get_learning_history(limit)

    def close(self):
        self.db.close()
