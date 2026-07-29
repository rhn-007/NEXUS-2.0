import sqlite3
from datetime import datetime


class MemoryDatabase:


    def __init__(
        self,
        path="nexus_memory.db"
    ):

        self.connection = sqlite3.connect(
            path,
            check_same_thread=False
        )

        self.create_tables()



    def create_tables(self):

        cursor = self.connection.cursor()


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                key TEXT NOT NULL,

                value TEXT NOT NULL,

                type TEXT NOT NULL,

                created_at TEXT

            )
            """
        )


        self.connection.commit()




    # =====================================
    # INSERT MEMORY
    # =====================================

    def insert(
        self,
        key,
        value,
        memory_type="fact"
    ):


        cursor = self.connection.cursor()


        cursor.execute(
            """
            INSERT INTO memories
            (key, value, type, created_at)

            VALUES (?, ?, ?, ?)

            """,

            (
                key,
                value,
                memory_type,
                datetime.now().isoformat()
            )

        )


        self.connection.commit()




    # =====================================
    # SEARCH MEMORY
    # =====================================

    def search(
        self,
        keyword
    ):


        cursor = self.connection.cursor()


        cursor.execute(
            """
            SELECT key, value, type
            FROM memories

            WHERE key LIKE ?
            OR value LIKE ?

            ORDER BY id ASC

            """,

            (
                f"%{keyword}%",
                f"%{keyword}%"
            )

        )


        return cursor.fetchall()




    # =====================================
    # GET ALL FACTS
    # =====================================

    def get_facts(self):


        cursor = self.connection.cursor()


        cursor.execute(
            """
            SELECT key, value
            FROM memories

            WHERE type='fact'

            """

        )


        return cursor.fetchall()




    # =====================================
    # GET RECENT CONVERSATIONS
    # =====================================

    def get_conversations(
        self,
        limit=10
    ):


        cursor = self.connection.cursor()


        cursor.execute(
            """
            SELECT key, value
            FROM memories

            WHERE type='conversation'

            ORDER BY id DESC

            LIMIT ?

            """,

            (
                limit,
            )

        )


        return cursor.fetchall()
