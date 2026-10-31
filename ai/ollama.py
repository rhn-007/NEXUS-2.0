"""Client for communicating with the local Ollama model."""

import requests

from utils.logger import setup_logger
from ai.prompts import SYSTEM_PROMPT


logger = setup_logger(__name__)


class OllamaClient:
    def __init__(self):
        self.url = "http://localhost:11434/api/chat"
        self.model = "qwen2.5:3b"
        logger.info("Ollama client ready")

    def generate_response(self, message, context=None):
        try:
            messages = []
            has_system_prompt = False

            if isinstance(context, list):
                for item in context:
                    if not isinstance(item, dict):
                        continue

                    role = item.get("role")
                    content = item.get("content")

                    if role not in ("system", "user", "assistant") or not content:
                        continue

                    if role == "system":
                        if has_system_prompt:
                            continue
                        has_system_prompt = True

                    messages.append({
                        "role": role,
                        "content": str(content)
                    })

            elif isinstance(context, str) and context.strip():
                messages.append({
                    "role": "system",
                    "content": SYSTEM_PROMPT + "\n\n" + context
                })
                has_system_prompt = True

            if not has_system_prompt:
                messages.insert(0, {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                })

            # The assistant normally adds the current user message to its
            # conversation history before calling this method. Do not append
            # it a second time.
            last_message_is_current = (
                len(messages) > 1
                and messages[-1].get("role") == "user"
                and messages[-1].get("content") == str(message)
            )

            if not last_message_is_current:
                messages.append({
                    "role": "user",
                    "content": str(message)
                })

            logger.info("Sending %s messages to Ollama...", len(messages))

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9
                }
            }

            response = requests.post(
                self.url,
                json=payload,
                timeout=120
            )

            if not response.ok:
                logger.error(
                    "Ollama HTTP %s: %s",
                    response.status_code,
                    response.text
                )
                return f"Ollama error (HTTP {response.status_code})"

            data = response.json()
            result = data.get("message", {}).get("content", "").strip()

            if not result:
                logger.error("Ollama returned an empty or invalid response: %s", data)
                return "Ollama returned an empty response."

            return result

        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out.")
            return "Ollama took too long to respond."

        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to Ollama.")
            return "I can't connect to Ollama."

        except requests.exceptions.RequestException as error:
            logger.error("Ollama request error: %s", error)
            return f"Ollama request error: {error}"

        except Exception as error:
            logger.error("Ollama error: %s", error)
            return f"Ollama error: {error}"
