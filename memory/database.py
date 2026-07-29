import sqlite3


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

                category TEXT

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

        cursor = self.connection.cursor()


        cursor.execute(

            """
            INSERT INTO memories
            (key,value,category)

            VALUES (?,?,?)

            """,

            (
                key,
                value,
                category
            )

        )


        self.connection.commit()



    def search(
        self,
        key
    ):

        cursor = self.connection.cursor()


        cursor.execute(

            """
            SELECT key,value,category
            FROM memories
            WHERE key LIKE ?

            """,

            (
                f"%{key}%",

            )

        )


        return cursor.fetchall()
