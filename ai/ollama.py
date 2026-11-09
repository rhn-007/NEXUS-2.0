"""
NEXUS Ollama Client

Handles communication with the local Ollama model.
"""

import os
import time

import requests

from utils.logger import setup_logger
from ai.prompts import SYSTEM_PROMPT
from core.response_style import ResponseStyleController


logger = setup_logger(__name__)


# How long Ollama keeps the model loaded after a request. Ollama's own
# default is 5 minutes, after which the next request pays a reload delay.
# Override with the NEXUS_OLLAMA_KEEP_ALIVE environment variable.
DEFAULT_KEEP_ALIVE = "30m"


def get_keep_alive():

    return (
        os.environ.get("NEXUS_OLLAMA_KEEP_ALIVE", "").strip()
        or DEFAULT_KEEP_ALIVE
    )


# What the model is shown of the conversation. Everything stays stored in
# full; this only decides how much of an old, long message is sent along.
# Set NEXUS_FULL_HISTORY=1 to send every message in full again.
RECENT_FULL_MESSAGES = 6
OLD_MESSAGE_MAX_CHARS = 1200
OLD_MESSAGE_KEEP_CHARS = 500


def compact_history(
    messages,
    keep_recent=RECENT_FULL_MESSAGES,
    max_chars=OLD_MESSAGE_MAX_CHARS,
    keep_chars=OLD_MESSAGE_KEEP_CHARS
):
    """
    Shorten old, long user and assistant messages for the model.

    The most recent messages are always sent in full, and so are short
    older ones, system messages and reference material. Returns the new
    list (the input is never changed) and counts of what was shortened.
    """

    info = {"shortened": 0, "chars_saved": 0}

    if os.environ.get("NEXUS_FULL_HISTORY", "").strip().lower() in (
        "1", "true", "yes"
    ):
        return list(messages), info

    conversation = [
        index for index, item in enumerate(messages)
        if item.get("role") in ("user", "assistant")
    ]

    recent = set(conversation[-keep_recent:]) if keep_recent > 0 else set()

    result = []

    for index, item in enumerate(messages):

        content = str(item.get("content", ""))

        if (
            item.get("role") in ("user", "assistant")
            and index not in recent
            and len(content) > max_chars
        ):

            cut = content[:keep_chars]

            if " " in cut:
                cut = cut.rsplit(" ", 1)[0]

            shortened = (
                cut.rstrip()
                + " ... (the rest of this older message is shortened here)"
            )

            info["shortened"] += 1
            info["chars_saved"] += len(content) - len(shortened)

            result.append({**item, "content": shortened})

        else:

            result.append(item)

    return result, info


def extract_stats(data, messages):
    """
    Collect timing and size measurements for one model request.

    Ollama reports durations in nanoseconds. Only numbers are returned,
    never any message text.
    """

    def milliseconds(key):

        value = data.get(key)

        if isinstance(value, (int, float)):
            return round(value / 1_000_000, 1)

        return None

    stats = {
        "messages_sent": len(messages),
        "prompt_chars": sum(
            len(str(item.get("content", "")))
            for item in messages
        ),
        "load_ms": milliseconds("load_duration"),
        "prompt_tokens": data.get("prompt_eval_count"),
        "prompt_eval_ms": milliseconds("prompt_eval_duration"),
        "generated_tokens": data.get("eval_count"),
        "generation_ms": milliseconds("eval_duration"),
        "ollama_total_ms": milliseconds("total_duration")
    }

    return {
        key: value
        for key, value in stats.items()
        if value is not None
    }


def format_stats(stats):
    """One readable log line for the measurements above."""

    parts = []

    if "load_ms" in stats:
        parts.append(f"load {stats['load_ms'] / 1000:.1f}s")

    if "prompt_tokens" in stats:
        prompt = f"prompt {stats['prompt_tokens']} tokens"
        if "prompt_eval_ms" in stats:
            prompt += f" in {stats['prompt_eval_ms'] / 1000:.1f}s"
        parts.append(prompt)

    if "generated_tokens" in stats:
        generated = f"generated {stats['generated_tokens']} tokens"
        if "generation_ms" in stats:
            generated += f" in {stats['generation_ms'] / 1000:.1f}s"
        parts.append(generated)

    if "ollama_total_ms" in stats:
        parts.append(f"total {stats['ollama_total_ms'] / 1000:.1f}s")

    return " | ".join(parts)


class OllamaClient:

    def __init__(self, observer=None):

        self.url = "http://localhost:11434/api/chat"

        self.model = "qwen2.5:3b"

        self.response_style = ResponseStyleController()
        self.observer = observer

        # Measurements from the most recent request.
        self.last_stats = {}

        logger.info(
            "Ollama client ready"
        )

    def generate_response(self, message, context=None):
        self.last_stats = {}
        started_at = time.perf_counter()
        result = self._generate_response(message, context)
        duration_ms = (time.perf_counter() - started_at) * 1000

        if self.observer:
            lowered = str(result or "").lower()
            failed_prefixes = (
                "ollama error",
                "ollama returned",
                "ollama took too long",
                "i can't connect to ollama"
            )
            status = (
                "failed"
                if lowered.startswith(failed_prefixes)
                else "completed"
            )
            try:
                self.observer.record_event(
                    event_type="model_generation",
                    status=status,
                    duration_ms=duration_ms,
                    metadata={
                        "model": self.model,
                        "input_length": len(str(message)),
                        "output_length": len(str(result or "")),
                        **self.last_stats
                    }
                )
            except Exception as error:
                logger.warning("Could not record model metrics: %s", error)

        return result

    def _generate_response(
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

            # The assistant records the user's message in the
            # conversation before building the context, so it is usually
            # already the last context entry. Only add it when missing,
            # otherwise the model would receive it twice.

            current_message = {
                "role": "user",
                "content": str(message)
            }

            if messages[-1] != current_message:

                messages.append(
                    current_message
                )

            # ==========================
            # WHAT THE MODEL SEES
            # ==========================

            # Old long messages are shortened for the model only. The
            # conversation itself is stored and kept in full.

            messages, history_info = compact_history(messages)

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

                "keep_alive": get_keep_alive(),

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

            # ==========================
            # TIMING MEASUREMENTS
            # ==========================

            self.last_stats = extract_stats(
                data,
                messages
            )

            self.last_stats["history_shortened"] = history_info["shortened"]
            self.last_stats["history_chars_saved"] = history_info["chars_saved"]

            logger.info(
                f"Ollama timing: {format_stats(self.last_stats)} "
                f"({self.last_stats.get('messages_sent', 0)} messages, "
                f"{self.last_stats.get('prompt_chars', 0)} characters, "
                f"{history_info['shortened']} older shortened)"
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
