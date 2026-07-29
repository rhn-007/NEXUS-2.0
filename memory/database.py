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





    def search(

        self,

        keyword

    ):


        with self.lock:


            cursor = self.connection.cursor()



            cursor.execute(

                """

                SELECT key,value,category

                FROM memories

                WHERE value LIKE ?

                OR key LIKE ?

                ORDER BY id DESC

                """,

                (

                    f"%{keyword}%",

                    f"%{keyword}%"

                )

            )


            return cursor.fetchall()





    def get_all(self):


        cursor = self.connection.cursor()


        cursor.execute(

            """

            SELECT key,value,category

            FROM memories

            ORDER BY id

            """

        )


        return cursor.fetchall()
