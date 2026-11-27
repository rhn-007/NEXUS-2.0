"""
NEXUS Ollama Client

Handles communication with the local Ollama model.
"""

import requests

from utils.logger import setup_logger
from ai.prompts import SYSTEM_PROMPT
from core.response_style import ResponseStyleController


logger = setup_logger(__name__)


class OllamaClient:

    def __init__(self):

        self.url = "http://localhost:11434/api/chat"

        self.model = "qwen2.5:3b"

        self.response_style = ResponseStyleController()
        self._model_used = False

        logger.info(
            "Ollama client ready"
        )

    def unload_model(self):
        """
        Ask Ollama to unload the model used by this NEXUS session.

        This unloads the model only; it does not stop the Ollama server.
        Note that Ollama does not track which application owns a model, so
        another application using this same model may also be affected.
        """

        if not self._model_used:
            return

        try:
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "messages": [],
                    "stream": False,
                    "keep_alive": 0
                },
                timeout=5
            )
            response.raise_for_status()
            self._model_used = False
            logger.info(
                "Unloaded Ollama model %s. Ollama server remains running.",
                self.model
            )

        except requests.exceptions.RequestException as error:
            logger.warning("Could not unload Ollama model %s: %s", self.model, error)

        except Exception as error:
            logger.warning("Unexpected error while unloading Ollama model: %s", error)

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
                    "content": SYSTEM_PROMPT
                }
            )

            # ==========================
            # CONVERSATION CONTEXT
            # ==========================

            if context:

                if isinstance(context, list):

                    for item in context:

                        # Only accept properly structured
                        # conversation messages.

                        if not isinstance(item, dict):

                            continue

                        role = item.get("role")

                        content = item.get("content")

                        if role not in [
                            "system",
                            "user",
                            "assistant"
                        ]:

                            continue

                        if not content:

                            continue

                        messages.append(
                            {
                                "role": role,
                                "content": str(content)
                            }
                        )

                elif isinstance(context, str):

                    messages.append(
                        {
                            "role": "system",
                            "content": context
                        }
                    )

            # ==========================
            # CURRENT USER MESSAGE
            # ==========================

            messages.append(
                {
                    "role": "user",
                    "content": str(message)
                }
            )

            # ==========================
            # DEBUG
            # ==========================

            logger.info(
                f"Sending {len(messages)} messages to Ollama..."
            )

            # ==========================
            # OLLAMA REQUEST
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

            self._model_used = True

            response = requests.post(

                self.url,

                json=payload,

                timeout=120

            )

            # ==========================
            # DETAILED ERROR REPORTING
            # ==========================

            if not response.ok:

                logger.error(
                    f"Ollama HTTP {response.status_code}"
                )

                logger.error(
                    f"Ollama response: {response.text}"
                )

                return (
                    f"Ollama error "
                    f"(HTTP {response.status_code})"
                )

            # ==========================
            # PARSE RESPONSE
            # ==========================

            data = response.json()

            if "message" not in data:

                logger.error(
                    f"Unexpected Ollama response: {data}"
                )

                return (
                    "Ollama returned an invalid response."
                )

            result = data["message"].get(
                "content",
                ""
            )

            result = result.strip()

            if not result:

                logger.error(
                    f"Ollama returned empty response: {data}"
                )

                return (
                    "Ollama returned an empty response."
                )

            # ==========================
            # FINAL RESPONSE CLEANUP
            # ==========================

            result = self.response_style.refine(
                result
            )

            return result

        except requests.exceptions.Timeout:

            logger.error(
                "Ollama request timed out."
            )

            return (
                "Ollama took too long to respond."
            )

        except requests.exceptions.ConnectionError:

            logger.error(
                "Could not connect to Ollama."
            )

            return (
                "I can't connect to Ollama."
            )

        except requests.exceptions.RequestException as e:

            logger.error(
                f"Ollama request error: {e}"
            )

            return (
                f"Ollama request error: {e}"
            )

        except Exception as e:

            logger.error(
                f"Ollama error: {e}"
            )

            return (
                f"Ollama error: {e}"
            )
