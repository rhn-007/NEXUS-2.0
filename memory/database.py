"""
NEXUS Memory Database

Handles persistent storage.

Stores:
- User memories
- Conversations
"""

import sqlite3
import threading
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

        self.lock = threading.RLock()

        self.create_tables()



    # ==========================================
    # CREATE TABLES
    # ==========================================

    def create_tables(self):

        with self.lock:

            cursor = self.connection.cursor()


            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    key TEXT NOT NULL,

                    value TEXT NOT NULL,

                    category TEXT DEFAULT 'general',

                    created_at TEXT

                )
                """
            )


            self.connection.commit()



    # ==========================================
    # INSERT MEMORY
    # ==========================================

    def insert(
        self,
        key,
        value,
        category="general"
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                INSERT INTO memories
                (
                    key,
                    value,
                    category,
                    created_at
                )

                VALUES (?,?,?,?)

                """,

                (
                    key,
                    value,
                    category,
                    datetime.now().isoformat()
                )

            )


            self.connection.commit()



    # ==========================================
    # SEARCH MEMORY
    # ==========================================

    def search(
        self,
        key
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT
                    key,
                    value,
                    category

                FROM memories

                WHERE key LIKE ?

                ORDER BY id DESC

                """,

                (
                    f"%{key}%",
                )

            )


            return cursor.fetchall()



    # ==========================================
    # GET CONVERSATIONS
    # ==========================================

    def get_conversations(
        self,
        limit=10
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT
                    key,
                    value

                FROM memories

                WHERE category='conversation'

                ORDER BY id DESC

                LIMIT ?

                """,

                (
                    limit,
                )

            )


            return cursor.fetchall()



    # ==========================================
    # GET FACTS
    # ==========================================

    def get_facts(
        self
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT
                    key,
                    value

                FROM memories

                WHERE category!='conversation'

                ORDER BY id DESC

                """

            )


            return cursor.fetchall()
