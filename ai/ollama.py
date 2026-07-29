import requests

from utils.logger import setup_logger
from core.config import Config


logger = setup_logger(__name__)



class OllamaClient:


    def __init__(self):

        self.url = Config.OLLAMA_URL

        self.model = Config.OLLAMA_MODEL


        logger.info(
            "Ollama client ready"
        )



    def generate(
        self,
        messages
    ):

        try:

            prompt = self._format_messages(
                messages
            )


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
                ""
            )


        except Exception as e:

            logger.error(
                f"Ollama error: {e}"
            )


            return (
                "I am unable to reach my AI model right now."
            )



    def _format_messages(
        self,
        messages
    ):

        text = ""


        for message in messages:

            role = message["role"]

            content = message["content"]


            text += (
                f"{role}: {content}\n"
            )


        text += "\nassistant:"


        return text
