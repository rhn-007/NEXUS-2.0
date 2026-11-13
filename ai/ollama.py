"""
NEXUS Ollama Client

Handles communication with the local Ollama model.
"""

import json
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

# Default local model used by NEXUS conversations and dependent features.
DEFAULT_MODEL = "qwen2.5:7b"


def get_keep_alive():

    return (
        os.environ.get("NEXUS_OLLAMA_KEEP_ALIVE", "").strip()
        or DEFAULT_KEEP_ALIVE
    )


# What generate_response returns when the model could not answer.
FAILURE_PREFIXES = (
    "ollama error",
    "ollama returned",
    "ollama took too long",
    "ollama request error",
    "i can't connect to ollama"
)


def is_failure(reply):
    """True when the text is one of the client's own error messages."""

    return str(reply or "").lower().startswith(FAILURE_PREFIXES)


def streaming_enabled():
    """Show the reply as it is written. NEXUS_STREAM=0 turns it off."""

    return os.environ.get("NEXUS_STREAM", "").strip().lower() not in (
        "0", "false", "no", "off"
    )


def model_options():
    """
    Settings sent to Ollama. NEXUS_NUM_THREAD and NEXUS_NUM_GPU are only
    sent when set to a whole number, so by default Ollama decides.
    """

    options = {"temperature": 0.3, "top_p": 0.9}

    for variable, key in (
        ("NEXUS_NUM_THREAD", "num_thread"),
        ("NEXUS_NUM_GPU", "num_gpu")
    ):

        value = os.environ.get(variable, "").strip()

        if value.isdigit():
            options[key] = int(value)

    return options


# What the model is shown of the conversation. Everything stays stored in
# full; this only decides how much of an old, long message is sent along.
# Set NEXUS_FULL_HISTORY=1 to send every message in full again.
RECENT_FULL_MESSAGES = 6
OLD_MESSAGE_MAX_CHARS = 1200
OLD_MESSAGE_KEEP_CHARS = 500

# Older messages (beyond the recent ones) are sent newest first until this
# many characters are used; anything older is left out of the model's view.
OLD_HISTORY_BUDGET_CHARS = 3000


def compact_history(
    messages,
    keep_recent=RECENT_FULL_MESSAGES,
    max_chars=OLD_MESSAGE_MAX_CHARS,
    keep_chars=OLD_MESSAGE_KEEP_CHARS,
    old_budget=OLD_HISTORY_BUDGET_CHARS
):
    """
    Shorten old, long user and assistant messages for the model.

    The most recent messages are always sent in full, and so are short
    older ones, system messages and reference material. Returns the new
    list (the input is never changed) and counts of what was shortened.
    """

    info = {"shortened": 0, "chars_saved": 0, "dropped": 0}

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

    # Keep the newest older messages within the budget, drop the rest.
    if old_budget and old_budget > 0:

        older = [
            index for index, item in enumerate(result)
            if item.get("role") in ("user", "assistant")
            and index not in recent
        ]

        used = 0
        drop = set()

        for index in reversed(older):

            used += len(str(result[index].get("content", "")))

            if used > old_budget or drop:
                drop.add(index)

        if drop:

            info["dropped"] = len(drop)
            info["chars_saved"] += sum(
                len(str(messages[index].get("content", "")))
                for index in drop
            )

            result = [
                item for index, item in enumerate(result)
                if index not in drop
            ]

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


def read_stream(response, on_text):
    """
    Read Ollama's streamed reply and return it shaped like a normal
    (non-streamed) response. on_text gets each piece as it arrives. If the
    stream breaks after some text arrived, the text so far is returned.
    """

    parts = []
    final = {}
    incomplete = False

    try:

        for line in response.iter_lines():

            if not line:
                continue

            chunk = json.loads(line)

            if chunk.get("error"):
                raise ValueError(str(chunk["error"]))

            piece = (chunk.get("message") or {}).get("content", "")

            if piece:

                parts.append(piece)

                try:
                    on_text(piece)
                except Exception as error:
                    logger.warning("Streaming display error: %s", error)

            if chunk.get("done"):
                final = chunk

    except (ValueError, requests.exceptions.RequestException) as error:

        if not parts:
            raise

        logger.warning("Stream ended early, keeping the text so far: %s", error)

        incomplete = True

    data = {key: value for key, value in final.items() if key != "message"}

    # A reply that was cut off must not be mistaken for a finished one.
    data["incomplete"] = incomplete or not final

    data["message"] = {"role": "assistant", "content": "".join(parts)}

    return data


def placement_text(models, name):
    """Where Ollama says the model is running: CPU, GPU or a mix."""

    for item in models or []:

        if name not in (item.get("name"), item.get("model")):
            continue

        size = item.get("size") or 0
        vram = item.get("size_vram") or 0

        if size <= 0:
            return None

        if vram <= 0:
            return "100% CPU"

        share = round(vram * 100 / size)

        if share >= 100:
            return "100% GPU"

        return f"{100 - share}% CPU / {share}% GPU"

    return None


class OllamaClient:

    def __init__(self, observer=None):

        self.url = "http://localhost:11434/api/chat"

        self.model = DEFAULT_MODEL

        self.response_style = ResponseStyleController()
        self.observer = observer

        # Measurements from the most recent request.
        self.last_stats = {}

        self._placement_logged = False

        logger.info(
            "Ollama client ready"
        )

    def _log_placement(self):
        """Log once whether the model runs on the CPU, the GPU or both."""

        if self._placement_logged:
            return

        self._placement_logged = True

        try:

            reply = requests.get(
                self.url.replace("/api/chat", "/api/ps"),
                timeout=2
            )

            where = placement_text(
                reply.json().get("models"),
                self.model
            )

            if where:
                logger.info("Ollama is running %s on: %s", self.model, where)

        except Exception:
            pass

    def generate_response(self, message, context=None, on_text=None):
        """
        on_text, when given, is called with each piece of the reply as the
        model writes it. The finished reply is still returned whole.
        """

        self.last_stats = {}
        started_at = time.perf_counter()
        result = self._generate_response(message, context, on_text)
        duration_ms = (time.perf_counter() - started_at) * 1000

        if self.observer:
            status = (
                "failed"
                if is_failure(result)
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
        context=None,
        on_text=None
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

            streaming = bool(on_text) and streaming_enabled()

            payload = {

                "model": self.model,

                "messages": messages,

                "stream": streaming,

                "keep_alive": get_keep_alive(),

                "options": model_options()

            }

            response = requests.post(

                self.url,

                json=payload,

                timeout=120,

                stream=streaming

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

            if streaming:

                data = read_stream(response, on_text)


            else:

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

            if data.get("incomplete"):
                self.last_stats["incomplete"] = True

            self.last_stats["history_shortened"] = history_info["shortened"]
            self.last_stats["history_dropped"] = history_info["dropped"]
            self.last_stats["history_chars_saved"] = history_info["chars_saved"]

            logger.info(
                f"Ollama timing: {format_stats(self.last_stats)} "
                f"({self.last_stats.get('messages_sent', 0)} messages, "
                f"{self.last_stats.get('prompt_chars', 0)} characters, "
                f"{history_info['shortened']} older shortened, "
                f"{history_info['dropped']} left out)"
            )

            self._log_placement()

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
