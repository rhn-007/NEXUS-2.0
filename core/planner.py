"""
NEXUS Intent Planner

For requests the fast path cannot read, asks the local model what Rohan
wants and in which steps. The model can only choose from a fixed list of
actions, and every choice is checked before anything runs. It never
produces commands that are executed directly.
"""

import json
import re
import time
from dataclasses import dataclass, field

import requests

from ai.ollama import get_keep_alive
from core.intent import BUILTIN_COMMANDS, Step
from utils.logger import setup_logger


logger = setup_logger(__name__)


MAX_STEPS = 3
MAX_VALUE_LENGTH = 150
HISTORY_MESSAGES = 4
HISTORY_CHARACTERS = 160
PLANNER_TIMEOUT_SECONDS = 40

MODES = ("voice", "keyboard", "continuous")

ACTION_HELP = {
    "open_browser": "open the web browser (value: empty)",
    "open_website": "open a website (value: a known site name or a full URL)",
    "web_search": "search Google for something (value: the search words)",
    "research": "research a topic in depth from several web sources, "
                "takes a minute or two (value: the topic)",
    "open_app": "open an app or folder (value: its name)",
    "calculate": "do arithmetic (value: the expression, for example 12*7)",
    "show_speech_profile": "show what NEXUS learned about how Rohan speaks "
                           "(value: empty)",
    "forget_speech_profile": "erase the speech profile (value: empty)",
    "performance_report": "show NEXUS's own performance report (value: empty)",
    "about_me": "tell Rohan what NEXUS knows about him (value: empty)",
    "switch_mode": "change how Rohan talks to NEXUS (value: voice, keyboard "
                   "or continuous)"
}

ACTIONS = tuple(ACTION_HELP)


@dataclass
class Plan:
    kind: str = "chat"          # chat | act | ask
    steps: list = field(default_factory=list)
    question: str = ""
    planner_ms: float = 0.0
    valid: bool = True


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["chat", "act", "ask"]},
        "steps": {
            "type": "array",
            "maxItems": MAX_STEPS,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "value": {"type": "string"}
                },
                "required": ["action", "value"]
            }
        },
        "question": {"type": "string"}
    },
    "required": ["decision", "steps", "question"]
}


_URL = re.compile(r"^https?://[^\s]+$")

_DOMAIN = re.compile(
    r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|ai|edu|gov|co|dev|"
    r"app|me|tv|uk)(?:/\S*)?$"
)

_EXPRESSION = re.compile(r"^[\d\s+\-*/%().]+$")


