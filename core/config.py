import os

from dotenv import load_dotenv


load_dotenv()



class Config:


    APP_NAME = "NEXUS"


    VERSION = "2.0"


    DEBUG = (
        os.getenv(
            "DEBUG",
            "False"
        )
        == "True"
    )


    OLLAMA_URL = os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434"
    )
