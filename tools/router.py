
"""
NEXUS Tool Router

Decides which tool handles a request.
"""

from tools.calculator import CalculatorTool
from ui.status import activity


class ToolResult:

    def __init__(
        self,
        success=False,
        message="",
        spoken=None
    ):

        self.success = success
        self.message = message

        # Optional shorter text to say out loud. None means say the message.
        self.spoken = spoken


class ToolRouter:

    def __init__(
        self,
        registry
    ):

        self.registry = registry
        self.calculator = CalculatorTool()

    def execute(
        self,
        text
    ):

        if not text:
            return ToolResult()

        query = text.lower().strip()

        # ==========================
        # CALCULATOR
        # ==========================

        if self.calculator.can_handle(text):

            with activity("Calculating"):
                result = self.calculator.execute(text)

            if result is not None:

                return ToolResult(
                    True,
                    str(result)
                )

        # ==========================
        # BROWSER PRIORITY
        # ==========================

        browser_tool = self.registry.get("browser")

        browser_commands = [
            "open browser",
            "launch browser",
            "start browser",
            "open website",
            "open youtube",
            "open google",
            "open github",
            "open wikipedia",
            "open reddit",
            "open chatgpt",
            "open instagram",
            "open whatsapp web",
            "go to",
            "visit",
            "browse",
            "search",
            "google"
        ]

        is_browser_command = any(
            command in query
            for command in browser_commands
        )

        if (
            browser_tool
            and is_browser_command
            and browser_tool.can_handle(text)
        ):

            with activity(
                "Searching"
                if any(w in query for w in ("search", "google"))
                else "Opening website"
            ):
                result = browser_tool.execute(text)

            if hasattr(result, "success"):

                return ToolResult(
                    result.success,
                    result.message
                )

            return ToolResult(
                True,
                str(result)
            )

        # ==========================
        # APPLICATION CONTROL
        # ==========================

        application_tool = self.registry.get("application")

        if (
            application_tool
            and application_tool.can_handle(text)
        ):

            with activity("Opening application"):
                result = application_tool.execute(text)

            if hasattr(result, "success") and hasattr(result, "message"):
                data = getattr(result, "data", None) or {}
                return ToolResult(
                    bool(result.success),
                    str(result.message or ""),
                    data.get("spoken") if isinstance(data, dict) else None
                )

            # ApplicationTool must return an explicit ToolResponse. Treat
            # unexpected legacy values as failures rather than reporting
            # that an application definitely opened.
            return ToolResult(
                False,
                str(result) if result is not None else
                "The application tool returned no result."
            )

        # ==========================
        # OTHER REGISTERED TOOLS
        # ==========================

        for tool in self.registry.all():

            if tool.name in ["browser", "application"]:
                continue

            if tool.can_handle(text):

                with activity(
                    "Researching"
                    if tool.name == "research"
                    else "Working"
                ):
                    result = tool.execute(text)

                if (
                    hasattr(result, "success")
                    and hasattr(result, "message")
                ):

                    spoken = (
                        getattr(result, "data", None) or {}
                    ).get("spoken")

                    return ToolResult(
                        result.success,
                        result.message,
                        spoken
                    )

                return ToolResult(
                    True,
                    str(result)
                )

        return ToolResult()