class IntentPlanner:

    def __init__(
        self,
        url,
        model,
        websites=None,
        app_names=None,
        app_checker=None
    ):

        self.url = url
        self.model = model
        self.websites = sorted(str(site).lower() for site in (websites or []))
        self.app_names = sorted(str(name).lower() for name in (app_names or []))
        self.app_checker = app_checker or (
            lambda name: name.lower() in self.app_names
        )

    # ======================================================
    # PROMPT
    # ======================================================

    def build_messages(self, text, recent=None):

        actions = "\n".join(
            f"- {name}: {description}"
            for name, description in ACTION_HELP.items()
        )

        system = (
            "You are the action planner for NEXUS, a personal assistant on "
            "Rohan's Windows PC. Work out what Rohan wants. Reply with JSON "
            "only.\n"
            "decision: \"chat\" if he is just talking or asking a question; "
            "\"act\" if he wants something done using the actions below; "
            "\"ask\" if he wants an action but a detail is missing, with one "
            "short question in \"question\".\n"
            f"Actions:\n{actions}\n"
            f"Known apps and folders: {', '.join(self.app_names) or 'none'}.\n"
            f"Known websites: {', '.join(self.websites) or 'none'}.\n"
            f"Use at most {MAX_STEPS} steps, in the order to do them. Use the "
            "recent conversation to understand words like \"it\" or \"that\". "
            "For chat, use no steps. Never invent actions or apps."
        )

        lines = []

        for item in self._recent_items(text, recent):

            who = "Rohan" if item["role"] == "user" else "NEXUS"
            lines.append(f"{who}: {item['content']}")

        history = "\n".join(lines) or "(none)"

        user = (
            f"Recent conversation:\n{history}\n\n"
            f"Rohan now says: {str(text).strip()[:400]}"
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

    def _recent_items(self, text, recent):

        items = []

        for item in recent or []:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = str(item.get("content") or "").strip()

            if role not in ("user", "assistant") or not content:
                continue

            content = re.sub(r"\s+", " ", content)

            items.append({
                "role": role,
                "content": content[:HISTORY_CHARACTERS]
            })

        # The assistant records the current message before planning.
        current = re.sub(r"\s+", " ", str(text).strip())[:HISTORY_CHARACTERS]

        if items and items[-1]["role"] == "user" and (
            items[-1]["content"] == current
        ):
            items.pop()

        return items[-HISTORY_MESSAGES:]

    # ======================================================
    # MODEL CALL
    # ======================================================

    def _call_model(self, messages, response_format):

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": response_format,
            "keep_alive": get_keep_alive(),
            "options": {"temperature": 0, "num_predict": 160}
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=PLANNER_TIMEOUT_SECONDS
        )

        if not response.ok:
            return None

        return response.json().get("message", {}).get("content", "")

    def plan(self, text, recent=None):
        """Always returns a Plan. Any failure means plain conversation."""

        started = time.perf_counter()

        try:

            messages = self.build_messages(text, recent)

            content = self._call_model(messages, RESPONSE_SCHEMA)

            if content is None:
                # Older Ollama versions only accept the plain "json" format.
                content = self._call_model(messages, "json")

            plan = self.parse(content)

        except Exception as error:

            logger.warning("Planner failed: %s", error)

            plan = Plan(valid=False)

        plan.planner_ms = round((time.perf_counter() - started) * 1000, 1)

        logger.info(
            "Planner: %s, %d step(s), %.1fs",
            plan.kind,
            len(plan.steps),
            plan.planner_ms / 1000
        )

        return plan

    # ======================================================
    # CHECKING THE MODEL'S ANSWER
    # ======================================================

    def parse(self, content):

        try:
            data = json.loads(content or "")
        except (TypeError, ValueError):
            return Plan(valid=False)

        if not isinstance(data, dict):
            return Plan(valid=False)

        decision = data.get("decision")

        if decision == "ask":

            question = str(data.get("question") or "").strip()

            if question and len(question) <= 200:
                return Plan(kind="ask", question=question)

            return Plan(valid=False)

        if decision != "act":
            return Plan()

        raw_steps = data.get("steps")

        if not isinstance(raw_steps, list) or not raw_steps:
            return Plan(valid=False)

        steps = []

        for raw in raw_steps[:MAX_STEPS]:

            if not isinstance(raw, dict):
                return Plan(valid=False)

            checked = self._check_step(raw.get("action"), raw.get("value"))

            if isinstance(checked, Plan):
                return checked

            if checked is None:
                return Plan(valid=False)

            steps.append(checked)

        return Plan(kind="act", steps=steps)

    def _check_step(self, action, value):
        """Return a Step, a Plan (to ask a question), or None if invalid."""

        if action not in ACTIONS:
            return None

        value = re.sub(r"\s+", " ", str(value or "")).strip()

        if len(value) > MAX_VALUE_LENGTH:
            return None

        if action == "open_browser":
            return Step(action, "", "open browser")

        if action == "open_website":

            site = value.lower()

            if site in self.websites:
                return Step(action, site, f"go to {site}")

            if _URL.match(value):
                return Step(action, value, f"go to {value}")

            if _DOMAIN.match(site):
                return Step(action, site, f"go to https://{site}")

            return None

        if action == "web_search":

            if len(value) < 2:
                return None

            return Step(action, value, f"search {value}")

        if action == "research":

            if len(value) < 3:
                return None

            return Step(action, value, f"research {value}")

        if action == "open_app":

            if not value:
                return None

            if self.app_checker(value):
                return Step(action, value, f"open {value}")

            return Plan(
                kind="ask",
                question=(
                    f"I don't know how to open '{value}' yet. "
                    "Which app or folder do you mean?"
                )
            )

        if action == "calculate":

            if (
                not _EXPRESSION.match(value)
                or not re.search(r"\d", value)
                or not re.search(r"[+\-*/%]", value)
                or len(value) > 60
            ):
                return None

            return Step(action, value, f"calculate {value}")

        if action == "switch_mode":

            mode = value.lower()

            if mode not in MODES:
                return None

            return Step(action, mode, "")

        if action in BUILTIN_COMMANDS:
            return Step(action, "", BUILTIN_COMMANDS[action])

        return None
