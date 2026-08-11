"""
NEXUS Ollama Client

Handles communication with the local Ollama model
and applies the NEXUS personality to every response.
"""

import requests

from utils.logger import setup_logger

from core.response_style import ResponseStyleController


logger = setup_logger(__name__)


class OllamaClient:

    def __init__(self):

        self.url = "http://localhost:11434/api/chat"

        self.model = "llama3"

        self.response_style = ResponseStyleController()

        logger.info(
            "Ollama client ready"
        )

    def generate_response(
        self,
        message,
        context=None
    ):

        try:

            messages = []

            # ==========================
            # NEXUS PERSONALITY
            # ==========================

            messages.append(
                {
                    "role": "system",
                    "content": self.response_style.get_personality_prompt()
                }
            )

            # ==========================
            # MEMORY / CONVERSATION
            # ==========================

            if context:

                if isinstance(context, list):

                    messages.extend(
                        context
                    )

                else:

                    messages.append(
                        {
                            "role": "system",
                            "content": str(context)
                        }
                    )

            # ==========================
            # USER MESSAGE
            # ==========================

            messages.append(
                {
                    "role": "user",
                    "content": message
                }
            )

            # ==========================
            # OLLAMA SETTINGS
            # ==========================

            payload = {

                "model": self.model,

                "messages": messages,

                "stream": False,

                "options": {

                    "temperature": 0.3,

                    "top_p": 0.9

                }

            }

            logger.info(
                "Sending request to Ollama..."
            )

            response = requests.post(

                self.url,

                json=payload,

                timeout=120

            )

            response.raise_for_status()

            data = response.json()

            result = data["message"]["content"].strip()

            # ==========================
            # FINAL RESPONSE CLEANUP
            # ==========================

            result = self.response_style.refine(
                result
            )

            return result

        except Exception as e:

            logger.error(
                f"Ollama error: {e}"
            )

            return (
                f"Ollama error: {e}"
            )
