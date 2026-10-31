"""Plans and coordinates safe multi-step NEXUS actions."""

import re

from tools.router import ToolResult


class ActionPlanner:
    """Uses the language model to plan only actions supported by local tools."""

    SEQUENCE_PATTERNS = (
        r"\band then\b",
        r"\bthen\b",
        r"\bafter that\b",
        r"\bafterwards\b",
        r"\bonce .+\b",
        r"\bfirst .+\bthen\b"
    )

    ACTION_VERBS = (
        "open",
        "launch",
        "start",
        "visit",
        "browse",
        "search",
        "google",
        "go to",
        "calculate",
        "solve"
    )

    def __init__(self, llm, tool_router):
        self.llm = llm
        self.tool_router = tool_router

    def should_plan(self, request):
        text = request.lower()

        if any(
            re.search(pattern, text)
            for pattern in self.SEQUENCE_PATTERNS
        ):
            return True

        has_conjunction = bool(re.search(r"\band\b", text))
        action_count = sum(
            1 for verb in self.ACTION_VERBS
            if re.search(r"\b" + re.escape(verb) + r"\b", text)
        )

        return has_conjunction and action_count >= 2

    def execute_if_needed(self, request):
        """Return None for ordinary requests, otherwise a handled result."""
        if not self.should_plan(request):
            return None

        steps = self.llm.generate_action_plan(
            request,
            self.tool_router.describe_tools()
        )

        if not steps:
            return ToolResult(
                success=False,
                message=(
                    "I couldn't create a valid action plan for that request. "
                    "Try separating it into clearer actions."
                ),
                handled=True
            )

        return self.tool_router.execute_plan(steps)
