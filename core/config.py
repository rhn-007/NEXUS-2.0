import os

from dotenv import load_dotenv


load_dotenv()



class Config:

    APP_NAME = "NEXUS"

    VERSION = "2.0"


    OLLAMA_URL = os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434"
    )


    OLLAMA_MODEL = os.getenv(
        "OLLAMA_MODEL",
        "llama3"
    )


    MEMORY_DB = os.getenv(
        "MEMORY_DB",
        "nexus_memory.db"
    )
