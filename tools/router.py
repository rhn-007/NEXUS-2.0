
"""
NEXUS Tool Router

Decides which tool handles a request.
"""

from tools.calculator import CalculatorTool


class ToolResult:

    def __init__(
        self,
        success=False,
        message=""
    ):

        self.success = success
        self.message = message


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

            result = application_tool.execute(text)

            return ToolResult(
                True,
                str(result)
            )

        # ==========================
        # OTHER REGISTERED TOOLS
        # ==========================

        for tool in self.registry.all():

            if tool.name in ["browser", "application"]:
                continue

            if tool.can_handle(text):

                result = tool.execute(text)

                if (
                    hasattr(result, "success")
                    and hasattr(result, "message")
                ):

                    return ToolResult(
                        result.success,
                        result.message
                    )

                return ToolResult(
                    True,
                    str(result)
                )

        return ToolResult()
