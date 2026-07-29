import requests

from utils.logger import setup_logger
from core.config import Config


logger = setup_logger(__name__)


class OllamaClient:


    def __init__(self):

        self.url = Config.OLLAMA_URL

        self.model = "llama3"


        logger.info(
            "Ollama client initialized"
        )



    def generate(
        self,
        prompt
    ):

        if not prompt:

            return (
                "Please provide a message."
            )


        try:

            response = requests.post(

                f"{self.url}/api/generate",

                json={

                    "model": self.model,

                    "prompt": prompt,

                    "stream": False

                },

                timeout=120

            )


            response.raise_for_status()


            data = response.json()


            return data.get(
                "response",
                "No response generated."
            )



        except requests.exceptions.Timeout:


            logger.error(
                "Ollama request timed out."
            )


            return (
                "Ollama took too long to respond."
            )



        except Exception as e:


            logger.error(
                f"Ollama error: {e}"
            )


            return (
                "I could not connect to my AI model."
            )
