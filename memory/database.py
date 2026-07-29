"""
NEXUS Memory Database
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


        self.lock = threading.Lock()


        self.create_tables()




    def create_tables(self):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                CREATE TABLE IF NOT EXISTS memories(

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    key TEXT,

                    value TEXT,

                    category TEXT,

                    created_at TEXT

                )
                """

            )


            self.connection.commit()




    def insert(
        self,
        key,
        value,
        category="profile"
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




    def search(
        self,
        key
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT key,value,category

                FROM memories

                WHERE key LIKE ?

                ORDER BY id DESC

                """,

                (

                    f"%{key}%",

                )

            )


            return cursor.fetchall()




    def get_profile(self):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT key,value

                FROM memories

                WHERE category='profile'

                """

            )


            return cursor.fetchall()




    def get_conversations(
        self,
        limit=10
    ):


        with self.lock:


            cursor = self.connection.cursor()


            cursor.execute(

                """
                SELECT key,value

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
